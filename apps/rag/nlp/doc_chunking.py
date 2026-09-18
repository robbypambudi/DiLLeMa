from langchain_text_splitters import RecursiveCharacterTextSplitter
from loguru import logger


class DocumentChunker:
    """Split documents along page/section boundaries, then sentence-aware windows."""

    def __init__(self, chunk_size: int = 800, chunk_overlap: int = 120):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
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
        """Index leaf chunks with page metadata. Retrieve on the leaf, cite the page."""
        chunks: list[dict] = []
        for unit in sections:
            page, section, text = unit[0], unit[1], unit[2]
            # Markdown and DOCX sections carry no printed page label.
            page_label = unit[3] if len(unit) > 3 else None
            body = (text or "").strip()
            if not body:
                continue
            for piece in self.text_splitter.split_text(body):
                quote = piece.strip()
                if not quote:
                    continue
                label_parts = [file_name] if file_name else []
                if page is not None:
                    label_parts.append(f"halaman {page_label or page}")
                if section:
                    label_parts.append(section)
                prefix = f"[{', '.join(label_parts)}]\n" if label_parts else ""
                chunks.append(
                    {
                        "text": f"{prefix}{quote}",
                        "page": page,
                        "page_label": page_label,
                        "section": section or "",
                        "quote": quote[:350],
                        "page_text": body[:5000],
                    }
                )
        return chunks
