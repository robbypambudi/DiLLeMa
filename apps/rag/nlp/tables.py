"""Make the Markdown tables PyMuPDF extracts fit for embedding and BM25.

`table.to_markdown()` renders every cell with its PDF styling, so a row reads
`|**Code (****_Kode Mata Kuliah_) **|EF234202|` and each table carries a
`|---|---|` rule, `ColN` placeholders for unnamed columns, and merged cells
repeated once per column. None of it is content: it dilutes the embedding and,
as BM25 terms, makes every table match every other table.

A table also often opens with its own name -- a course, a form, a module --
and that name is the only thing that says which entity the rows belong to.
"""

import re

_RULE = re.compile(r"^\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)*\|?\s*$")
_PLACEHOLDER = re.compile(r"^Col\d+$")
_BOLD = re.compile(r"\*{2,}")
_ITALIC = re.compile(r"(?<![\w_])_([^_\n]+?)_(?![\w_])")
_BREAK = re.compile(r"\s*<br\s*/?>\s*", re.IGNORECASE)
_SPACE = re.compile(r"[ \t]+")

# Row labels that name the entity a key-value table describes, and the ones
# that identify it. Bilingual because the documents are.
_NAME_KEY = re.compile(
    r"^(?:course|mata kuliah|module|modul|nama(?: mata kuliah)?|name|title|judul)\b",
    re.IGNORECASE,
)
_CODE_KEY = re.compile(r"^(?:code|kode)\b", re.IGNORECASE)
MAX_TITLE_CHARS = 100
MAX_SINGLE_CELL_TITLE = 60


def is_table_line(line: str) -> bool:
    return line.lstrip().startswith("|")


def split_cells(line: str) -> list[str]:
    inner = line.strip().removeprefix("|").removesuffix("|")
    return [cell.strip() for cell in inner.split("|")]


def _clean_cell(cell: str) -> str:
    cell = _BREAK.sub(" ", cell)
    cell = _BOLD.sub("", cell)
    cell = _ITALIC.sub(r"\1", cell)
    cell = _SPACE.sub(" ", cell).strip()
    return "" if _PLACEHOLDER.match(cell) else cell


def clean_row(line: str) -> str:
    """One table row as `a | b | c`, or "" when nothing in it is content."""
    cells = [_clean_cell(cell) for cell in split_cells(line)]
    # A merged cell is extracted once per column it spans.
    deduped = [
        cell
        for index, cell in enumerate(cells)
        if index == 0 or cell != cells[index - 1]
    ]
    kept = [cell for cell in deduped if cell]
    return f"| {' | '.join(kept)} |" if kept else ""


def clean_tables(text: str) -> str:
    """Strip rendering artefacts from table rows; prose lines pass through."""
    lines = []
    for line in text.splitlines():
        if not is_table_line(line):
            lines.append(line)
            continue
        if _RULE.match(line.strip()):
            continue
        row = clean_row(line)
        if row:
            lines.append(row)
    return "\n".join(lines)


def _looks_like_title(cell: str) -> bool:
    """A lone opening cell names the table only if it reads like a name.

    A wrapped sentence from the row above ends mid-clause; a name is short,
    capitalised and unpunctuated.
    """
    return (
        len(cell) <= MAX_SINGLE_CELL_TITLE
        and cell[:1].isupper()
        and not cell.endswith((".", ",", ";", ":"))
    )


def table_title(rows: list[str]) -> str:
    """The entity a table describes: its named row, else a one-cell opening row.

    The identifying code is appended, since questions ask by code as often as
    by name.
    """
    name = ""
    code = ""
    for row in rows:
        cells = split_cells(row)
        if len(cells) == 2 and cells[0] and cells[1]:
            if not name and _NAME_KEY.match(cells[0]):
                name = cells[1]
            elif not code and _CODE_KEY.match(cells[0]):
                code = cells[1]
    if not name and rows:
        cells = [cell for cell in split_cells(rows[0]) if cell]
        if len(cells) == 1 and _looks_like_title(cells[0]):
            name = cells[0]
    if not name or len(name) > MAX_TITLE_CHARS:
        return ""
    return f"{name} · {code}" if code and code not in name else name
