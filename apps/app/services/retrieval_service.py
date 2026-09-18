"""Retrieve and rank source evidence independently of answer generation."""

import json
from functools import cached_property
from uuid import UUID

from loguru import logger

from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.schema.question_schema import CreateQuestion

MAX_PAGES_FOR_GENERATOR = 4


def pack_parent_pages(pairs: list, max_pages: int = MAX_PAGES_FOR_GENERATOR) -> list:
    """Search on leaf chunks; send one parent page per hit to the generator."""
    packed = []
    seen = set()
    for pair in pairs:
        meta = dict(pair[2] if len(pair) > 2 else {})
        file_id = str(meta.get("file_id") or meta.get("file_name") or "")
        key = (file_id, meta.get("page"), meta.get("claim_id"))
        if key in seen:
            continue
        seen.add(key)
        parent = str(meta.get("page_text") or "").strip()
        quote = str(meta.get("quote") or "").strip()
        body = parent or str(pair[1] or "")
        if parent and quote and quote not in parent:
            body = f"{quote}\n\n{parent}"
        packed.append([pair[0], body, meta])
        if len(packed) >= max_pages:
            break
    return packed


def format_graph_evidence(item: dict) -> str:
    lines = [f"Klaim: {item.get('statement') or ''}"]
    qualifiers = item.get("qualifiers")
    if qualifiers:
        lines.append(f"Kualifikasi: {json.dumps(qualifiers, ensure_ascii=False)}")
    quote = item.get("quote") or ""
    if quote:
        lines.append(f"Kutipan: {quote}")
    source = item.get("text") or ""
    if source and source != quote:
        lines.append(f"Teks sumber: {source[:1200]}")
    return "\n".join(lines)


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
        from rag.embedding.default_embedding import DefaultEmbedding
        from rag.embedding.device import embedding_device

        return DefaultEmbedding(device=embedding_device())

    @cached_property
    def re_ranking(self):
        from rag.llm.re_rank import ReRanking

        return ReRanking()

    def retrieve(self, payload: CreateQuestion, using_augment_query=False):
        """Hybrid leaf retrieval, then parent-page packing for generation."""
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
            if hasattr(query_embedding, "ndim") and query_embedding.ndim > 1:
                query_embedding = query_embedding[0]
            search_result = self.qdrant_client.search(
                collection_name=collection.vectordb_collection_name,
                query_vector=query_embedding,
                query_text=query,
                limit=20,
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
                    candidates["graph:" + str(item["id"])] = [
                        payload.question_text,
                        format_graph_evidence(item),
                        {
                            "file_name": item["file_name"],
                            "file_id": str(item.get("file_id") or ""),
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
        ranked = self.re_ranking.rank(
            pairs=pairs,
            top_results=12 if graph_used else 8,
            min_score=settings.RERANK_MIN_SCORE,
        )
        if not ranked:
            logger.info(
                "No evidence cleared the relevance floor ({}) for collection {}",
                settings.RERANK_MIN_SCORE,
                payload.collection_id,
            )
            return []
        return pack_parent_pages(ranked)
