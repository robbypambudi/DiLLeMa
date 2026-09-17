import os
from typing import List

import numpy as np
from loguru import logger
from sentence_transformers import SentenceTransformer

from rag.embedding import BaseEmbeddingModel

DEFAULT_EMBED_MODEL = os.getenv(
    "EMBED_MODEL_NAME", "intfloat/multilingual-e5-base"
)


class DefaultEmbedding(BaseEmbeddingModel):
    """Retrieval embedder. E5 models require query:/passage: prefixes and L2 norm."""

    def __init__(self, device: str = "cpu", model_name: str | None = None):
        self.model_name = model_name or DEFAULT_EMBED_MODEL
        logger.info("Initializing embedding model {}", self.model_name)
        self.model = SentenceTransformer(self.model_name, device=device)
        self.uses_e5_prefix = "e5" in self.model_name.lower()

    @property
    def vector_size(self) -> int:
        return int(self.model.get_sentence_embedding_dimension())

    def _prefix(self, texts: str | List[str], kind: str) -> str | List[str]:
        if not self.uses_e5_prefix:
            return texts
        tag = "query: " if kind == "query" else "passage: "
        if isinstance(texts, str):
            return texts if texts.startswith(tag) else tag + texts
        return [text if text.startswith(tag) else tag + text for text in texts]

    def encode(self, text: str | List[str]) -> np.ndarray:
        """String queries use the query prefix; lists of chunks use passage."""
        kind = "passage" if isinstance(text, (list, tuple)) else "query"
        vector = self.model.encode(
            self._prefix(text, kind),
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        return vector

    def encode_queries(self, texts: List[str]) -> np.ndarray:
        return self.model.encode(
            self._prefix(texts, "query"),
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
