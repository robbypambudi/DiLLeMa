import os
from typing import List, Dict, Generator

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI
from loguru import logger

# OpenAI-compatible LLM endpoint (e.g. served by DiLLeMa). Configurable via env
# so the app is not pinned to a specific host/IP.
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:8000/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "any")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen-7b")

prompt = """
Kamu adalah chatbot interaktif bernama InformatikBot.
Anda bertugas untuk memberikan jawaban yang relevan berdasarkan pengetahuan dari context yang telah diberikan.
Pengguna akan memberikan pertanyaan, berdasarkan informasi yang diambil dari buku petunjuk teknis.

**Instruksi:**
- Jika informasi tidak secara eksplisit menjawab pertanyaan, tapi masih relevan secara makna atau konteks, buatlah kesimpulan yang logis berdasarkan informasi yang ada.
- Jawablah pertanyaan pengguna **sebisa mungkin berdasarkan informasi yang diberikan.** Jika diperlukan, kamu boleh menggunakan pengetahuan tambahan selama masih relevan dan dapat dipercaya.
- Namun, jika informasi benar-benar tidak tersedia, barulah katakan: "Maaf, saya tidak memiliki informasi yang cukup untuk menjawab pertanyaan ini."

**Instruksi tambahan:**
- Tulis jawaban dalam format HTML agar mudah ditampilkan di halaman web.
- Gunakan tag HTML seperti `<ol>`, `<ul>`, `<li>` `<p>`, `<h3>`, `<h4>`, `<b`>, dan `<br>` untuk membuat penomoran dan poin yang rapi.
- Jika ada daftar bertingkat, gunakan struktur bertingkat HTML seperti:
  <ol>
    <li>Poin utama
      <ol type="a">
        <li>Sub-poin pertama</li>
        <li>Sub-poin kedua</li>
      </ol>
    </li>
  </ol>
- Tambahkan `<br>` jika diperlukan untuk kejelasan visual antar paragraf atau bagian.

Berikut adalah informasi yang diberikan:
"""


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
            temperature=0.7
        )
        self.output_parser = StrOutputParser()
        logger.info(f"OpenAIChat initialized with model: {model_name}")

    def _prepare_messages(self, question: str, context_pairs: list[list]) -> List:
        """
        Menyiapkan pesan untuk chat.

        Args:
            question (str): Pertanyaan dari pengguna
            context_pairs (List[Dict]): Daftar pasangan konteks (pertanyaan dan jawaban)

        Returns:
            List: Daftar pesan yang telah disiapkan
        """
        messages = [
            SystemMessage(content=prompt.strip()),
        ]

        # Menambahkan konteks dari pairs
        context = ""
        for pair in context_pairs:
            context += f"Q: {pair[0]}\nA: {pair[1]}\n\n"
        context = context.strip()

        return messages + [
            HumanMessage(content=f"{context}\n\nQ: {question}\nA:")
        ]

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

    async def chat_with_stream(self, question: str, context_pairs: List[list]):
        """
        Melakukan chat dengan mode streaming.

        Args:
            question (str): Pertanyaan dari pengguna
            context_pairs (List[list]): Daftar pasangan konteks

        Returns:
            Generator: Generator untuk streaming response
        """
        try:
            messages = self._prepare_messages(question, context_pairs)
            async for chunk in self.chat_model.astream(messages):
                if chunk.content:
                    processed_chunk = self.output_parser.parse(chunk.content)
                    yield processed_chunk
        except Exception as e:
            error_msg = f"Error in chat streaming: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)