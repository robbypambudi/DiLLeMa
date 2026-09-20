import os

from loguru import logger
from sentence_transformers import CrossEncoder

from rag.embedding.device import embedding_device

DEFAULT_RERANK_MODEL = os.getenv(
    "RERANK_MODEL_NAME", "BAAI/bge-reranker-v2-m3"
)
# A small multilingual cross-encoder that prunes candidates before the large
# one scores them. Measured on CPU with real chunks and 40 candidates x 2
# phrasings: the 568M default manages ~3 pairs/s and takes 28.0s, pruning to
# 12 with a 118M model first takes 11.8s (2.4x), and with int8 as well 7.9s
# (3.5x). Answers found are identical at 12 and 20 (24/26 on the golden set,
# the same as scoring every candidate); 8 is where it starts costing recall.
# Empty disables it. Set RERANK_PREFILTER_MODEL=cross-encoder/mmarco-mMiniLMv2-L12-H384-v1
DEFAULT_PREFILTER_MODEL = os.getenv("RERANK_PREFILTER_MODEL", "").strip()
PREFILTER_KEEP = max(1, int(os.getenv("RERANK_PREFILTER_KEEP", "12")))
# Dynamic int8 on CPU: ~1.4x on its own, and it stacks with the prefilter.
# Ignored on GPU, where dynamic quantization does not apply.
QUANTIZE_ON_CPU = os.getenv("RERANK_QUANTIZE", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


class ReRanking:
    """Cross-encoder rerank. Default model is multilingual (Indonesian + English).

    Scores always come from the large model, including when a prefilter is
    configured: the prefilter only chooses which candidates are worth scoring.
    Every threshold in the pipeline (`RERANK_MIN_SCORE`, the relative floor,
    the scope gate) is calibrated against this model's 0..1 sigmoid output, and
    a smaller model's raw logits (measured at 2.0-8.3) would silently pass all
    of them.
    """

    def __init__(
        self,
        model_name: str | None = None,
        prefilter_model: str | None = None,
        prefilter_keep: int | None = None,
        quantize: bool | None = None,
    ):
        self.model_name = model_name or DEFAULT_RERANK_MODEL
        self.device = embedding_device()
        self.model = CrossEncoder(self.model_name, device=self.device)
        self.prefilter_model_name = (
            DEFAULT_PREFILTER_MODEL if prefilter_model is None else prefilter_model
        )
        self.prefilter_keep = prefilter_keep or PREFILTER_KEEP
        self._prefilter = None
        if QUANTIZE_ON_CPU if quantize is None else quantize:
            self._quantize()

    def _quantize(self) -> None:
        """Int8 the linear layers, on CPU only; a failure just leaves fp32."""
        if self.device != "cpu":
            return
        try:
            import torch

            self.model.model = torch.ao.quantization.quantize_dynamic(
                self.model.model, {torch.nn.Linear}, dtype=torch.qint8
            )
            logger.info("Reranker quantized to int8 for CPU inference")
        except Exception as exc:
            logger.warning(
                "Int8 quantization unavailable ({}); using full precision",
                type(exc).__name__,
            )

    @property
    def prefilter(self):
        """The small model, loaded on first use so nothing pays for it unused.

        Read defensively: tests build this class with `object.__new__` and set
        only `model`, and ranking must keep working for them.
        """
        self._prefilter = getattr(self, "_prefilter", None)
        self.prefilter_model_name = getattr(self, "prefilter_model_name", "")
        self.prefilter_keep = getattr(self, "prefilter_keep", PREFILTER_KEEP)
        self.device = getattr(self, "device", "cpu")
        if self._prefilter is None and self.prefilter_model_name:
            try:
                self._prefilter = CrossEncoder(
                    self.prefilter_model_name, device=self.device
                )
                logger.info("Rerank prefilter loaded: {}", self.prefilter_model_name)
            except Exception as exc:
                # Without it every candidate is scored by the large model,
                # which is slower but exactly the previous behaviour.
                logger.warning(
                    "Rerank prefilter unavailable ({}); scoring all candidates",
                    type(exc).__name__,
                )
                self.prefilter_model_name = ""
        return self._prefilter

    def rank(
        self,
        top_results: int = 3,
        pairs: list = None,
        min_score: float | None = None,
        queries: list[str] | None = None,
    ) -> list:
        """Rank pairs, dropping any the cross-encoder scores below `min_score`.

        Scores are sigmoid outputs in 0..1. Without a floor, a question the
        corpus cannot answer still returns its least-bad chunks and the model
        answers from them; an empty result is what lets the caller say so.

        With `queries` (the question and its rewrites), a passage is scored
        against each and keeps its best score: a page written in English is
        judged against the English rewrite that found it, not only against the
        Indonesian question it barely shares words with.
        """
        if not pairs:
            raise ValueError("Pairs cannot be None or empty.")
        pairs = self._prefiltered(pairs, queries)
        scores = self._scores(pairs, queries)
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

    def best_score(self, pairs: list, query: str | None = None) -> float:
        """The best relevance score in `pairs`, for a scope check before ranking.

        Scoring stops at the best match, so the caller can decide whether the
        corpus covers the question without paying for a full ranking pass.
        """
        if not pairs:
            return 0.0
        probe = [[query, pair[1]] for pair in pairs] if query else [pair[:2] for pair in pairs]
        return max(float(score) for score in self.model.predict(probe))

    def _prefiltered(self, pairs: list, queries: list[str] | None) -> list:
        """The candidates worth the large model's time, in their original order.

        A candidate is kept on its best score across the same phrasings the
        full ranking would use, so the prefilter cannot drop the page that only
        the English rewrite matches. Widening `prefilter_keep` trades speed for
        recall: at 12 the golden set loses one list-shaped question, at 20 it
        loses none.
        """
        if self.prefilter is None or len(pairs) <= self.prefilter_keep:
            return pairs
        variants = [query for query in dict.fromkeys(queries or []) if query]
        if not variants:
            scored = self.prefilter.predict([pair[:2] for pair in pairs])
        else:
            flat = self.prefilter.predict(
                [[query, pair[1]] for pair in pairs for query in variants]
            )
            width = len(variants)
            scored = [
                max(flat[index * width : (index + 1) * width])
                for index in range(len(pairs))
            ]
        keep = sorted(
            range(len(pairs)), key=lambda index: scored[index], reverse=True
        )[: self.prefilter_keep]
        return [pairs[index] for index in sorted(keep)]

    def _scores(self, pairs: list, queries: list[str] | None) -> list[float]:
        variants = [query for query in dict.fromkeys(queries or []) if query]
        if len(variants) < 2:
            return [float(score) for score in self.model.predict([pair[:2] for pair in pairs])]
        flat = self.model.predict(
            [[query, pair[1]] for pair in pairs for query in variants]
        )
        width = len(variants)
        return [
            float(max(flat[index * width : (index + 1) * width]))
            for index in range(len(pairs))
        ]
