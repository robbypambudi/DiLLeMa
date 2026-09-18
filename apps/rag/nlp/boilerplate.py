"""Remove the page furniture that repeats on every page of a document.

A running header, a footer and a page number are extracted again for every
page, so they end up inside every chunk: they add nothing a reader asked for,
they push real text out of the window, and as BM25 terms they match the whole
document at once. They are recognisable only across pages -- one page cannot
tell a header from a heading -- so the removal happens after extraction, on
the document as a whole.
"""

import re
from collections import Counter

# Furniture is short, sits at the top or bottom of the page, and repeats.
MAX_LINE_CHARS = 90
EDGE_LINES = 3
# Only a short line is allowed to match with its numbers blanked out. A full
# sentence repeated across pages is a clause that really is stated on each of
# them, and "Pasal # ayat #" must not swallow it.
MAX_NUMBERED_MATCH_CHARS = 40
MIN_PAGES = 3
MIN_SHARE = 0.6

_DIGITS = re.compile(r"\d+")
_PAGE_NUMBER = re.compile(
    r"^(?:halaman|hal\.?|page|p\.)?\s*[ivxlcdm\d]{1,6}\s*(?:(?:/|dari|of)\s*\d+)?$",
    re.I,
)


def _key(line: str) -> str:
    """Page numbers differ per page; the line around them is what repeats."""
    folded = line.casefold()
    if len(line) > MAX_NUMBERED_MATCH_CHARS:
        return folded
    return _DIGITS.sub("#", folded)


def _edge_count(lines: list[str]) -> int:
    """Never treat a whole short page as its own header and footer."""
    return max(1, min(EDGE_LINES, len(lines) // 3))


def _edges(lines: list[str]) -> list[str]:
    count = _edge_count(lines)
    return lines[:count] + lines[-count:]


def repeating_keys(pages: list[str]) -> set[str]:
    counts: Counter[str] = Counter()
    for page in pages:
        lines = [line.strip() for line in page.splitlines() if line.strip()]
        for line in set(_edges(lines)):
            if len(line) <= MAX_LINE_CHARS:
                counts[_key(line)] += 1
    threshold = max(MIN_PAGES, int(len(pages) * MIN_SHARE))
    return {key for key, count in counts.items() if count >= threshold}


def strip_boilerplate(pages: list[str]) -> list[str]:
    """Drop repeated headers, footers and page numbers from each page.

    Only the outermost lines are considered: the same sentence in the middle of
    a page is body text, and a document too short to establish a pattern is left
    exactly as it was.
    """
    if len(pages) < MIN_PAGES:
        return pages
    repeated = repeating_keys(pages)
    if not repeated:
        return pages

    cleaned = []
    for page in pages:
        lines = page.splitlines()
        filled = [index for index, line in enumerate(lines) if line.strip()]
        count = _edge_count(filled)
        edges = set(filled[:count] + filled[-count:])
        kept = [
            line
            for index, line in enumerate(lines)
            if index not in edges or not _is_furniture(line.strip(), repeated)
        ]
        cleaned.append("\n".join(kept).strip())
    return cleaned


def _is_furniture(line: str, repeated: set[str]) -> bool:
    if not line or len(line) > MAX_LINE_CHARS:
        return False
    return _key(line) in repeated or bool(_PAGE_NUMBER.match(line))
