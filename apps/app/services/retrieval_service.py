"""Retrieve and rank source evidence independently of answer generation."""

import json
from functools import cached_property
from uuid import UUID

from loguru import logger

from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.schema.question_schema import CreateQuestion
from app.services.scope_gate import trivial_reason
from rag.evidence import source_key

MAX_PAGES_FOR_GENERATOR = 4


def _ignore_stage(stage: str, **detail) -> None:
    """Default progress sink for callers that do not report retrieval stages."""


def _log_evidence_trace(payload, candidates, ranked, packed, reason):
    """Identifiers and scores only; never log document text or the question."""
    logger.info(
        "RAG evidence trace: {}",
        json.dumps(
            {
                "question_id": str(getattr(payload, "question_id", "")),
                "collection_id": str(payload.collection_id),
                "reason": reason,
                "candidate_count": len(candidates),
                "ranked": [
                    {
                        "chunk_id": p[2].get("chunk_id"),
                        "point_id": p[2].get("point_id"),
                        "file_id": p[2].get("file_id"),
                        "score": p[2].get("rerank_score"),
                    }
                    for p in ranked
                ],
                "packed": [
                    {
                        "file_id": p[2].get("file_id"),
                        "parent_id": p[2].get("parent_id"),
                        "document_version": p[2].get("document_version"),
                        "chunk_ids": p[2].get("evidence_chunk_ids", []),
                        "chars": len(p[1]),
                    }
                    for p in packed
                ],
            }
        ),
    )


def pack_parent_pages(pairs: list, max_pages: int = MAX_PAGES_FOR_GENERATOR) -> list:
    """Keep every retrieved leaf of selected parents, then add nearby context.

    The 5,000-character expansion budget is soft: an oversized evidence span
    is kept whole. Never trade away a matched leaf for the beginning of a page.
    """
    if max_pages <= 0:
        return []
    groups = {}
    for pair in pairs:
        key = source_key(pair)
        if key not in groups and len(groups) >= max_pages:
            continue
        groups.setdefault(key, []).append(pair)

    packed = []
    for group in groups.values():
        meta = dict(group[0][2] if len(group[0]) > 2 else {})
        parts = []
        windows = []
        spans = []
        citation_texts = []
        for pair in group:
            item = pair[2] if len(pair) > 2 else {}
            leaf = str(item.get("evidence_text") or pair[1] or "").strip()
            citation_texts.append(leaf)
            context = str(item.get("evidence_context") or "").strip()
            if context and context not in leaf:
                leaf = f"{context}\n{leaf}"
            # Claim formatting carries qualifiers and must not be replaced by
            # just its quotation or a neighbouring vector page.
            if item.get("claim_id"):
                leaf = str(pair[1] or "").strip()
            if leaf and not any(leaf in part for part in parts):
                parts = [part for part in parts if part not in leaf]
                parts.append(leaf)
            parent = str(
                item.get("parent_window") or item.get("page_text") or ""
            ).strip()
            if parent and not item.get("claim_id"):
                windows.append(parent)
                citation_texts.append(parent)
            spans.append(
                {
                    key: item.get(key)
                    for key in (
                        "chunk_id",
                        "section_id",
                        "source_start",
                        "source_end",
                        "offset_basis",
                    )
                }
            )
        for window in windows:
            expanded = [part for part in parts if part not in window]
            if any(window in part for part in expanded):
                continue
            # Source context precedes a detached leaf only when it contains
            # that leaf. Otherwise put the matched evidence first.
            candidate = expanded + [window]
            if len("\n\n".join(candidate)) <= 5000:
                parts = candidate
        body = "\n\n".join(parts)
        meta["evidence_spans"] = spans
        meta["evidence_chunk_ids"] = [s["chunk_id"] for s in spans if s["chunk_id"]]
        # Citation selection sees exactly the evidence the generator saw.
        # Keep canonical slices separate: table headers added to a late row
        # must not become one fictitious contiguous quotation.
        meta["citation_texts"] = list(
            dict.fromkeys(text for text in citation_texts if text and text in body)
        )
        packed.append([group[0][0], body, meta])
    return packed


def drop_weak_evidence(pairs: list, ratio: float) -> list:
    """Keep evidence scoring at least `ratio` of the best reranked match."""
    scores = [pair[2].get("rerank_score") for pair in pairs if len(pair) > 2]
    if not ratio or not scores or any(score is None for score in scores):
        return pairs
    floor = max(scores) * ratio
    return [pair for pair in pairs if pair[2]["rerank_score"] >= floor]


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

    def _search_into(self, candidates, seed_file_ids, collection, payload, query):
        """Add one query's hits to the shared candidate pool, deduplicated."""
        query_embedding = self.embedding_model.encode(query)
        if hasattr(query_embedding, "ndim") and query_embedding.ndim > 1:
            query_embedding = query_embedding[0]
        search_result = self.qdrant_client.search(
            collection_name=collection.vectordb_collection_name,
            query_vector=query_embedding,
            query_text=query,
            limit=settings.RETRIEVAL_CANDIDATES,
        )
        for hit in search_result:
            metadata = dict(hit.payload or {})
            metadata.setdefault("point_id", str(hit.id))
            text = metadata.get("document", "")
            if not text:
                continue
            candidates.setdefault(str(hit.id), [payload.question_text, text, metadata])
            try:
                seed_file_ids.add(UUID(str(metadata.get("file_id"))))
            except (ValueError, TypeError):
                pass

    def _in_scope(self, question: str, candidates: dict, report) -> bool:
        """Decide on evidence whether the corpus covers the question at all.

        Only the first `SCOPE_PROBE_CANDIDATES` hits are scored, against a
        floor below `RERANK_MIN_SCORE`: the probe must never reject what the
        full pipeline would have answered, so it settles the clear cases and
        leaves the borderline ones to the rerank that follows.

        Hits arrive in hybrid-fusion order, whose scores rank documents but do
        not measure relevance -- hence the cross-encoder, on a pool small
        enough that the saving is real.
        """
        probe = list(candidates.values())[: settings.SCOPE_PROBE_CANDIDATES]
        if not probe:
            report("out_of_scope", reason="empty_collection")
            return False
        report("checking", passages=len(probe))
        try:
            best = self.re_ranking.best_score(probe, question)
        except Exception as exc:
            # A probe that cannot run must not cost the user their answer.
            logger.warning(
                "Scope probe unavailable; continuing with full retrieval ({})",
                type(exc).__name__,
            )
            return True
        if best >= settings.SCOPE_GATE_MIN_SCORE:
            return True
        report("out_of_scope", reason="no_relevant_passage")
        logger.info(
            "Question rejected by scope probe (best {:.4f} < {})",
            best,
            settings.SCOPE_GATE_MIN_SCORE,
        )
        return False

    def retrieve(
        self,
        payload: CreateQuestion,
        using_augment_query: bool | None = False,
        on_stage=None,
    ):
        """Hybrid leaf retrieval, then parent-page packing for generation.

        `using_augment_query=None` defers to the `QUERY_AUGMENTATION` setting.
        `on_stage(stage, **counts)` reports progress while the work runs; it
        carries counts only, never document text or the question itself.
        """
        report = on_stage or _ignore_stage
        collection = self.collections_repository.read_by_id(payload.collection_id)
        if not collection:
            raise NotFoundError(
                f"Collection with ID {payload.collection_id} not found."
            )

        reason = trivial_reason(payload.question_text)
        if reason:
            # Nothing was spent: no embedding, no search, no rewrite call.
            report("out_of_scope", reason=reason)
            logger.info("Question rejected before retrieval ({})", reason)
            return []

        if using_augment_query is None:
            using_augment_query = settings.QUERY_AUGMENTATION

        candidates = {}
        seed_file_ids = set()
        # The question alone goes first. Its hits are what the scope probe
        # judges, and they stay in the pool, so a question that passes has
        # paid for one search it would have run anyway.
        report("searching", queries=1, collection=collection.collection_name)
        self._search_into(
            candidates, seed_file_ids, collection, payload, payload.question_text
        )

        if settings.SCOPE_GATE_ENABLED and not self._in_scope(
            payload.question_text, candidates, report
        ):
            return []

        queries = [payload.question_text]
        if using_augment_query:
            report("augmenting")
            queries = self.augment_query_generator.augment(payload.question_text)
            extra = [query for query in queries if query != payload.question_text]
            if extra:
                report(
                    "searching",
                    queries=len(extra),
                    collection=collection.collection_name,
                )
            for query in extra:
                self._search_into(candidates, seed_file_ids, collection, payload, query)

        graph_used = False
        if settings.KG_ENABLED and self.knowledge_repository:
            report("graph", candidates=len(candidates))
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
            _log_evidence_trace(payload, [], [], [], "no_candidates")
            report("no_evidence", candidates=0)
            return []
        # The question and its translation: keyword rewrites widen the search,
        # but scoring every candidate against every rewrite multiplies the
        # cross-encoder's work for little gain.
        rerank_options = {"queries": queries[:2]} if len(queries) > 1 else {}
        report("ranking", candidates=len(pairs), graph=int(graph_used))
        ranked = self.re_ranking.rank(
            pairs=pairs,
            top_results=12 if graph_used else 8,
            min_score=settings.RERANK_MIN_SCORE,
            **rerank_options,
        )
        if not ranked:
            _log_evidence_trace(payload, pairs, [], [], "below_relevance_floor")
            report("no_evidence", candidates=len(pairs))
            logger.info(
                "No evidence cleared the relevance floor ({}) for collection {}",
                settings.RERANK_MIN_SCORE,
                payload.collection_id,
            )
            return []
        report("reading", passages=len(ranked))
        packed = pack_parent_pages(
            drop_weak_evidence(ranked, settings.RERANK_RELATIVE_FLOOR)
        )
        _log_evidence_trace(payload, pairs, ranked, packed, "packed")
        return packed
