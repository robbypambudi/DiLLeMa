import html
import os
import re
from typing import List

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI
from loguru import logger

# OpenAI-compatible LLM endpoint (e.g. served by DiLLeMa). Configurable via env
# so the app is not pinned to a specific host/IP.
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:8000/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "any")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen-7b")
LLM_MAX_TOKENS = max(64, int(os.getenv("LLM_MAX_TOKENS", "768")))
LLM_MAX_CHARS = max(500, int(os.getenv("LLM_MAX_CHARS", "4000")))
LLM_MAX_LIST_ITEMS = max(3, int(os.getenv("LLM_MAX_LIST_ITEMS", "8")))

prompt = """
Kamu adalah chatbot interaktif bernama InformatikBot.
Jawab hanya dari bukti sumber. Jangan mengarang.

Tulis HTML dengan struktur ini, lalu berhenti:
<p>Ringkasan singkat.</p>
<ol>
<li><b>Judul:</b> satu fakta baru dari sumber.</li>
</ol>

Aturan:
- Paling banyak 6 <li>. Jangan mengulang judul atau kalimat yang sama.
- Jangan menulis angka 1. 2. 3. di dalam teks. Nomor dibuat oleh HTML.
- Jika tidak ada fakta baru, tutup </ol> dan berhenti.
- Jangan menulis daftar sumber.
"""

_ITEM_RE = re.compile(r"(?:<li\b|^\s*\d+\.\s)", re.I | re.M)
_TITLE_RE = re.compile(
    r"(?:^\s*\d+\.\s+|<li>\s*)(?:\*\*|<b>)?([^:<\n*]{6,80})",
    re.I | re.M,
)
_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")


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
            temperature=0.7,
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
        return str(meta.get("file_name") or "").strip()

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
            name = self._source_key(pair)
            index = labels.get(name, 1)
            context += f"[S{index}]\n{pair[1]}\n\n"
        context = context.strip()
        return messages + [
            HumanMessage(content=f"BUKTI SUMBER:\n{context}\n\nPERTANYAAN: {question}")
        ]

    @staticmethod
    def format_sources(context_pairs):
        """One footer row per source file. Chunks from the same PDF are not repeated."""
        files: dict[str, dict] = {}
        order: list[str] = []
        for pair in context_pairs:
            meta = pair[2] if len(pair) > 2 else {}
            name = str(meta.get("file_name") or "").strip()
            if not name:
                continue
            if name not in files:
                files[name] = {"pages": [], "quote": ""}
                order.append(name)
            entry = files[name]
            page = meta.get("page")
            if page is not None and page not in entry["pages"]:
                entry["pages"].append(page)
            quote = meta.get("quote") or ""
            if quote and not entry["quote"]:
                entry["quote"] = quote
        items = []
        for index, name in enumerate(order, 1):
            extra = files[name]
            location = ""
            if extra["pages"]:
                location = f", halaman {', '.join(str(page) for page in extra['pages'])}"
            label = html.escape(f"[S{index}] {name}{location}")
            excerpt = f" — {html.escape(extra['quote'][:350])}" if extra["quote"] else ""
            items.append(f"<li>{label}{excerpt}</li>")
        return (
            "<p><b>Sumber konteks:</b></p><ul>" + "".join(items) + "</ul>"
            if items
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
