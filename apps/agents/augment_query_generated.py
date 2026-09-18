import os
import re

from loguru import logger
from openai import OpenAI

# OpenAI-compatible LLM endpoint (e.g. served by DiLLeMa), configurable via env.
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:8000/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "any")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen-7b")

prompt = """
Anda adalah asisten ahli dalam menelusuri dokumen petunjuk teknis.
Untuk setiap pertanyaan dari pengguna, sarankan hingga lima pertanyaan tambahan yang relevan untuk membantu menemukan informasi yang dibutuhkan.
Setiap pertanyaan tambahan harus:
- Singkat dan langsung (tanpa kalimat majemuk)
- Hanya satu pertanyaan per baris (tanpa nomor atau tanda baca di depan)
- Beragam aspeknya, namun tetap berkaitan erat dengan pertanyaan awal
"""


class OpenAIClient:
    def __init__(self, api_key=None):
        # Prefer explicitly passed key, else the configured LLM_API_KEY.
        self.api_key = api_key or LLM_API_KEY
        self.client = OpenAI(
            base_url=LLM_BASE_URL,
            api_key=self.api_key
        )
        logger.info("OpenAI client initialized against {}".format(LLM_BASE_URL))


# Numbering, bullets and the "Berikut ..." preamble a small model wraps its
# list in. Left in, each one becomes a search that retrieves 20 unrelated chunks.
_ORNAMENT = re.compile(r"^\s*(?:[-*\u2022]|\d+[.)])\s*")
_PREAMBLE = re.compile(
    r"^\s*(?:berikut|berikut ini|pertanyaan tambahan|tentu|baik|semoga|catatan)\b",
    re.I,
)
MAX_EXTRA_QUERIES = 3
MIN_QUERY_CHARS = 15


def clean_queries(original: str, generated: str) -> list[str]:
    """The original question first, then the generated lines worth searching.

    A 7B model answers this prompt with a heading, numbering and the occasional
    apology. Only interrogative lines survive, deduplicated and capped: every
    extra query costs a full retrieval pass and widens the candidate pool the
    reranker has to sort out.
    """
    queries = [original]
    seen = {original.strip().lower()}
    for line in (generated or "").splitlines():
        candidate = _ORNAMENT.sub("", line).strip().strip('"')
        if len(candidate) < MIN_QUERY_CHARS or _PREAMBLE.match(candidate):
            continue
        if candidate.endswith(":") or "?" not in candidate:
            continue  # a heading or a statement, not a question to search with
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        queries.append(candidate)
        if len(queries) > MAX_EXTRA_QUERIES:
            break
    return queries


class AugmentQueryGenerated:
    def __init__(self, api_key):
        self.openai = OpenAIClient(api_key=api_key)

    def augment(self, query, model: str | None = None) -> list[str]:
        """
        Augment the given query using OpenAI's API.
        """
        model = model or LLM_MODEL
        try:
            response = self.openai.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": query}
                ],
                max_tokens=150,
                # Low enough that the model rephrases the question instead of
                # inventing a neighbouring topic.
                temperature=0.3,
            )
            generated = response.choices[0].message.content or ""
        except Exception as exc:
            # Augmentation is an optimisation; the question still has to be
            # answerable when the generator is down.
            logger.warning(
                "Query augmentation failed ({}); searching the original question only",
                type(exc).__name__,
            )
            return [query]
        queries = clean_queries(query, generated)
        logger.info("Augmented query into {} searches", len(queries))
        return queries
