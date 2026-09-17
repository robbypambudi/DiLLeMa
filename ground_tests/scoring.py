"""Deterministic diagnostics, not a semantic judge or proof of factual truth."""

from collections import Counter
from html import unescape
from html.parser import HTMLParser
import re
import unicodedata

SCORER_VERSION = 1
REFUSALS = (
    "tidak disebutkan", "tidak tersedia", "tidak ada informasi", "tidak memiliki informasi",
    "tidak mencantumkan", "tidak diketahui", "tidak dijelaskan", "tidak dapat menentukan",
    "not provided", "not mentioned", "not specified", "do not know",
)


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def normalize(text):
    # Source footers contain evidence that must not earn answer-quality points.
    text = re.split(r"(?:<p>\s*)?(?:<b>)?sumber konteks\b", text, flags=re.I)[0]
    parser = PlainText()
    parser.feed(text)
    text = unicodedata.normalize("NFKC", unescape(" ".join(parser.parts))).lower()
    return " ".join(re.findall(r"[^\W_]+", text, re.UNICODE))


def contains(text, phrase):
    return f" {normalize(phrase)} " in f" {normalize(text)} "


def token_f1(answer, reference):
    left, right = Counter(normalize(answer).split()), Counter(normalize(reference).split())
    if not left or not right:
        return 0.0
    common = sum((left & right).values())
    precision, recall = common / sum(left.values()), common / sum(right.values())
    return 2 * precision * recall / (precision + recall) if common else 0.0


def score_case(case, prediction):
    answer = prediction.get("answer", "")
    contexts = prediction.get("contexts", [])
    error = prediction.get("error")
    refusal = any(contains(answer, phrase) for phrase in REFUSALS)
    facts = [any(contains(answer, alias) for alias in aliases) for aliases in case["facts"]]
    forbidden = [value for value in case["forbidden"] if contains(answer, value)]
    # A number in an unanswerable answer is a conservative hallucination signal.
    abstention = refusal and not re.search(r"\d", normalize(answer))
    ranks = []
    for evidence in case["evidence"]:
        ranks.append(next((index for index, context in enumerate(contexts, 1)
                           if context["document_id"] == evidence["document_id"]
                           and contains(context["text"], evidence["quote"])), None))
    answerable = not case.get("unanswerable", False)
    passed = not error and (all(facts) and not forbidden and not refusal if answerable else abstention)
    return {
        "case_pass": float(passed),
        "fact_recall": sum(facts) / len(facts) if facts and not error else (0.0 if facts else None),
        "token_f1": token_f1(answer, case["reference"]) if not error else 0.0,
        "evidence_recall": sum(rank is not None for rank in ranks) / len(ranks) if ranks and not error else (0.0 if ranks else None),
        "evidence_mrr": (1 / min(rank for rank in ranks if rank is not None)) if not error and any(ranks) else (0.0 if ranks else None),
        "abstention_pass": float(abstention and not error) if not answerable else None,
        "error_rate": float(bool(error)),
        "matched_facts": facts,
        "forbidden_hits": forbidden,
    }


METRICS = {
    "case_pass": "Rule-based case pass rate",
    "fact_recall": "Required fact recall",
    "token_f1": "Answer/reference token F1",
    "evidence_recall": "Required evidence recall (final contexts)",
    "evidence_mrr": "First relevant evidence MRR",
    "abstention_pass": "Unanswerable abstention pass rate",
    "error_rate": "Request error rate (lower is better)",
}


def aggregate(rows):
    summary = {}
    for metric in METRICS:
        values = [row["scores"][metric] for row in rows if row["scores"][metric] is not None]
        summary[metric] = {"value": sum(values) / len(values) if values else None, "n": len(values)}
    return summary
