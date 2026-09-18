"""Page-aware text extraction for RAG indexing."""

import os
from pathlib import Path
from typing import NamedTuple

from loguru import logger

# PyMuPDF can drive Tesseract, which is not part of the runtime image. When it
# is absent the pages stay empty and are reported rather than silently dropped.
OCR_ENABLED = os.getenv("PDF_OCR", "true").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
OCR_LANGUAGE = os.getenv("PDF_OCR_LANGUAGE", "ind+eng")
OCR_DPI = int(os.getenv("PDF_OCR_DPI", "300"))


class Section(NamedTuple):
    """An indexable unit of a document.

    `page` is the physical page index the PDF viewer scrolls to; `page_label`
    is what is printed on that page. They diverge in every document with front
    matter, and citing the physical index there sends the reader to the wrong
    page of the document they are holding.
    """

    page: int | None
    section: str
    text: str
    page_label: str | None = None


def read_sections(path: str, mime: str) -> list[Section]:
    """Return (page, section, text) units. Empty PDF pages are skipped, not fatal."""
    suffix = Path(path).suffix.lower()
    mime = mime or ""
    if mime == "application/pdf" or suffix == ".pdf":
        return _pdf_sections(path)
    if suffix == ".docx" or "wordprocessingml" in mime:
        import pypandoc

        text = pypandoc.convert_file(path, "md")
        return _markdown_sections(text)
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    if suffix in {".md", ".markdown"} or mime == "text/markdown":
        return _markdown_sections(text)
    return [Section(None, "", text)]


def document_pages(path: str, mime: str) -> int | None:
    """Physical page count, so ingestion can report the pages it could not read."""
    suffix = Path(path).suffix.lower()
    if not (mime == "application/pdf" or suffix == ".pdf"):
        return None
    try:
        import pymupdf

        with pymupdf.open(path) as document:
            return document.page_count
    except Exception:
        try:
            from pypdf import PdfReader

            return len(PdfReader(path).pages)
        except Exception:  # pragma: no cover - unreadable file fails earlier
            return None


def _pdf_sections(path: str) -> list[Section]:
    """Layout-aware extraction, falling back to pypdf if PyMuPDF cannot read it."""
    try:
        import pymupdf
    except ImportError:  # pragma: no cover - PyMuPDF is a declared dependency
        logger.warning("PyMuPDF unavailable; extracting {} with pypdf", path)
        return _pypdf_sections(path)
    try:
        with pymupdf.open(path) as document:
            return _layout_sections(document, path)
    except Exception as exc:
        logger.warning(
            "PyMuPDF could not read {} ({}); falling back to pypdf",
            path,
            type(exc).__name__,
        )
        return _pypdf_sections(path)


def _layout_sections(document, path: str) -> list[Section]:
    sections: list[Section] = []
    empty: list[int] = []
    ocr_available = OCR_ENABLED
    for number, page in enumerate(document, 1):
        text = _page_text(page)
        if not text.strip() and ocr_available:
            text, ocr_available = _ocr_text(page)
        if text.strip():
            sections.append(Section(number, "", text, _page_label(page, number)))
        else:
            empty.append(number)
    if empty:
        # A scanned page that vanishes from the index is invisible at query
        # time: the answer is simply missing, with nothing to explain why.
        logger.warning(
            "{} of {} pages in {} hold no extractable text and were not indexed: {}",
            len(empty),
            document.page_count,
            path,
            empty[:20],
        )
    if not sections:
        raise ValueError(f"No extractable text in PDF: {path}")
    return sections


def _page_text(page) -> str:
    """Page text in reading order, with tables rendered instead of flattened.

    A table read line by line becomes a column of stray numbers that matches
    nothing; keeping its rows intact is what makes technical documents
    answerable.
    """
    try:
        tables = list(page.find_tables())
    except Exception:  # pragma: no cover - detection is best effort
        tables = []
    if not tables:
        return page.get_text("text", sort=True)

    boxes = [table.bbox for table in tables]
    parts: list[tuple[float, str]] = []
    for block in page.get_text("blocks", sort=True):
        x0, y0, x1, y1, text = block[0], block[1], block[2], block[3], block[4]
        middle = ((x0 + x1) / 2, (y0 + y1) / 2)
        if any(_inside(middle, box) for box in boxes):
            continue  # the table renders this text itself
        if text.strip():
            parts.append((y0, text))
    for table, box in zip(tables, boxes):
        rendered = _render_table(table)
        if rendered:
            parts.append((box[1], rendered))
    return "\n".join(text for _, text in sorted(parts, key=lambda part: part[0]))


def _inside(point, box) -> bool:
    return box[0] <= point[0] <= box[2] and box[1] <= point[1] <= box[3]


def _render_table(table) -> str:
    try:
        return table.to_markdown().strip()
    except Exception:
        pass
    try:
        rows = table.extract()
    except Exception:  # pragma: no cover - malformed table
        return ""
    lines = []
    for row in rows:
        cells = [str(cell or "").replace("\n", " ").strip() for cell in row]
        if any(cells):
            lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _page_label(page, number: int) -> str | None:
    try:
        label = page.get_label()
    except Exception:  # pragma: no cover - documents without a label tree
        return None
    return str(label) if label and str(label) != str(number) else None


def _ocr_text(page) -> tuple[str, bool]:
    """OCR one empty page. Returns the text and whether OCR is still usable."""
    try:
        textpage = page.get_textpage_ocr(
            language=OCR_LANGUAGE, dpi=OCR_DPI, full=True
        )
        return page.get_text("text", textpage=textpage), True
    except Exception as exc:
        logger.warning(
            "OCR unavailable ({}); scanned pages stay unindexed. Install Tesseract "
            "with the '{}' language data, or set PDF_OCR=false to stop trying.",
            type(exc).__name__,
            OCR_LANGUAGE,
        )
        return "", False


def _pypdf_sections(path: str) -> list[Section]:
    from pypdf import PdfReader

    reader = PdfReader(path)
    labels = _pypdf_labels(reader)
    sections = []
    for number, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ""
        if text.strip():
            sections.append(Section(number, "", text, labels.get(number)))
    if not sections:
        raise ValueError(f"No extractable text in PDF: {path}")
    return sections


def _pypdf_labels(reader) -> dict[int, str]:
    """Printed page labels by physical index, for the pages that have one.

    A label equal to the physical number carries no information, so it is left
    out and the citation falls back to the number it would have shown anyway.
    """
    try:
        labels = list(reader.page_labels)
    except Exception:  # pragma: no cover - malformed or unlabelled documents
        return {}
    return {
        number: str(label)
        for number, label in enumerate(labels, 1)
        if label and str(label) != str(number)
    }


def _markdown_sections(text: str) -> list[Section]:
    from knowledge.documents import markdown_sections

    parsed = markdown_sections(text)
    if parsed:
        return [Section(*unit) for unit in parsed]
    return [Section(None, "", text)] if text.strip() else []
