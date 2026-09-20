"""Give a follow-up question back the topic it left out.

"Berapa lama prosesnya?" names nothing a search can match, so retrieval --
and the scope gate in front of it -- would judge it against an empty topic
and reject a question the collection answers perfectly well.

Prepending the earlier questions is **not** how the result is searched. It is
a probe instrument and a fallback: measured against a real corpus, a passage
scored against "<old question> <new question>" lets the *old* topic's document
outrank the one that answers the new question (0.86 vs 0.79 in our fixture),
so a topic switch phrased briefly retrieves the wrong page with confidence.

`RetrievalService` therefore uses this string only to ask "does the corpus
answer this once the topic is restored?", and on yes hands the question to
`agents.standalone_question` for a real rewrite. This stays as the fallback
for when that rewrite is unavailable, where it is weaker but still better
than a follow-up with no topic at all.
"""

import re

# Words that point back at something already said instead of naming it.
_REFERENTIAL = re.compile(
    r"\b(itu|tersebut|tsb|tadi|sebelumnya|ini|mereka|beliau|keduanya)\b",
    re.IGNORECASE,
)
# The Indonesian possessive clitic: "prosesnya", "syaratnya", "biayanya".
_CLITIC = re.compile(r"\b\w{3,}nya\b", re.IGNORECASE)
# Openers that continue a previous question rather than start a new one.
_CONTINUATION = re.compile(
    r"^\s*(kalau|kalo|bagaimana\s+dengan|gimana\s+dengan|untuk|lalu|terus|"
    r"selain\s+itu|apa\s+lagi|dan|bagaimana\s+jika|jelaskan|rinci|detail)\b",
    re.IGNORECASE,
)
# Above this a question carries enough of its own terms to be searched alone.
MAX_ELLIPTIC_WORDS = 7
# Questions carried over. Two hops is enough to survive one intervening
# follow-up without dragging in a topic the user has already left.
HISTORY_QUESTIONS = 2
MAX_QUERY_CHARS = 300


def is_followup(question: str) -> bool:
    """Whether the question leans on the conversation to be understood."""
    text = (question or "").strip()
    if not text:
        return False
    if _REFERENTIAL.search(text) or _CLITIC.search(text) or _CONTINUATION.match(text):
        return True
    return len(text.split()) <= MAX_ELLIPTIC_WORDS


def contextual_query(question: str, history: list[tuple[str, str]]) -> str:
    """The string to search with: the question, plus the topic it assumes.

    Only earlier *questions* are carried, never the answers. An answer is long
    enough to outweigh the question in both BM25 and the cross-encoder, and
    carrying one would steer the next search back to the passages it was
    already built from -- entrenching a wrong retrieval instead of correcting it.
    """
    text = (question or "").strip()
    if not history or not is_followup(text):
        return text
    earlier = [
        previous.strip()
        for previous, _ in history[-HISTORY_QUESTIONS:]
        if previous and previous.strip()
    ]
    if not earlier:
        return text
    return " ".join([*earlier, text])[:MAX_QUERY_CHARS]
