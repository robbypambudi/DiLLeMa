"""Turn extracted document units into retrieval chunks.

Retrieval is only as good as what a chunk says about itself. Three things
decide that here:

- What a chunk belongs to. A page in the middle of a course module or a
  chapter carries no heading of its own, so the last heading or table title
  seen is carried forward and written into the chunk. The file name and page
  number are not: they are the same for every chunk of a file, and as index
  terms they match the whole document at once.
- What it contains. Running headers and footers, table rules and cell styling
  are removed before splitting, so they neither fill the window nor match.
- Where it is cut. Pages split on headings first, tables on row boundaries
  (repeating the header row), and fragments too short to stand on their own
  are folded into their neighbour.
"""

import hashlib
import json
import re

from langchain_text_splitters import RecursiveCharacterTextSplitter
from loguru import logger

from rag.nlp.boilerplate import strip_boilerplate
from rag.nlp.structure import split_structure
from rag.nlp.tables import clean_tables, is_table_line, split_cells, table_title

PAGE_TEXT_CHARS = 5000
QUOTE_CHARS = 350
CHUNK_SCHEMA_VERSION = "evidence-v2"


class DocumentChunker:
    """Split documents along page/section boundaries, then sentence-aware windows."""

    def __init__(
        self,
        chunk_size: int = 800,
        chunk_overlap: int = 120,
        min_chunk_chars: int = 150,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_chars = min_chunk_chars
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separators=["\n\n", "\n", ". ", ".", " "],
        )
        logger.info(
            "DocumentChunker initialized with chunk_size: {}, chunk_overlap: {}",
            self.chunk_size,
            self.chunk_overlap,
        )

    def chunk_text(self, text: str) -> list[str]:
        return self.text_splitter.split_text(text)

    def chunk_sections(
        self,
        sections: list,
        file_name: str = "",
    ) -> list[dict]:
        """Index leaf chunks with page metadata. Retrieve on the leaf, cite the page.

        `file_name` is accepted for callers that pass it, but deliberately not
        written into the chunk text.
        """
        units = [
            (unit[0], unit[1] or "", unit[2] or "", unit[3] if len(unit) > 3 else None)
            for unit in sections
        ]
        bodies = [clean_tables(text) for _, _, text, _ in units]
        # Furniture is only recognisable across pages, so the whole paginated
        # document is cleaned at once.
        if units and all(page is not None for page, *_ in units):
            bodies = strip_boilerplate(bodies)

        # Version the extracted document, not its file name. Offsets below are
        # Unicode character offsets in a cleaned unit, not PDF byte offsets.
        version = hashlib.sha256(
            json.dumps(units, ensure_ascii=False).encode()
        ).hexdigest()
        chunks: list[dict] = []
        carried = ""
        previous_outer = None
        for unit_index, ((page, outer, _, page_label), body) in enumerate(
            zip(units, bodies)
        ):
            # A new Markdown/DOCX section starts its own heading scope.
            if outer != previous_outer:
                carried = ""
                previous_outer = outer
            body = body.strip()
            if not body:
                continue
            pieces: list[tuple[str, str, str]] = []
            for heading, block in split_structure(body):
                heading = heading or carried
                title = self._block_title(block)
                if title:
                    heading = title
                carried = heading
                if not self._has_content(block):
                    continue
                section = " / ".join(part for part in (outer, heading) if part)
                for context, quote in self._split_block(block):
                    pieces.append((section, context, quote))
            parent_id = hashlib.sha256(f"{version}:{unit_index}".encode()).hexdigest()
            cursor = 0
            for piece_index, (section, context, quote) in enumerate(
                self._merge_small(pieces)
            ):
                # Splitting may change whitespace. Only publish offsets when
                # a contiguous span can be verified against canonical text.
                pattern = r"\s+".join(re.escape(word) for word in quote.split())
                match = re.compile(pattern).search(body, cursor) if pattern else None
                start, end = (match.start(), match.end()) if match else (None, None)
                evidence = body[start:end] if match else quote
                if match:
                    cursor = start + 1  # permit overlap, distinguish repeated passages
                window_start = (
                    max(0, start - max(0, PAGE_TEXT_CHARS - (end - start)) // 2)
                    if match
                    else 0
                )
                window_end = min(
                    len(body), window_start + max(PAGE_TEXT_CHARS, len(evidence))
                )
                window = body[window_start:window_end] if match else ""
                chunks.append(
                    {
                        "text": self._chunk_text(section, context, quote),
                        "page": page,
                        "page_label": page_label,
                        "section": section,
                        "quote": quote[:QUOTE_CHARS],
                        "page_text": body[:PAGE_TEXT_CHARS],
                        "chunk_schema_version": CHUNK_SCHEMA_VERSION,
                        "document_version": version,
                        "parent_id": parent_id,
                        "section_id": hashlib.sha256(
                            f"{parent_id}:{section}".encode()
                        ).hexdigest(),
                        "chunk_id": f"{parent_id}:{piece_index}",
                        "source_start": start,
                        "source_end": end,
                        "offset_basis": "cleaned_unit_unicode",
                        "evidence_text": evidence,
                        "evidence_context": context,
                        "parent_window": window,
                        "parent_window_start": window_start if match else None,
                    }
                )
        return chunks

    @staticmethod
    def _has_content(block: str) -> bool:
        """A heading line alone is a label, not a passage worth retrieving."""
        lines = [line for line in block.strip().splitlines() if line.strip()]
        return len(lines) > 1 or (bool(lines) and not split_structure(lines[0])[0][0])

    @staticmethod
    def _block_title(block: str) -> str:
        rows = [line for line in block.splitlines() if is_table_line(line)]
        return table_title(rows[:6]) if rows else ""

    @staticmethod
    def _chunk_text(section: str, context: str, quote: str) -> str:
        body = f"{context}\n{quote}" if context else quote
        first_line = body.lstrip().split("\n", 1)[0].strip()
        if not section or first_line == section:
            return body
        return f"{section}\n{body}"

    def _split_block(self, block: str) -> list[tuple[str, str]]:
        """(context, quote) pairs; context is a repeated table header, if any."""
        pieces: list[tuple[str, str]] = []
        for is_table, lines in self._runs(block):
            if is_table:
                pieces.extend(self._split_table(lines))
                continue
            text = "\n".join(lines).strip()
            if text:
                pieces.extend(("", piece.strip()) for piece in self.chunk_text(text))
        return [(context, quote) for context, quote in pieces if quote]

    @staticmethod
    def _runs(block: str) -> list[tuple[bool, list[str]]]:
        runs: list[tuple[bool, list[str]]] = []
        for line in block.splitlines():
            table = is_table_line(line)
            if runs and runs[-1][0] == table:
                runs[-1][1].append(line)
            else:
                runs.append((table, [line]))
        return runs

    @staticmethod
    def _is_group_row(row: str, columns: int) -> bool:
        """A one-cell row dividing a table into groups, like `| SEMESTER 3 |`.

        It names every row beneath it, so a cut that leaves it behind strands
        those rows: the courses of semester 3 become a list of courses of
        nothing, and no search for "semester 3" can reach them again.
        """
        cells = [cell for cell in split_cells(row) if cell.strip()]
        return columns >= 3 and len(cells) == 1

    def _split_table(self, rows: list[str]) -> list[tuple[str, str]]:
        """Cut between rows, never inside one; list tables repeat their header."""
        header = rows[0] if len(split_cells(rows[0])) >= 3 else ""
        columns = len(split_cells(header)) if header else 0
        body = rows[1:] if header else rows
        budget = self.chunk_size - len(header)
        groups: list[str] = []
        # The group row in force when each group started, so a cut that
        # separates rows from their group row can put it back.
        starts: list[str] = []
        group: list[str] = []
        size = 0
        divider = ""
        opened_with = ""
        for row in body:
            if group and size + len(row) + 1 > budget:
                groups.append("\n".join(group))
                starts.append(opened_with)
                group, size = [], 0
                opened_with = divider
            if self._is_group_row(row, columns):
                divider = row
            if len(row) > budget:
                # One oversized cell, e.g. a long description: split its text.
                groups.extend(self.chunk_text(row))
                continue
            group.append(row)
            size += len(row) + 1
        if group:
            groups.append("\n".join(group))
            starts.append(opened_with)
        if not header:
            return [("", quote) for quote in groups]
        if not groups:
            return [("", header)]

        def context_for(index: int) -> str:
            # Only a cut that stranded rows needs the group row put back. A
            # group whose own first row names its group already says so, and
            # labelling it with the previous group would be worse than silence.
            carried = starts[index] if index < len(starts) else ""
            first = next(
                (line for line in groups[index].splitlines() if line.strip()), ""
            )
            if not carried or self._is_group_row(first, columns):
                return header
            return f"{header}\n{carried}"

        # The first group reads the header as its own first row; later groups
        # carry it as context so their columns still have names.
        return [("", f"{header}\n{groups[0]}")] + [
            (context_for(index), quote) for index, quote in enumerate(groups[1:], 1)
        ]

    def _merge_small(
        self, pieces: list[tuple[str, str, str]]
    ) -> list[tuple[str, str, str]]:
        """Fold fragments too short to answer anything into a neighbour."""
        merged: list[tuple[str, str, str]] = []
        limit = self.chunk_size + self.min_chunk_chars
        for section, context, quote in pieces:
            if merged:
                last_section, last_context, last_quote = merged[-1]
                small = min(len(quote), len(last_quote)) < self.min_chunk_chars
                if (
                    small
                    and last_section == section
                    and len(last_quote) + len(quote) + 1 <= limit
                ):
                    merged[-1] = (last_section, last_context, f"{last_quote}\n{quote}")
                    continue
            merged.append((section, context, quote))
        return merged
