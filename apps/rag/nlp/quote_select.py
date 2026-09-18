"""Choose the sentence on a source page that backs what the answer says.

Indexing can only store the head of a chunk as its quote, so the excerpt shown
next to a citation was whatever the chunk happened to start with -- usually a
heading or the tail of the previous paragraph. Which sentence actually supports
a claim is only knowable once the claim exists, so the choice is made at
citation time instead.

The result is always a contiguous slice of the page: the PDF panel highlights a
quote by searching the rendered page text for it, so a paraphrase or a stitched
excerpt would leave the reader on the right page with nothing lit up.
"""

import math
import re

from rag.nlp.tokens import content_stems

_BREAK = re.compile(r"(?<=[.!?;:])\s+|\n+")
_TAG = re.compile(r"<[^>]+>")

# Short enough to stay a quotation, long enough that the viewer's whitespace-
# stripped search has something distinctive to find.
MIN_QUOTE_CHARS = 60
MAX_QUOTE_CHARS = 350


def strip_markup(text: str) -> str:
    """Answers are HTML; their tags are not evidence terms."""
    return _TAG.sub(" ", text or "")


def sentence_spans(text: str) -> list[tuple[int, int]]:
    """Offsets of each sentence, so slices stay verbatim substrings."""
    spans: list[tuple[int, int]] = []
    start = 0
    for match in _BREAK.finditer(text):
        spans.append((start, match.start()))
        start = match.end()
    spans.append((start, len(text)))

    trimmed = []
    for begin, end in spans:
        while begin < end and text[begin].isspace():
            begin += 1
        while end > begin and text[end - 1].isspace():
            end -= 1
        if end - begin > 1:
            trimmed.append((begin, end))
    return trimmed


def _score(claim_terms: set[str], sentence: str) -> float:
    terms = set(content_stems(sentence))
    overlap = claim_terms & terms
    if not overlap:
        return 0.0
    # A shared number -- "Pasal 12", "2026", "Rp 4,5 miliar" -- is much stronger
    # evidence than a shared word, and it is what a reader verifies first.
    weight = sum(2.0 if any(c.isdigit() for c in term) else 1.0 for term in overlap)
    # Long sentences overlap with everything; normalise so they do not dominate.
    return weight / math.sqrt(len(terms))


def select_quote(
    claim: str,
    page_text: str,
    fallback: str = "",
    max_chars: int = MAX_QUOTE_CHARS,
) -> str:
    """The sentence in `page_text` that best supports `claim`.

    Falls back to the indexed quote when the page has no overlapping sentence,
    which is the honest outcome for a source the model did not really use.
    """
    text = page_text or ""
    claim_terms = set(content_stems(strip_markup(claim)))
    spans = sentence_spans(text)
    if not claim_terms or not spans:
        return fallback[:max_chars]

    best = max(
        range(len(spans)),
        # Ties go to the earliest sentence: on a page that repeats a term, the
        # first statement of it is the definition and the rest are references.
        key=lambda index: (_score(claim_terms, text[slice(*spans[index])]), -index),
    )
    if _score(claim_terms, text[slice(*spans[best])]) <= 0:
        return fallback[:max_chars]

    start, end = spans[best]
    # A one-line sentence ("Pasal 12.") is not enough for the viewer to locate,
    # so grow into the following sentences while the quote stays short.
    index = best
    while end - start < MIN_QUOTE_CHARS and index + 1 < len(spans):
        following = spans[index + 1][1]
        if following - start > max_chars:
            break
        index += 1
        end = following

    quote = text[start:end]
    if len(quote) > max_chars:
        cut = quote.rfind(" ", 0, max_chars)
        quote = quote[: cut if cut > MIN_QUOTE_CHARS else max_chars]
    return quote.strip()
