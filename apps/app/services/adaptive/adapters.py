"""Production boundaries with explicit calls, timeouts, filters and capacity."""

import asyncio
import hashlib
import math
import time

from openai import AsyncOpenAI
from qdrant_client import AsyncQdrantClient, models

from .config import AdaptiveConfig
from .contracts import Document, Filters, GenerationResult
from .resilience import (
    BoundedWorker,
    BudgetExceeded,
    CircuitBreaker,
    CircuitOpen,
    TTLCache,
)


class HybridRetriever:
    def __init__(
        self,
        config,
        client,
        embedding_provider,
        reranker_provider,
        embedding_worker=None,
        reranker_worker=None,
    ):
        self.config = config
        self.client = client
        self.embedding_provider = embedding_provider
        self.reranker_provider = reranker_provider
        self.embedding_worker = embedding_worker or BoundedWorker(
            config.retrieval.embedding_concurrency
        )
        self.reranker_worker = reranker_worker or BoundedWorker(
            config.retrieval.reranker_concurrency
        )
        self.vector_slots = asyncio.Semaphore(config.retrieval.vector_concurrency)
        self.breaker = CircuitBreaker(
            config.retrieval.circuit_failures, config.retrieval.circuit_cooldown_ms
        )
        self.embeddings = TTLCache(
            config.cache.embedding_entries, config.cache.embedding_ttl_seconds
        )

    async def retrieve(
        self,
        query: str,
        top_k: int,
        filters: Filters,
        trace,
        *,
        collection_name: str = "",
    ) -> list[Document]:
        if not collection_name or filters.collection_id is None:
            raise ValueError("A resolved collection is required")
        began = time.monotonic()
        cfg = self.config
        try:
            key = hashlib.sha256(
                (str(filters.collection_id) + "\0" + query).encode()
            ).hexdigest()
            vector = self.embeddings.get(key)
            if vector is None:
                trace.embedding_calls += 1
                async with asyncio.timeout(
                    min(trace.remaining_ms, cfg.latency.dependency_timeout_ms) / 1000
                ):
                    vector = await self.embedding_worker.run(
                        lambda: self.embedding_provider().encode(query)
                    )
                vector = vector.tolist() if hasattr(vector, "tolist") else vector
                self.embeddings.put(key, vector)
            else:
                trace.cache_hits += 1
            conditions = []
            if filters.file_ids:
                conditions.append(
                    models.FieldCondition(
                        key="file_id",
                        match=models.MatchAny(any=[str(i) for i in filters.file_ids]),
                    )
                )
            if filters.page is not None:
                conditions.append(
                    models.FieldCondition(
                        key="page", match=models.MatchValue(value=filters.page)
                    )
                )
            scope = models.Filter(must=conditions) if conditions else None
            hits = []
            sparse = None
            for attempt in range(cfg.retrieval.retries + 1):
                self.breaker.check()
                trace.retrieval()
                try:
                    async with asyncio.timeout(
                        min(trace.remaining_ms, cfg.latency.dependency_timeout_ms)
                        / 1000
                    ):
                        async with self.vector_slots:
                            # Request-local collection metadata: no stale layout or
                            # visibility is reused across a delete/reindex operation.
                            info = await self.client.get_collection(collection_name)
                            vectors = info.config.params.vectors
                            named = isinstance(vectors, dict) and "dense" in vectors
                            hybrid = named and "bm25" in (
                                info.config.params.sparse_vectors or {}
                            )
                            kwargs = dict(
                                collection_name=collection_name,
                                query_filter=scope,
                                limit=cfg.retrieval.candidates,
                                with_payload=True,
                                timeout=max(
                                    1,
                                    math.ceil(cfg.latency.dependency_timeout_ms / 1000),
                                ),
                            )
                            if hybrid:
                                from rag.embedding.sparse_bm25 import encode_sparse

                                if sparse is None:
                                    sparse = await self.embedding_worker.run(
                                        encode_sparse, query
                                    )

                                kwargs.update(
                                    prefetch=[
                                        models.Prefetch(
                                            query=vector,
                                            using="dense",
                                            filter=scope,
                                            limit=cfg.retrieval.candidates,
                                        ),
                                        models.Prefetch(
                                            query=sparse,
                                            using="bm25",
                                            filter=scope,
                                            limit=cfg.retrieval.candidates,
                                        ),
                                    ],
                                    query=models.FusionQuery(fusion=models.Fusion.RRF),
                                )
                            else:
                                kwargs.update(query=vector)
                                if named:
                                    kwargs["using"] = "dense"
                            hits = list(
                                (await self.client.query_points(**kwargs)).points
                            )
                    self.breaker.success()
                    break
                except (asyncio.CancelledError, BudgetExceeded):
                    raise
                except Exception as exc:
                    self.breaker.failure()
                    trace.error("vector", isinstance(exc, TimeoutError))
                    if attempt >= cfg.retrieval.retries:
                        raise
                    await asyncio.sleep(
                        cfg.retrieval.retry_backoff_ms * (2**attempt) / 1000
                    )
            documents = []
            for hit in hits:
                meta = hit.payload or {}
                # Defense in depth even if a replacement backend ignores filters.
                if filters.file_ids and str(meta.get("file_id")) not in {
                    str(i) for i in filters.file_ids
                }:
                    continue
                if filters.page is not None and meta.get("page") != filters.page:
                    continue
                text = str(
                    meta.get("evidence_text") or meta.get("document") or ""
                ).strip()
                # Never silently truncate evidence mid-condition to meet a cap.
                if not text or len(text) > cfg.limits.max_document_chars:
                    continue
                if not math.isfinite(float(hit.score)):
                    continue
                documents.append(
                    Document(
                        id=str(hit.id),
                        text=text,
                        file_id=str(meta.get("file_id") or ""),
                        file_name=str(meta.get("file_name") or "sumber"),
                        page=meta.get("page"),
                        section=str(meta.get("section") or ""),
                        context=str(meta.get("evidence_context") or "")[
                            : cfg.limits.max_document_chars
                        ],
                        document_version=str(meta.get("document_version") or ""),
                        score=float(hit.score),
                        score_kind="rrf" if hybrid else "cosine",
                    )
                )
            if documents and cfg.retrieval.rerank:
                trace.reranker_operations += 1
                try:
                    pairs = [[query, d.text, {"adaptive_id": d.id}] for d in documents]
                    async with asyncio.timeout(
                        min(trace.remaining_ms, cfg.latency.dependency_timeout_ms)
                        / 1000
                    ):
                        ranked = await self.reranker_worker.run(
                            lambda: self.reranker_provider().rank(
                                pairs=pairs,
                                top_results=top_k,
                                min_score=cfg.retrieval.min_rerank_score,
                            )
                        )
                    mapped = {d.id: d for d in documents}
                    documents = [
                        mapped[p[2]["adaptive_id"]].model_copy(
                            update={
                                "score": float(p[2]["rerank_score"]),
                                "score_kind": "reranker",
                            }
                        )
                        for p in ranked
                    ]
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    trace.error("reranker", isinstance(exc, TimeoutError))
                    trace.fallback_count += 1
                    trace.event("fallback", reason="unreranked_evidence")
            return documents[: min(top_k, cfg.limits.max_documents_per_step)]
        finally:
            trace.retrieval_latency_ms += (time.monotonic() - began) * 1000

    async def close(self):
        self.embedding_worker.close()
        self.reranker_worker.close()
        await self.client.close()


class LLMGenerator:
    def __init__(self, config: AdaptiveConfig, base_url: str, api_key: str, model: str):
        self.config = config
        self.model = model
        self.client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            max_retries=0,
            timeout=config.latency.dependency_timeout_ms / 1000,
        )
        self.slots = asyncio.Semaphore(config.retrieval.llm_concurrency)
        self.breaker = CircuitBreaker(
            config.retrieval.circuit_failures, config.retrieval.circuit_cooldown_ms
        )

    async def generate(self, messages, max_tokens):
        self.breaker.check()
        try:
            async with self.slots:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=0,
                    stream=False,
                )
            self.breaker.success()
        except asyncio.CancelledError:
            raise
        except Exception:
            self.breaker.failure()
            raise
        usage = response.usage
        return GenerationResult(
            content=response.choices[0].message.content or "",
            input_tokens=usage.prompt_tokens if usage else None,
            output_tokens=usage.completion_tokens if usage else None,
            finish_reason=response.choices[0].finish_reason or "stop",
        )

    async def close(self):
        await self.client.close()
