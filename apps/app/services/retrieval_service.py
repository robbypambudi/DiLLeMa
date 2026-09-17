"""Retrieve and rank source evidence independently of answer generation."""

import json
from functools import cached_property
from uuid import UUID

from loguru import logger

from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.schema.question_schema import CreateQuestion


class RetrievalService:
    def __init__(
        self,
        collections_repository,
        qdrant_client,
        augment_query_generator,
        knowledge_repository=None,
        embedding_model=None,
        re_ranking=None,
    ):
        self.collections_repository = collections_repository
        self.qdrant_client = qdrant_client
        self.augment_query_generator = augment_query_generator
        self.knowledge_repository = knowledge_repository
        if embedding_model is not None:
            self.embedding_model = embedding_model
        if re_ranking is not None:
            self.re_ranking = re_ranking

    @cached_property
    def embedding_model(self):
        from sentence_transformers import SentenceTransformer
        from rag.embedding.device import embedding_device

        return SentenceTransformer(
            "sentence-transformers/all-mpnet-base-v2", device=embedding_device()
        )

    @cached_property
    def re_ranking(self):
        from rag.llm.re_rank import ReRanking

        return ReRanking()

    def retrieve(self, payload: CreateQuestion, using_augment_query=False):
        """Combine vector and approved graph evidence, retaining source metadata."""
        collection = self.collections_repository.read_by_id(payload.collection_id)
        if not collection:
            raise NotFoundError(
                f"Collection with ID {payload.collection_id} not found."
            )

        if using_augment_query:
            queries = self.augment_query_generator.augment(payload.question_text)
        else:
            queries = [payload.question_text]

        candidates = {}
        seed_file_ids = set()
        for query in queries:
            query_embedding = self.embedding_model.encode(query)
            search_result = self.qdrant_client.client.search(
                collection_name=collection.vectordb_collection_name,
                query_vector=query_embedding.tolist(),
                limit=10,
            )
            for hit in search_result:
                metadata = hit.payload or {}
                text = metadata.get("document", "")
                if not text:
                    continue
                candidates.setdefault(
                    str(hit.id), [payload.question_text, text, metadata]
                )
                try:
                    seed_file_ids.add(UUID(str(metadata.get("file_id"))))
                except (ValueError, TypeError):
                    pass

        graph_used = False
        if settings.KG_ENABLED and self.knowledge_repository:
            try:
                evidence = self.knowledge_repository.retrieve(
                    payload.collection_id,
                    payload.question_text,
                    seed_file_ids,
                    limit=settings.KG_RETRIEVAL_LIMIT,
                )
                for item in evidence:
                    context = json.dumps(
                        {
                            "claim": item["statement"],
                            "qualifiers": item["qualifiers"],
                            "quote": item["quote"],
                            "source_text": item["text"],
                        },
                        ensure_ascii=False,
                    )
                    candidates["graph:" + str(item["id"])] = [
                        payload.question_text,
                        context,
                        {
                            "file_name": item["file_name"],
                            "page": item["page"],
                            "quote": item["quote"],
                            "claim_id": str(item["id"]),
                        },
                    ]
                graph_used = bool(evidence)
            except Exception as exc:
                logger.warning(
                    "Graph retrieval unavailable; using vector evidence ({})",
                    type(exc).__name__,
                )

        pairs = list(candidates.values())
        if not pairs:
            return []
        if using_augment_query or graph_used:
            return self.re_ranking.rank(pairs=pairs, top_results=6 if graph_used else 3)
        return pairs
