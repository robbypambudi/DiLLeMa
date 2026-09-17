import json
from functools import cached_property
from uuid import UUID

from starlette.concurrency import run_in_threadpool
from loguru import logger

from agents.augment_query_generated import AugmentQueryGenerated
from app.core.config import settings
from app.models.questions import Questions
from app.repositories import CollectionsRepository
from app.repositories.questions_repository import QuestionsRepository
from app.schema.question_schema import CreateQuestion
from app.services.base_service import BaseService
from rag.qdrant.client import QdrantHttpClient


class QuestionsService(BaseService):
    """
    Question service class for handling question-related operations.
    """

    def __init__(
        self,
        questions_repository: QuestionsRepository,
        collections_repository: CollectionsRepository,
        qdrant_client: QdrantHttpClient,
        augment_query_generator: AugmentQueryGenerated,
        knowledge_repository=None,
        embedding_model=None,
        re_ranking=None,
        openai_chat=None,
    ) -> None:
        self.question_repository = questions_repository
        self.collections_repository = collections_repository
        self.qdrant_client = qdrant_client
        self.augment_query_generator = augment_query_generator
        self.knowledge_repository = knowledge_repository
        for name, value in (
            ("embedding_model", embedding_model),
            ("re_ranking", re_ranking),
            ("openai_chat", openai_chat),
        ):
            if value is not None:
                setattr(self, name, value)
        super().__init__(questions_repository)

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

    @cached_property
    def openai_chat(self):
        from rag.llm.chat_model import OpenAIChat

        return OpenAIChat(key="any")

    def _before_question(self, payload: CreateQuestion, using_augment_query=False):
        """
        Create a new question and answer pair.
        """
        # Get Collection Name
        collection = self.collections_repository.read_by_id(payload.collection_id)
        if not collection:
            raise ValueError(f"Collection with ID {payload.collection_id} not found.")

        if using_augment_query:
            quries = self.augment_query_generator.augment(payload.question_text)
        else:
            quries = [payload.question_text]

        candidates = {}
        seed_file_ids = set()
        for query in quries:
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

    def question_no_stream(self, payload: CreateQuestion):
        re_ranked_pairs = self._before_question(
            payload, using_augment_query=payload.using_augment_query
        )

        response = (
            self.openai_chat.chat(
                question=payload.question_text,
                context_pairs=re_ranked_pairs,
            )
            if re_ranked_pairs
            else "Maaf, saya tidak memiliki informasi yang cukup untuk menjawab pertanyaan ini."
        )
        response += self.openai_chat.format_sources(re_ranked_pairs)
        question = self.question_repository.create(
            Questions(
                question_id=payload.question_id,
                question_text=payload.question_text,
                answer=response,
                collection_id=payload.collection_id,
            )
        )
        return question

    async def question_stream(self, payload: CreateQuestion):
        """
        Stream the question and answer pairs.
        """
        try:
            re_ranked_pairs = await run_in_threadpool(
                self._before_question,
                payload,
                using_augment_query=payload.using_augment_query,
            )
            accumulated_answer = ""
            if re_ranked_pairs:
                async for chunk in self.openai_chat.chat_with_stream(
                    question=payload.question_text,
                    context_pairs=re_ranked_pairs,
                ):
                    if chunk:
                        accumulated_answer += chunk
                        yield {"data": chunk}
                sources = self.openai_chat.format_sources(re_ranked_pairs)
                if sources:
                    accumulated_answer += sources
                    yield {"data": sources}
            else:
                accumulated_answer = "Maaf, saya tidak memiliki informasi yang cukup untuk menjawab pertanyaan ini."
                yield {"data": accumulated_answer}

            self.question_repository.create(
                Questions(
                    question_id=payload.question_id,
                    question_text=payload.question_text,
                    answer=accumulated_answer,
                    collection_id=payload.collection_id,
                )
            )
        except Exception as e:
            logger.error(f"Error in question_stream: {str(e)}")
            yield {"data": "Could not generate an answer."}

    def clear_all(self):
        """
        Clear all questions from the database.
        """
        self.question_repository.clear_all()
