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

    def rank(
        self, top_results: int = 3, pairs: list = None, min_score: float | None = None
    ) -> list:
        """Rank pairs, dropping any the cross-encoder scores below `min_score`.

        Scores are sigmoid outputs in 0..1. Without a floor, a question the
        corpus cannot answer still returns its least-bad chunks and the model
        answers from them; an empty result is what lets the caller say so.
        """
        if not pairs:
            raise ValueError("Pairs cannot be None or empty.")
        scores = self.model.predict([pair[:2] for pair in pairs])
        sorted_pairs = sorted(zip(scores, pairs), key=lambda x: x[0], reverse=True)
        if min_score is not None:
            sorted_pairs = [
                item for item in sorted_pairs if float(item[0]) >= min_score
            ]
        # The score travels with the evidence so packing can judge how far
        # below the best match a page falls.
        return [
            [*pair[:2], {**(pair[2] if len(pair) > 2 else {}), "rerank_score": float(score)}]
            for score, pair in sorted_pairs[:top_results]
        ]
