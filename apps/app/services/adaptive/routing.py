"""Cheap routing and evidence heuristics, not calibrated truth probabilities."""

import re
import unicodedata

from pydantic import BaseModel, Field

from .config import RoutingConfig
from .contracts import AnswerRequest, Document, EvidenceEvaluation, Strategy

STOP = set(
    "the a an is are of to for in on and or with what which how does do our please based berdasarkan apa berapa siapa kapan yang dan atau dari di ke untuk dengan apakah bagaimana saya kami ini itu dokumen documentation document compare bandingkan versus vs between antara".split()
)


def normalize(query: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", query).split())


def terms(text: str) -> set[str]:
    return {
        word.casefold()
        for word in re.findall(r"[\w-]+", text)
        if (word.casefold() not in STOP and len(word) > 1)
        or (len(word) == 1 and (word.isupper() or word.isdigit()))
    }


class Analysis(BaseModel):
    query: str
    complexity: float
    external_knowledge: bool
    reasons: list[str] = Field(default_factory=list)
    goals: list[str] = Field(default_factory=list)


def plan(query: str, config: RoutingConfig) -> list[str]:
    # Deterministic decomposition retains the original query in every search.
    # No invented entities and no model-issued tools.
    comparison = re.search(
        r"(?:compare|bandingkan|perbandingan|between|antara)\s+(.+?)\s+(?:and|dan|versus|vs\.?|dengan)\s+(.+)",
        query,
        re.I,
    )
    if comparison:
        left, right = comparison.groups()
        right = re.split(r"\s+(?:based on|berdasarkan|using)\b", right, flags=re.I)[0]
        return [left.strip(" .?"), right.strip(" .?")][: config.max_subqueries]
    clauses = re.split(
        r"[;?]\s*|\b(?:and then|kemudian|selanjutnya)\b", query, flags=re.I
    )
    return [p.strip() for p in clauses if len(terms(p)) > 0][
        : config.max_subqueries
    ] or [query]


def analyze(request: AnswerRequest, config: RoutingConfig) -> Analysis:
    query = normalize(request.query)
    lower = query.casefold()
    transform = bool(
        re.match(
            r"(?:please\s+)?(?:rewrite|rephrase|summari[sz]e|translate|format|paraphrase|ringkas|rangkum|terjemahkan|parafrase|tulis ulang|ubah format)\b",
            lower,
        )
    )
    provided = bool(request.text and request.text.strip()) or (
        transform and bool(re.search(r":\s*\S+", query))
    )
    creative = bool(
        re.match(
            r"(?:please\s+)?(?:write|draft|buat|tulis)\s+(?:a |an |sebuah )?(?:thank.you|poem|puisi|ucapan|greeting|contoh email)\b",
            lower,
        )
    )
    arithmetic = bool(
        re.fullmatch(r"(?:calculate|hitung)\s+[\d\s+*/().%-]+[?]?", lower)
    )
    general = bool(
        re.match(
            r"(?:how (?:do|can) i|bagaimana cara)\s+(?:organize|structure|format|menyusun|memformat)\b",
            lower,
        )
    ) and not re.search(r"policy|kebijakan|latest|terbaru|our|kami", lower)
    direct = (
        (transform and provided)
        or creative
        or arithmetic
        or general
        or lower.strip("!?. ") in {"hello", "hi", "halo", "thanks", "terima kasih"}
    )
    reasons = []
    score = 0.0
    for pattern, label, weight in [
        (
            r"\b(compare|comparison|versus|vs|bandingkan|perbandingan|reconcile|bertentangan|kontradiksi)\b",
            "comparison_or_conflict",
            0.7,
        ),
        (
            r"\b(across|multiple sources|several documents|lintas|beberapa (sumber|dokumen))\b",
            "multiple_sources",
            0.45,
        ),
        (
            r"\b(and then|then determine|depends on|kemudian|selanjutnya|bergantung)\b",
            "multi_hop",
            0.55,
        ),
        (
            r"\b(aggregate|total|summarize all|seluruh|gabungkan|rata-rata)\b",
            "aggregation",
            0.35,
        ),
    ]:
        if re.search(pattern, lower):
            reasons.append(label)
            score += weight
    if len(query.split()) >= config.long_query_words:
        reasons.append("long_query")
        score += 0.15
    if len(re.findall(r"\b(?:19|20)\d{2}\b", query)) > 1:
        reasons.append("multiple_periods")
        score += 0.15
    return Analysis(
        query=query,
        complexity=min(score, 1),
        external_knowledge=not direct,
        reasons=reasons or ["external_lookup" if not direct else "self_contained_task"],
        goals=plan(query, config),
    )


def route(
    analysis: Analysis, forced: Strategy | None, config: RoutingConfig
) -> Strategy:
    if forced:
        return forced
    if not analysis.external_knowledge:
        return Strategy.DIRECT
    return (
        Strategy.AGENTIC
        if analysis.complexity >= config.agentic_complexity_threshold
        else Strategy.RAG
    )


def relevance(document: Document) -> float:
    if document.score_kind == "reranker":
        return max(0, min(1, document.score))
    if document.score_kind == "cosine":
        return max(0, min(1, (document.score + 1) / 2))
    # RRF is a rank-fusion score, not a cosine or probability. Do not pretend
    # to calibrate its arbitrary magnitude; rely primarily on coverage.
    return 0.5


def evaluate(
    query: str, goals: list[str], docs: list[Document], config: RoutingConfig
) -> EvidenceEvaluation:
    if not docs:
        return EvidenceEvaluation(missing_information=goals or [query])
    sets = [terms(d.text + " " + d.section + " " + d.context) for d in docs]
    union = set().union(*sets)
    wanted = terms(query)
    coverage = len(wanted & union) / max(1, len(wanted))
    missing = [
        g
        for g in goals
        if len(terms(g) & union) / max(1, len(terms(g))) < config.coverage_threshold
    ]
    unique_sources = len({d.file_id or d.id for d in docs})
    if (
        re.search(
            r"\b(across|multiple sources|several documents|lintas|beberapa (sumber|dokumen))\b",
            query,
            re.I,
        )
        and unique_sources < config.multiple_sources_min
    ):
        missing.append("multiple_sources")
    scores = sorted((relevance(d) for d in docs), reverse=True)
    redundancy = 1 - len({normalize(d.text) for d in docs}) / len(docs)
    confidence = max(
        0,
        min(
            1,
            (0.4 * scores[0] + 0.2 * sum(scores) / len(scores) + 0.4 * coverage)
            * (1 - 0.25 * redundancy),
        ),
    )
    conflict = False
    for i, left in enumerate(sets):
        for right in sets[i + 1 :]:
            words_left = {w for w in left if not any(c.isdigit() for c in w)}
            words_right = {w for w in right if not any(c.isdigit() for c in w)}
            overlap = len(words_left & words_right) / max(
                1, len(words_left | words_right)
            )
            nums_left = {w for w in left if any(c.isdigit() for c in w)}
            nums_right = {w for w in right if any(c.isdigit() for c in w)}
            years_left = {w for w in nums_left if re.fullmatch(r"(?:19|20)\d{2}", w)}
            years_right = {w for w in nums_right if re.fullmatch(r"(?:19|20)\d{2}", w)}
            if years_left and years_right and years_left.isdisjoint(years_right):
                continue
            negations = {"not", "never", "tidak", "bukan", "dilarang"}
            if overlap >= config.conflict_overlap and (
                (nums_left and nums_right and nums_left != nums_right)
                or bool(left & negations) != bool(right & negations)
            ):
                conflict = True
    sufficient = (
        confidence >= config.retrieval_confidence_threshold
        and coverage >= config.coverage_threshold
        and not missing
        and not conflict
    )
    return EvidenceEvaluation(
        sufficient=sufficient,
        confidence=confidence,
        evidence_coverage=coverage,
        missing_information=missing,
        potential_conflict=conflict,
        next_action="answer" if sufficient else "retrieve",
        signals={
            "top_1": scores[0],
            "top_k_mean": sum(scores) / len(scores),
            "score_gap": scores[0] - scores[-1],
            "unique_sources": len({d.file_id or d.id for d in docs}),
            "redundancy": redundancy,
        },
    )
