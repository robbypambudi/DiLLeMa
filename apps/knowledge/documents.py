"""Page-aware baseline parser; preserves exact text for evidence verification."""

import hashlib
import json
import re
from importlib.metadata import version
from pathlib import Path
from uuid import UUID, uuid5

from knowledge.contracts import PIPELINE_VERSION, SourceChunk

PARSER_VERSION = "page-section-parser-2"


def markdown_sections(text: str) -> list[tuple[None, str, str]]:
    """Preserve exact Markdown while tracking headings outside fenced code."""
    sections = []
    headings = []
    start = offset = 0
    fence = None
    for line in text.splitlines(keepends=True):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if marker:
            value = marker.group(1)
            if fence is None:
                fence = value
            elif value[0] == fence[0] and len(value) >= len(fence):
                fence = None
        heading = (
            None
            if fence or marker
            else re.match(r"^ {0,3}(#{1,6})[ \t]+(.+?)\s*$", line)
        )
        if heading:
            if text[start:offset].strip():
                sections.append(
                    (
                        None,
                        " / ".join(title for _, title in headings),
                        text[start:offset],
                    )
                )
            level = len(heading.group(1))
            headings = [(depth, title) for depth, title in headings if depth < level]
            headings.append((level, re.sub(r"[ \t]+#+[ \t]*$", "", heading.group(2))))
            start = offset
        offset += len(line)
    if text[start:].strip():
        sections.append(
            (None, " / ".join(title for _, title in headings), text[start:])
        )
    return sections


def parser_provenance(path: str, mime: str) -> dict:
    """Version parser dependencies as well as our own transformations."""
    suffix = Path(path).suffix.lower()
    provenance = {"version": PARSER_VERSION}
    if mime == "application/pdf" or suffix == ".pdf":
        provenance.update(backend="pypdf", backend_version=version("pypdf"))
    elif suffix == ".docx" or "wordprocessingml" in mime:
        import pypandoc

        provenance.update(
            backend="pandoc", backend_version=str(pypandoc.get_pandoc_version())
        )
    else:
        provenance.update(backend="utf8")
    return provenance


def chunks_fingerprint(chunks: list[SourceChunk]) -> str:
    return hashlib.sha256(
        json.dumps(
            [chunk.model_dump(mode="json") for chunk in chunks], sort_keys=True
        ).encode()
    ).hexdigest()


def read_sections(path: str, mime: str) -> list[tuple[int | None, str, str]]:
    suffix = Path(path).suffix.lower()
    if mime == "application/pdf" or suffix == ".pdf":
        from pypdf import PdfReader

        sections = []
        for number, page in enumerate(PdfReader(path).pages, 1):
            text = page.extract_text() or ""
            if not text.strip():
                raise ValueError(
                    f"Page {number} has no extractable text; OCR is required before knowledge extraction"
                )
            sections.append((number, "", text))
        return sections
    if suffix == ".docx" or "wordprocessingml" in mime:
        import pypandoc

        # No implicit binary download: missing pandoc is an actionable job failure.
        text = pypandoc.convert_file(path, "md")
        return markdown_sections(text)
    else:
        text = Path(path).read_text(encoding="utf-8")
    if suffix in (".md", ".markdown") or mime == "text/markdown":
        return markdown_sections(text)
    return [(None, "document", text)]


def chunk_sections(
    sections: list[tuple[int | None, str, str]],
    file_id: UUID,
    content_hash: str,
    size: int = 2400,
    overlap: int = 240,
) -> list[SourceChunk]:
    if size < 100 or not 0 <= overlap < size:
        raise ValueError("Invalid chunk size/overlap")
    chunks = []
    for block, (page, section, text) in enumerate(sections):
        source_digest = hashlib.sha256(
            json.dumps([page, section, text], ensure_ascii=False).encode()
        ).hexdigest()
        start = 0
        while start < len(text):
            end = min(start + size, len(text))
            if end < len(text):
                for separator in ("\n\n", "\n", ". ", " "):
                    boundary = text.rfind(separator, start + size // 2, end)
                    if boundary >= 0:
                        end = boundary + len(separator)
                        break
            raw = text[start:end]
            left = len(raw) - len(raw.lstrip())
            body = raw.strip()
            if body:
                offset = start + left
                identity = f"{PIPELINE_VERSION}:{PARSER_VERSION}:{content_hash}:{source_digest}:{block}:{offset}:{offset + len(body)}"
                chunks.append(
                    SourceChunk(
                        id=uuid5(file_id, identity),
                        text=body,
                        page=page,
                        section=section,
                        ordinal=len(chunks),
                        start=offset,
                        end=offset + len(body),
                    )
                )
            if end == len(text):
                break
            start = max(start + 1, end - overlap)
    if not chunks:
        raise ValueError("Document has no extractable text")
    return chunks


def parse_document(path: str, mime: str, file_id: UUID, max_chunks: int = 200):
    content_hash = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    chunks = chunk_sections(read_sections(path, mime), file_id, content_hash)
    if len(chunks) > max_chunks:
        raise ValueError(
            f"Document exceeds extraction limit of {max_chunks} chunks; split it or raise KG_MAX_CHUNKS"
        )
    return content_hash, chunks
