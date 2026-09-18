"""Split a page along the structure technical documents are written in.

A fixed-size window does not know what a clause is, so "Pasal 12" ends up
half in one chunk and half in the next, and retrieval returns a fragment that
answers nothing. Splitting on headings first keeps each provision whole and,
just as usefully, gives every chunk a heading to be indexed under -- PDF pages
otherwise carry no section label at all.
"""

import re

# Deliberately narrow. A heading occupies its own short line; anything that
# reads like a sentence (lower-case start, trailing full stop, long line) is
# body text, and treating list items as headings would shatter the page.
_HEADING = re.compile(
    r"^[ \t]*("
    r"(?:BAB|Bab)[ \t]+(?:[IVXLCDM]+|\d+)\b[^\n]{0,80}"
    r"|(?:BAGIAN|Bagian)[ \t]+[^\n]{1,80}"
    r"|(?:PASAL|Pasal)[ \t]+\d+[A-Za-z]?"
    r"|(?:LAMPIRAN|Lampiran)[ \t]+[^\n]{0,80}"
    r"|\d+(?:\.\d+){0,3}[.)]?[ \t]+[A-Z][^\n]{2,80}"
    # An unnumbered title set in capitals on its own line: "DAFTAR ISI",
    # "LIST OF ELECTIVE COURSES". Two words at least, so a lone acronym or
    # table label is not mistaken for one.
    r"|[A-Z][A-Z0-9&()\-–]*(?:[ \t]+[A-Z0-9&()\-–]+){1,11}"
    r")[ \t]*$",
    re.M,
)


def split_structure(text: str) -> list[tuple[str, str]]:
    """(heading, block) pairs in reading order; one ("", text) pair if unstructured.

    Each block keeps its own heading line, so a chunk taken from it still says
    which provision it belongs to.
    """
    headings = [
        match for match in _HEADING.finditer(text) if not _looks_like_prose(match)
    ]
    if not headings:
        return [("", text)]

    blocks: list[tuple[str, str]] = []
    preamble = text[: headings[0].start()]
    if preamble.strip():
        blocks.append(("", preamble))
    for position, match in enumerate(headings):
        end = (
            headings[position + 1].start()
            if position + 1 < len(headings)
            else len(text)
        )
        blocks.append((match.group(1).strip(), text[match.start() : end]))
    return blocks


_SINGLE_NUMBER = re.compile(r"^\d+[.)]?[ \t]")
_LEADER = re.compile(r"\.{4,}|…")


def _looks_like_prose(match: re.Match) -> bool:
    heading = match.group(1).strip()
    # A table-of-contents line names a heading; it does not start one.
    if _LEADER.search(heading):
        return True
    # "1. Students are able to ..." is a list item. A one-level number is a
    # heading only when the line is set in capitals, as section titles are.
    if _SINGLE_NUMBER.match(heading) and not heading.isupper():
        return True
    # "1. Rektor menetapkan pagu penelitian." is a numbered sentence, not a
    # heading: it ends the way sentences end.
    return heading.endswith((".", ",", ";", ":")) and not heading.lower().startswith(
        ("bab", "bagian", "pasal", "lampiran")
    )
