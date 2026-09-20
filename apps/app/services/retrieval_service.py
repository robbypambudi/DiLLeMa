"""Retrieve and rank source evidence independently of answer generation."""

import json
import re
from functools import cached_property
from uuid import UUID

from loguru import logger

from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.schema.question_schema import CreateQuestion
from app.services.conversation_context import contextual_query
from app.services.scope_gate import trivial_reason
from rag.evidence import source_key

MAX_PAGES_FOR_GENERATOR = 4


def _ignore_stage(stage: str, **detail) -> None:
    """Default progress sink for callers that do not report retrieval stages."""


def _resolves_nothing(rewritten: str, question: str) -> bool:
    """Whether a rewrite added nothing the original question did not have.

    An echo and a truncation both leave the follow-up as context-dependent as
    it started, so neither may replace the carried topic.
    """
    if not rewritten.strip():
        return True
    def words(text: str) -> set[str]:
        return set(re.findall(r"[^\W_]+", text.lower()))

    return not (words(rewritten) - words(question))


def _log_evidence_trace(payload, candidates, ranked, packed, reason):
    """Identifiers and scores only; never log document text or the question."""
    logger.info(
        "RAG evidence trace: {}",
        json.dumps(
            {
                "question_id": str(getattr(payload, "question_id", "")),
                "collection_id": str(payload.collection_id),
                "reason": reason,
                "candidate_count": len(candidates),
                "ranked": [
                    {
                        "chunk_id": p[2].get("chunk_id"),
                        "point_id": p[2].get("point_id"),
                        "file_id": p[2].get("file_id"),
                        "score": p[2].get("rerank_score"),
                    }
                    for p in ranked
                ],
                "packed": [
                    {
                        "file_id": p[2].get("file_id"),
                        "parent_id": p[2].get("parent_id"),
                        "document_version": p[2].get("document_version"),
                        "chunk_ids": p[2].get("evidence_chunk_ids", []),
                        "chars": len(p[1]),
                    }
                    for p in packed
                ],
            }
        ),
    )


def pack_parent_pages(pairs: list, max_pages: int = MAX_PAGES_FOR_GENERATOR) -> list:
    """Keep every retrieved leaf of selected parents, then add nearby context.

    The 5,000-character expansion budget is soft: an oversized evidence span
    is kept whole. Never trade away a matched leaf for the beginning of a page.
    """
    if max_pages <= 0:
        return []
    groups = {}
    for pair in pairs:
        key = source_key(pair)
        if key not in groups and len(groups) >= max_pages:
            continue
        groups.setdefault(key, []).append(pair)

    packed = []
    for group in groups.values():
        meta = dict(group[0][2] if len(group[0]) > 2 else {})
        parts = []
        windows = []
        spans = []
        citation_texts = []
        for pair in group:
            item = pair[2] if len(pair) > 2 else {}
            leaf = str(item.get("evidence_text") or pair[1] or "").strip()
            citation_texts.append(leaf)
            context = str(item.get("evidence_context") or "").strip()
            if context and context not in leaf:
                leaf = f"{context}\n{leaf}"
            # Claim formatting carries qualifiers and must not be replaced by
            # just its quotation or a neighbouring vector page.
            if item.get("claim_id"):
                leaf = str(pair[1] or "").strip()
            if leaf and not any(leaf in part for part in parts):
                parts = [part for part in parts if part not in leaf]
                parts.append(leaf)
            parent = str(
                item.get("parent_window") or item.get("page_text") or ""
            ).strip()
            if parent and not item.get("claim_id"):
                windows.append(parent)
                citation_texts.append(parent)
            spans.append(
                {
                    key: item.get(key)
                    for key in (
                        "chunk_id",
                        "section_id",
                        "source_start",
                        "source_end",
                        "offset_basis",
                    )
                }
            )
        for window in windows:
            expanded = [part for part in parts if part not in window]
            if any(window in part for part in expanded):
                continue
            # Source context precedes a detached leaf only when it contains
            # that leaf. Otherwise put the matched evidence first.
            candidate = expanded + [window]
            if len("\n\n".join(candidate)) <= 5000:
                parts = candidate
        body = "\n\n".join(parts)
        meta["evidence_spans"] = spans
        meta["evidence_chunk_ids"] = [s["chunk_id"] for s in spans if s["chunk_id"]]
        # Citation selection sees exactly the evidence the generator saw.
        # Keep canonical slices separate: table headers added to a late row
        # must not become one fictitious contiguous quotation.
        meta["citation_texts"] = list(
            dict.fromkeys(text for text in citation_texts if text and text in body)
        )
        packed.append([group[0][0], body, meta])
    return packed


def drop_weak_evidence(pairs: list, ratio: float) -> list:
    """Keep evidence scoring at least `ratio` of the best reranked match."""
    scores = [pair[2].get("rerank_score") for pair in pairs if len(pair) > 2]
    if not ratio or not scores or any(score is None for score in scores):
        return pairs
    floor = max(scores) * ratio
    return [pair for pair in pairs if pair[2]["rerank_score"] >= floor]


def format_graph_evidence(item: dict) -> str:
    lines = [f"Klaim: {item.get('statement') or ''}"]
    qualifiers = item.get("qualifiers")
    if qualifiers:
        lines.append(f"Kualifikasi: {json.dumps(qualifiers, ensure_ascii=False)}")
    quote = item.get("quote") or ""
    if quote:
        lines.append(f"Kutipan: {quote}")
    source = item.get("text") or ""
    if source and source != quote:
        lines.append(f"Teks sumber: {source[:1200]}")
    return "\n".join(lines)


class RetrievalService:
    def __init__(
        self,
        collections_repository,
        qdrant_client,
        augment_query_generator,
        knowledge_repository=None,
        embedding_model=None,
        re_ranking=None,
        standalone_question=None,
    ):
        self.collections_repository = collections_repository
        self.qdrant_client = qdrant_client
        self.augment_query_generator = augment_query_generator
        self.knowledge_repository = knowledge_repository
        if embedding_model is not None:
            self.embedding_model = embedding_model
        if re_ranking is not None:
            self.re_ranking = re_ranking
        if standalone_question is not None:
            self.standalone_question = standalone_question

    @cached_property
    def standalone_question(self):
        from agents.standalone_question import StandaloneQuestion

        return StandaloneQuestion()

    @cached_property
    def embedding_model(self):
        from rag.embedding.default_embedding import DefaultEmbedding
        from rag.embedding.device import embedding_device

        return DefaultEmbedding(device=embedding_device())

    @cached_property
    def re_ranking(self):
        from rag.llm.re_rank import ReRanking

        return ReRanking()

    def _search_into(self, candidates, seed_file_ids, collection, payload, query):
        """Add one query's hits to the shared pool and return that query's own.

        The pool is shared and deduplicated, but a probe has to judge the hits
        of the query it is probing, not whatever an earlier query put in front
        of them -- so this query's results come back in their own order.
        """
        found = []
        query_embedding = self.embedding_model.encode(query)
        if hasattr(query_embedding, "ndim") and query_embedding.ndim > 1:
            query_embedding = query_embedding[0]
        search_result = self.qdrant_client.search(
            collection_name=collection.vectordb_collection_name,
            query_vector=query_embedding,
            query_text=query,
            limit=settings.RETRIEVAL_CANDIDATES,
        )
        for hit in search_result:
            metadata = dict(hit.payload or {})
            metadata.setdefault("point_id", str(hit.id))
            text = metadata.get("document", "")
            if not text:
                continue
            pair = candidates.setdefault(
                str(hit.id), [payload.question_text, text, metadata]
            )
            found.append(pair)
            try:
                seed_file_ids.add(UUID(str(metadata.get("file_id"))))
            except (ValueError, TypeError):
                pass
        return found

    def _probe(self, pairs: list, query: str) -> float | None:
        """Best cross-encoder score over the head of `pairs`, or None if unusable.

        Only `SCOPE_PROBE_CANDIDATES` hits are scored: the full rerank scores
        RETRIEVAL_CANDIDATES per query, so this stays a rounding error beside it.
        Hybrid hits arrive in fusion order, whose scores rank documents but do
        not measure relevance -- hence the cross-encoder rather than `hit.score`.
        """
        probe = pairs[: settings.SCOPE_PROBE_CANDIDATES]
        if not probe:
            return None
        try:
            return float(self.re_ranking.best_score(probe, query))
        except Exception as exc:
            # A probe that cannot run -- or cannot be read as a score -- must
            # not cost the user their answer. The rerank floor still applies.
            logger.warning(
                "Scope probe unavailable; continuing with full retrieval ({})",
                type(exc).__name__,
            )
            return None

    def _resolve_query(
        self, payload, collection, candidates, seed_file_ids, history, report
    ) -> str | None:
        """What to search with, or None when nothing should be searched at all.

        Three outcomes, decided on evidence rather than on the shape of the
        sentence, because no lexical rule separates "kalau untuk S2 bagaimana?"
        (a follow-up) from "kalau jadwal kuliahnya?" (a new topic):

        * the question already retrieves well -> search it as it stands, and
          keep the conversation out of it;
        * it retrieves nothing alone but retrieves well once the topic is
          restored -> a real follow-up, worth rewriting into a standalone
          question;
        * neither -> the collection does not cover it.

        The bare question is probed first for a reason: a carried topic scores
        high for a genuine follow-up *and* for a topic switch, so that score
        cannot tell them apart. Only the bare score reveals that the question
        stands on its own.
        """
        question = payload.question_text

        def reject(reason):
            # SCOPE_GATE_ENABLED turns off rejection, not the decision: the
            # question still has to be resolved before it can be searched.
            if not settings.SCOPE_GATE_ENABLED:
                return question
            report("out_of_scope", reason=reason)
            return None

        report("searching", queries=1, collection=collection.collection_name)
        bare_pairs = self._search_into(
            candidates, seed_file_ids, collection, payload, question
        )
        if not bare_pairs and not candidates:
            return reject("empty_collection")

        report("checking", passages=min(len(bare_pairs), settings.SCOPE_PROBE_CANDIDATES))
        alone = self._probe(bare_pairs, question)
        if alone is None or alone >= settings.SCOPE_SELF_SUFFICIENT_SCORE:
            # Unprobeable questions continue: the gate is an optimisation.
            return question

        if history:
            carried = contextual_query(question, history)
            if carried != question:
                report("following_up")
                carried_pairs = self._search_into(
                    candidates, seed_file_ids, collection, payload, carried
                )
                with_topic = self._probe(carried_pairs, carried)
                if (
                    with_topic is not None
                    and with_topic >= settings.SCOPE_FOLLOWUP_MIN_SCORE
                ):
                    return self._standalone(question, carried, history, report)

        # Not self-sufficient and not a follow-up: fall back to the plain gate,
        # which must never reject what it would have allowed before.
        if alone >= settings.SCOPE_GATE_MIN_SCORE:
            return question
        logger.info(
            "Question rejected by scope probe (best {:.4f} < {})",
            alone,
            settings.SCOPE_GATE_MIN_SCORE,
        )
        return reject("no_relevant_passage")

    def _standalone(self, question: str, carried: str, history: list, report) -> str:
        """The follow-up as one self-contained question.

        The carried string is the fallback, not the goal: it searches well only
        while the topic holds, which is exactly what a rewrite makes explicit.

        The rewrite is reported back with its text, unlike every other stage:
        it is the asker's own question restated, returned over their own
        stream, and being told "rephrased" without being told *how* leaves
        them unable to tell a good rewrite from one that changed the subject.
        """
        if not settings.FOLLOWUP_REWRITE:
            report("rewritten", query=carried)
            return carried
        rewritten = self.standalone_question.rewrite(question, history) or ""
        if _resolves_nothing(rewritten, question):
            # A small model often echoes the question back, or shortens it.
            # Measured against a served 0.8B: "Selain itu siapa lagi?" came
            # back as "Siapa lagi?" and "Apa saja materi yang dipelajari di
            # dalamnya?" unchanged, which then retrieved another course
            # entirely. An echo resolved no reference, so the carried topic is
            # still the better search string -- never discard it for a no-op.
            rewritten = carried
        report("rewritten", query=rewritten)
        return rewritten

    def retrieve(
        self,
        payload: CreateQuestion,
        using_augment_query: bool | None = False,
        on_stage=None,
        history: list[tuple[str, str]] | None = None,
    ):
        """Hybrid leaf retrieval, then parent-page packing for generation.

        `using_augment_query=None` defers to the `QUERY_AUGMENTATION` setting.
        `on_stage(stage, **counts)` reports progress while the work runs; it
        carries counts only, never document text or the question itself.
        `history` lets a follow-up be searched with the topic it omitted.
        """
        report = on_stage or _ignore_stage
        collection = self.collections_repository.read_by_id(payload.collection_id)
        if not collection:
            raise NotFoundError(
                f"Collection with ID {payload.collection_id} not found."
            )

        reason = trivial_reason(payload.question_text)
        if reason:
            # Nothing was spent: no embedding, no search, no rewrite call.
            report("out_of_scope", reason=reason)
            logger.info("Question rejected before retrieval ({})", reason)
            return []

        if using_augment_query is None:
            using_augment_query = settings.QUERY_AUGMENTATION

        candidates = {}
        seed_file_ids = set()
        search_query = self._resolve_query(
            payload, collection, candidates, seed_file_ids, history or [], report
        )
        if search_query is None:
            return []
        rewritten = search_query != payload.question_text

        queries = [search_query]
        if rewritten:
            # The rewrite already states the question the way the corpus is
            # written; a second LLM call to paraphrase it buys little, and the
            # promise was at most one rewrite call per question.
            self._search_into(
                candidates, seed_file_ids, collection, payload, search_query
            )
        elif using_augment_query:
            report("augmenting")
            queries = self.augment_query_generator.augment(search_query)
            extra = [query for query in queries if query != search_query]
            if extra:
                report(
                    "searching",
                    queries=len(extra),
                    collection=collection.collection_name,
                )
            for query in extra:
                self._search_into(candidates, seed_file_ids, collection, payload, query)

        graph_used = False
        if settings.KG_ENABLED and self.knowledge_repository:
            report("graph", candidates=len(candidates))
            try:
                evidence = self.knowledge_repository.retrieve(
                    payload.collection_id,
                    payload.question_text,
                    seed_file_ids,
                    limit=settings.KG_RETRIEVAL_LIMIT,
                )
                for item in evidence:
                    candidates["graph:" + str(item["id"])] = [
                        payload.question_text,
                        format_graph_evidence(item),
                        {
                            "file_name": item["file_name"],
                            "file_id": str(item.get("file_id") or ""),
                            "page": item["page"],
                            "quote": item["quote"],
                            "claim_id": str(item["id"]),
                        },
                    ]
                graph_used = bool(evidence)
            except Exception as exc:
                logger.warning(
                    "Graph retrieval unavailable; using vector evidence ({})",
                    type(exc).__name__,
                )

        pairs = list(candidates.values())
        if not pairs:
            _log_evidence_trace(payload, [], [], [], "no_candidates")
            report("no_evidence", candidates=0)
            return []
        # The question and its translation: keyword rewrites widen the search,
        # but scoring every candidate against every rewrite multiplies the
        # cross-encoder's work for little gain.
        # At most two, and never the carried string: scoring a passage
        # against "<old question> <new question>" is what lets a stale document
        # outrank the one that answers the question actually asked.
        variants = list(dict.fromkeys([search_query, *queries, payload.question_text]))[
            :2
        ]
        rerank_options = {"queries": variants} if len(variants) > 1 else {}
        report("ranking", candidates=len(pairs), graph=int(graph_used))
        ranked = self.re_ranking.rank(
            pairs=pairs,
            top_results=12 if graph_used else 8,
            min_score=settings.RERANK_MIN_SCORE,
            **rerank_options,
        )
        if not ranked:
            _log_evidence_trace(payload, pairs, [], [], "below_relevance_floor")
            report("no_evidence", candidates=len(pairs))
            logger.info(
                "No evidence cleared the relevance floor ({}) for collection {}",
                settings.RERANK_MIN_SCORE,
                payload.collection_id,
            )
            return []
        report("reading", passages=len(ranked))
        packed = pack_parent_pages(
            drop_weak_evidence(ranked, settings.RERANK_RELATIVE_FLOOR)
        )
        _log_evidence_trace(payload, pairs, ranked, packed, "packed")
        return packed
