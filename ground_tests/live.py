"""Run production chunking/retrieval/generation against an isolated fixed corpus.

The SQL collection lookup and legacy question sink are in-memory adapters. Qdrant
uses its embedded engine. No user collections, questions or conversations change.
"""

import asyncio
from importlib.metadata import version
import os
from time import perf_counter
from types import SimpleNamespace
from uuid import NAMESPACE_URL, uuid5


class CorpusCollection:
    def __init__(self, collection):
        self.collection = collection

    def read_by_id(self, collection_id):
        if collection_id != self.collection.id:
            raise ValueError("Unexpected evaluation collection")
        return self.collection


class QuestionSink:
    def create(self, question):
        return question


class EmptyApprovedGraph:
    def retrieve(self, *args, **kwargs):
        return []


class CapturedRetrieval:
    def __init__(self, service):
        self.service = service
        self.contexts = []

    def retrieve(self, *args, **kwargs):
        self.contexts = self.service.retrieve(*args, **kwargs)
        return self.contexts


class LiveRunner:
    def __init__(self, dataset, *, augment=True, timeout=120):
        # Configuration must load before modules with environment-derived defaults.
        from app.core.config import settings
        from agents.augment_query_generated import AugmentQueryGenerated
        from app.services.question_service import QuestionsService
        from app.services.retrieval_service import RetrievalService
        from qdrant_client import QdrantClient
        from rag.embedding.default_embedding import DefaultEmbedding
        from rag.embedding.device import embedding_device
        from rag.llm.chat_model import OpenAIChat, LLM_MODEL, LLM_MAX_TOKENS, prompt
        from rag.llm.re_rank import ReRanking
        from rag.nlp.doc_chunking import DocumentChunker
        from rag.qdrant.client import QdrantHttpClient
        from .protocol import digest

        self.vector = None
        self.augment = augment
        self.timeout = timeout
        self.dataset = dataset
        self.collection = SimpleNamespace(id=uuid5(NAMESPACE_URL, dataset["id"]), vectordb_collection_name="ground_test")
        self.configuration = {
            "embedding_model": settings.EMBED_MODEL_NAME,
            "rerank_model": settings.RERANK_MODEL_NAME,
            "llm_alias": LLM_MODEL,
            "declared_llm_source": os.getenv("LLM_MODEL_SOURCE", "unknown"),
            "llm_max_tokens": LLM_MAX_TOKENS,
            "prompt_sha256": digest(prompt),
            "query_augmentation": augment,
            "kg_enabled": settings.KG_ENABLED,
            "graph_fixture": "empty approved graph (graph extraction/retrieval quality not evaluated)",
            "vector_backend": "Qdrant embedded, hybrid collection created by production adapter",
            "generation_path": "QuestionsService.question_stream",
            "packages": {name: version(name) for name in ("qdrant-client", "sentence-transformers", "langchain-openai", "torch")},
        }
        try:
            device = embedding_device()
            embedding = DefaultEmbedding(device=device, model_name=settings.EMBED_MODEL_NAME)
            ranker = ReRanking(model_name=settings.RERANK_MODEL_NAME)
            self.configuration["embedding_device"] = device
            chat = OpenAIChat(key="any")
            chat.chat_model.request_timeout = timeout
            chat.chat_model.max_retries = 0
            augmenter = AugmentQueryGenerated(api_key=None)
            augmenter.openai.client = augmenter.openai.client.with_options(timeout=timeout, max_retries=0)
            self.configuration["sampling"] = {
                "temperature": chat.chat_model.temperature, "top_p": chat.chat_model.top_p,
                "extra_body": chat.chat_model.extra_body,
            }
            # Only the transport/storage backend is replaced; indexing/search code
            # is exactly the production Qdrant adapter, including dense+BM25 fusion.
            self.vector = QdrantHttpClient.__new__(QdrantHttpClient)
            self.vector.client = QdrantClient(location=":memory:")
            self.vector.create_collection("ground_test", vector_size=embedding.vector_size)
            chunker = DocumentChunker()
            self.configuration["chunking"] = {"size": chunker.chunk_size, "overlap": chunker.chunk_overlap}
            for document in dataset["documents"]:
                chunks = chunker.chunk_sections([(None, "", document["text"])], file_name=document["id"])
                self.vector.add_documents(
                    collection_name="ground_test",
                    ids=[f"{document['id']}:{index}" for index in range(len(chunks))],
                    documents=[item["text"] for item in chunks],
                    metadatas=[{"file_name": document["id"], "document_id": document["id"], "file_id": str(uuid5(NAMESPACE_URL, document["id"]))} for _ in chunks],
                    embedding_function=embedding.encode,
                )
            collections = CorpusCollection(self.collection)
            self.retrieval = CapturedRetrieval(RetrievalService(
                collections, self.vector, augmenter, EmptyApprovedGraph(), embedding, ranker,
            ))
            self.service = QuestionsService(
                QuestionSink(), collections, self.vector, augmenter,
                openai_chat=chat, retrieval_service=self.retrieval,
            )
        except BaseException:
            self.close()
            raise

    def predict(self, case, repeat):
        from app.schema.question_schema import CreateQuestion

        payload = CreateQuestion(
            question_id=f"ground:{case['id']}:{repeat}", question_text=case["question"],
            collection_id=self.collection.id, using_augment_query=self.augment,
        )
        self.retrieval.contexts = []
        start = perf_counter()
        answer = ""
        error = None

        async def generate():
            nonlocal answer
            async for item in self.service.question_stream(payload):
                answer += item["data"]

        try:
            asyncio.run(generate())
            if "Could not generate an answer." in answer:
                error = "Generation failed (see runtime logs)"
        except Exception as exc:
            # Do not copy connection strings, API keys or remote response bodies.
            error = type(exc).__name__
        return {
            "answer": answer,
            "contexts": [{"document_id": pair[2].get("document_id", pair[2].get("file_name", "")), "text": pair[1]} for pair in self.retrieval.contexts],
            "error": error, "latency_seconds": perf_counter() - start,
        }

    def close(self):
        if self.vector is not None:
            self.vector.client.close()
