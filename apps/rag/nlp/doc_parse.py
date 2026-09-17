"""Page-aware text extraction for RAG indexing."""

from pathlib import Path


def read_sections(path: str, mime: str) -> list[tuple[int | None, str, str]]:
    """Return (page, section, text) units. Empty PDF pages are skipped, not fatal."""
    suffix = Path(path).suffix.lower()
    mime = mime or ""
    if mime == "application/pdf" or suffix == ".pdf":
        from pypdf import PdfReader

        sections = []
        for number, page in enumerate(PdfReader(path).pages, 1):
            text = page.extract_text() or ""
            if text.strip():
                sections.append((number, "", text))
        if not sections:
            raise ValueError(f"No extractable text in PDF: {path}")
        return sections
    if suffix == ".docx" or "wordprocessingml" in mime:
        import pypandoc

        text = pypandoc.convert_file(path, "md")
        return _markdown_sections(text)
    text = Path(path).read_text(encoding="utf-8")
    if suffix in {".md", ".markdown"} or mime == "text/markdown":
        return _markdown_sections(text)
    return [(None, "", text)]


def _markdown_sections(text: str) -> list[tuple[int | None, str, str]]:
    from knowledge.documents import markdown_sections

    parsed = markdown_sections(text)
    if parsed:
        return parsed
    return [(None, "", text)] if text.strip() else []
