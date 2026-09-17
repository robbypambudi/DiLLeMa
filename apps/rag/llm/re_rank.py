import os

from sentence_transformers import CrossEncoder

from rag.embedding.device import embedding_device

DEFAULT_RERANK_MODEL = os.getenv(
    "RERANK_MODEL_NAME", "BAAI/bge-reranker-v2-m3"
)


class ReRanking:
    """Cross-encoder rerank. Default model is multilingual (Indonesian + English)."""

    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or DEFAULT_RERANK_MODEL
        self.model = CrossEncoder(self.model_name, device=embedding_device())

    def rank(self, top_results: int = 3, pairs: list = None) -> list:
        if not pairs:
            raise ValueError("Pairs cannot be None or empty.")
        scores = self.model.predict([pair[:2] for pair in pairs])
        sorted_pairs = sorted(zip(scores, pairs), key=lambda x: x[0], reverse=True)
        return [pair for _, pair in sorted_pairs[:top_results]]
