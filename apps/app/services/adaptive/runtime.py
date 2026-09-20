"""Application-owned lifetime for the adaptive path, constructed lazily."""

from qdrant_client import AsyncQdrantClient

from app.core.config import settings
from rag.llm.chat_model import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL

from .adapters import HybridRetriever, LLMGenerator
from .config import AdaptiveConfig
from .orchestrator import AdaptiveAnswerService
from .resilience import BoundedWorker


class AdaptiveRuntime:
    def __init__(self, container, config=None, metrics=None):
        self.config = config or AdaptiveConfig()
        self.db = BoundedWorker(self.config.retrieval.db_concurrency)
        client = AsyncQdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
            timeout=self.config.latency.dependency_timeout_ms / 1000,
        )
        self.retriever = HybridRetriever(
            self.config, client, container.embedding_model, container.re_ranking
        )
        self.generator = LLMGenerator(self.config, LLM_BASE_URL, LLM_API_KEY, LLM_MODEL)
        self.service = AdaptiveAnswerService(
            self.config, self.retriever, self.generator, metrics
        )
        self.container = container

    async def close(self):
        self.db.close()
        try:
            await self.retriever.close()
        finally:
            await self.generator.close()
