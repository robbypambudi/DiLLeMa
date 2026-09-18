import html
import os
import re
from typing import List

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI
from loguru import logger

from rag.nlp.quote_select import select_quote

# OpenAI-compatible LLM endpoint (e.g. served by DiLLeMa). Configurable via env
# so the app is not pinned to a specific host/IP.
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:8000/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "any")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen-7b")
LLM_MAX_TOKENS = max(64, int(os.getenv("LLM_MAX_TOKENS", "768")))
LLM_MAX_CHARS = max(500, int(os.getenv("LLM_MAX_CHARS", "4000")))
LLM_MAX_LIST_ITEMS = max(3, int(os.getenv("LLM_MAX_LIST_ITEMS", "8")))

prompt = """
Kamu menjawab pertanyaan pengguna hanya dari BUKTI SUMBER.
Jangan menambah fakta, angka, atau istilah yang tidak tertulis di bukti.

Tulis jawaban dalam Markdown dengan format ini:
Satu kalimat ringkas yang langsung menjawab pertanyaan.

- **<topik singkat>**: fakta dari bukti [S1]
- **<topik singkat>**: fakta dari bukti [S2]

Aturan:
- Ganti <topik singkat> dengan isi yang sebenarnya, jangan menulis kata "Judul" atau "Topik".
- Setiap butir satu baris, diawali "- ", tanpa sub-butir.
- Tulis label [S1], [S2], dst. di akhir butir; jangan menulis nama file, halaman, atau baris "Sumber".
- Jika bukti saling berbeda, sebutkan perbedaannya dalam butir terpisah.
- Jika bukti tidak cukup, tulis satu paragraf yang menyebut bagian mana yang tidak ada, lalu berhenti.
- Paling banyak 6 butir. Jangan mengulang. Jangan memakai HTML.
"""

_ITEM_RE = re.compile(r"(?:<li\b|^\s*(?:\d+\.|[-*])\s)", re.I | re.M)
_TITLE_RE = re.compile(
    r"(?:^\s*(?:\d+\.|[-*])\s+|<li>\s*)(?:\*\*|<b>)?([^:<\n*]{6,80})",
    re.I | re.M,
)
_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")
_CITATION_RE = re.compile(r"\[S(\d+)\]")
# One list item or paragraph is one claim; the marker inside it says which
# source that claim came from.
_BLOCK_RE = re.compile(r"</li>|</p>|<br\s*/?>|\n", re.I)


class OpenAIChat:
    """
    Class untuk mengelola interaksi chat dengan OpenAI API.
    """

    def __init__(self, key: str, model_name: str | None = None) -> None:
        """
        Inisialisasi OpenAIChat.

        Args:
            key (str): OpenAI API key
            model_name (str): Nama model OpenAI yang akan digunakan
        """
        model_name = model_name or LLM_MODEL
        self.chat_model = ChatOpenAI(
            base_url=LLM_BASE_URL,
            api_key=LLM_API_KEY or key,
            model=model_name,
            # Qwen + vLLM: default sampling is prone to repetition loops.
            # https://qwen.readthedocs.io/en/v2.0/deployment/vllm.html
            temperature=0.2,
            top_p=0.8,
            max_tokens=LLM_MAX_TOKENS,
            stop=["<|im_end|>", "<|endoftext|>"],
            extra_body={
                "repetition_penalty": 1.15,
                "stop_token_ids": [151643, 151645],
            },
            streaming=True,
        )
        self.output_parser = StrOutputParser()
        logger.info(f"OpenAIChat initialized with model: {model_name}")

    @staticmethod
    def _source_key(pair: list) -> str:
        meta = pair[2] if len(pair) > 2 else {}
        name = str(meta.get("file_name") or "").strip()
        if not name:
            return ""
        page = meta.get("page")
        claim = str(meta.get("claim_id") or "").strip()
        if claim:
            return f"{name}#c{claim}"
        if page is not None:
            return f"{name}#p{page}"
        return name

    def _source_labels(self, context_pairs: list[list]) -> dict[str, int]:
        labels: dict[str, int] = {}
        for pair in context_pairs:
            name = self._source_key(pair)
            if name and name not in labels:
                labels[name] = len(labels) + 1
        return labels

    def _prepare_messages(self, question: str, context_pairs: list[list]) -> List:
        messages = [
            SystemMessage(content=prompt.strip()),
        ]
        labels = self._source_labels(context_pairs)
        context = ""
        for pair in context_pairs:
            key = self._source_key(pair)
            index = labels.get(key, 1)
            meta = pair[2] if len(pair) > 2 else {}
            header = str(meta.get("file_name") or "sumber")
            if meta.get("page") is not None:
                header += f", halaman {meta['page']}"
            context += f"[S{index}] {header}\n{pair[1]}\n\n"
        context = context.strip()
        return messages + [
            HumanMessage(content=f"BUKTI SUMBER:\n{context}\n\nPERTANYAAN: {question}")
        ]

    @staticmethod
    def cited_indices(answer: str) -> set[int]:
        """The [Sn] markers the model actually wrote."""
        return {int(digits) for digits in _CITATION_RE.findall(answer or "")}

    @classmethod
    def cited_claims(cls, answer: str) -> dict[int, str]:
        """Per source label, the sentences that cite it.

        A quote is chosen against the claim that points at it, not against the
        whole answer, so a source cited for one number is not excerpted at the
        paragraph that happens to share the most words overall.
        """
        claims: dict[int, list[str]] = {}
        for block in _BLOCK_RE.split(answer or ""):
            for index in {int(digits) for digits in _CITATION_RE.findall(block)}:
                claims.setdefault(index, []).append(block)
        return {index: " ".join(blocks) for index, blocks in claims.items()}

    @classmethod
    def source_items(cls, context_pairs, answer: str | None = None) -> list[dict]:
        """One entry per cited file, numbered like the [Sn] labels in the prompt.

        The rendered footer cannot carry the file identity, so the frontend gets
        the ids and page-level quotes it needs to open the original PDF here.

        Passing the answer makes two things knowable that retrieval alone cannot
        decide: which sources the model actually used, and which sentence on the
        page backs what it wrote. Without it every retrieved page is reported as
        a source, so most of the citations a reader checks lead nowhere.
        """
        files: dict[str, dict] = {}
        order: list[str] = []
        for pair in context_pairs:
            meta = pair[2] if len(pair) > 2 else {}
            name = str(meta.get("file_name") or "").strip()
            key = cls._source_key(pair)
            if not name or not key:
                continue
            if key not in files:
                files[key] = {
                    "file_id": None,
                    "file_name": name,
                    "pages": [],
                    "labels": {},
                    "parents": {},
                    "snippets": [],
                }
                order.append(key)
            entry = files[key]
            file_id = str(meta.get("file_id") or "").strip()
            if file_id and not entry["file_id"]:
                entry["file_id"] = file_id
            page = meta.get("page")
            if page is not None and page not in entry["pages"]:
                entry["pages"].append(page)
            label = meta.get("page_label")
            if label:
                entry["labels"].setdefault(page, str(label))
            # The page the generator saw is where a supporting sentence can be
            # found; graph claims have none and keep their stored quote.
            parent = str(meta.get("page_text") or "").strip()
            if parent:
                entry["parents"].setdefault(page, parent)
            quote = (meta.get("quote") or "")[:350]
            if quote and all(
                snippet["quote"] != quote for snippet in entry["snippets"]
            ):
                entry["snippets"].append({"page": page, "quote": quote})

        claims = cls.cited_claims(answer) if answer else {}
        # An answer with no markers at all cannot be attributed, so only the
        # best-ranked source is reported rather than all of them.
        cited = set(claims) or {1} if answer else None

        items = []
        for index, key in enumerate(order, 1):
            if cited is not None and index not in cited:
                continue
            entry = files[key]
            claim = claims.get(index) or answer or ""
            snippets = [
                {
                    "page": snippet["page"],
                    "page_label": entry["labels"].get(snippet["page"]),
                    "quote": (
                        select_quote(
                            claim,
                            entry["parents"].get(snippet["page"], ""),
                            snippet["quote"],
                        )
                        if claim
                        else snippet["quote"]
                    ),
                }
                for snippet in entry["snippets"]
            ]
            items.append(
                {
                    "index": index,
                    "file_id": entry["file_id"],
                    "file_name": entry["file_name"],
                    "pages": entry["pages"],
                    # Aligned with `pages`: the viewer scrolls by physical index
                    # while the reader is told the number printed on the page.
                    "page_labels": [
                        entry["labels"].get(page) for page in entry["pages"]
                    ],
                    "quote": snippets[0]["quote"] if snippets else "",
                    "snippets": snippets,
                }
            )
        return items

    @staticmethod
    def _page_location(item: dict) -> str:
        pages = item.get("pages") or []
        if not pages:
            return ""
        labels = item.get("page_labels") or []
        shown = [
            str(labels[position] or page) if position < len(labels) else str(page)
            for position, page in enumerate(pages)
        ]
        return f", halaman {', '.join(shown)}"

    @classmethod
    def format_sources(cls, context_pairs, answer: str | None = None):
        """One footer row per source file. Chunks from the same PDF are not repeated."""
        rows = []
        for item in cls.source_items(context_pairs, answer):
            label = html.escape(f"[S{item['index']}] {item['file_name']}{cls._page_location(item)}")
            excerpt = f" \u2014 {html.escape(item['quote'])}" if item["quote"] else ""
            rows.append(f"<li>{label}{excerpt}</li>")
        return (
            "<p><b>Sumber konteks:</b></p><ul>" + "".join(rows) + "</ul>"
            if rows
            else ""
        )

    @staticmethod
    def strip_source_footer(text: str) -> str:
        """Drop a model-written source list so we can append a unique one."""
        if not text:
            return text
        match = re.search(r"(?:<p>\s*)?(?:<b>)?Sumber konteks\b", text, re.I)
        if not match:
            return text
        return text[: match.start()].rstrip()

    @staticmethod
    def _plain_text(text: str) -> str:
        return _SPACE_RE.sub(" ", _TAG_RE.sub(" ", text)).strip().lower()

    @classmethod
    def should_stop_generation(cls, text: str) -> bool:
        """True when the model is looping, listing too many items, or over length."""
        if len(text) >= LLM_MAX_CHARS:
            return True
        if len(_ITEM_RE.findall(text)) > LLM_MAX_LIST_ITEMS:
            return True
        titles = [
            _SPACE_RE.sub(" ", title).strip().lower()
            for title in _TITLE_RE.findall(text)
        ]
        if titles and titles[-1] in titles[:-1]:
            return True
        plain = cls._plain_text(text)
        if len(plain) < 180:
            return False
        window = 64
        haystack = plain[-2400:]
        unit = haystack[-window:]
        return haystack.count(unit) >= 3

    def chat(self, question: str, context_pairs: list[list]) -> str:
        """
        Melakukan chat dengan mode normal (non-streaming).

        Args:
            question (str): Pertanyaan dari pengguna
            context_pairs (str): Full answer dari model

        Returns:
            str: Jawaban dari model
        """
        try:
            messages = self._prepare_messages(question, context_pairs)
            response = self.chat_model.invoke(messages)
            answer = self.output_parser.parse(response.content)
            logger.info(f"Generated response for question: {question}")
            return answer
        except Exception as e:
            logger.error(f"Error in chat: {str(e)}")
            raise

    @staticmethod
    def _merge_stream_text(current: str, incoming: str) -> str:
        """Treat cumulative snapshots as replacements, not extra text."""
        if not incoming:
            return current
        if not current:
            return incoming
        if incoming.startswith(current):
            return incoming
        if current.endswith(incoming):
            return current
        return current + incoming

    def _chunk_text(self, content) -> str:
        if not content:
            return ""
        if isinstance(content, str):
            return self.output_parser.parse(content)
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    parts.append(item.get("text") or "")
                else:
                    parts.append(getattr(item, "text", "") or "")
            return self.output_parser.parse("".join(parts))
        return self.output_parser.parse(str(content))

    async def chat_with_stream(self, question: str, context_pairs: List[list]):
        try:
            messages = self._prepare_messages(question, context_pairs)
            assembled = ""
            async for chunk in self.chat_model.astream(messages):
                incoming = self._chunk_text(chunk.content)
                if not incoming:
                    continue
                merged = self._merge_stream_text(assembled, incoming)
                delta = merged[len(assembled) :]
                if self.should_stop_generation(merged):
                    logger.warning("Stopped generation after repetition or length cap")
                    break
                assembled = merged
                if delta:
                    yield delta
        except Exception as e:
            error_msg = f"Error in chat streaming: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)
