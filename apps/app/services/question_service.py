from functools import cached_property

from starlette.concurrency import run_in_threadpool
from loguru import logger

from agents.augment_query_generated import AugmentQueryGenerated
from app.models.questions import Questions
from app.repositories import CollectionsRepository
from app.repositories.questions_repository import QuestionsRepository
from app.schema.question_schema import CreateQuestion
from app.services.base_service import BaseService
from app.services.retrieval_service import RetrievalService
from rag.qdrant.client import QdrantHttpClient
from rag.llm.chat_model import OpenAIChat


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
        retrieval_service=None,
    ) -> None:
        self.question_repository = questions_repository
        self.retrieval_service = retrieval_service or RetrievalService(
            collections_repository,
            qdrant_client,
            augment_query_generator,
            knowledge_repository,
            embedding_model,
            re_ranking,
        )
        if openai_chat is not None:
            self.openai_chat = openai_chat
        super().__init__(questions_repository)

    @cached_property
    def openai_chat(self):
        from rag.llm.chat_model import OpenAIChat

        return OpenAIChat(key="any")

    def _before_question(self, payload: CreateQuestion, using_augment_query=False):
        return self.retrieval_service.retrieve(payload, using_augment_query)

    def _save_answer(self, payload: CreateQuestion, answer: str):
        return self.question_repository.create(
            Questions(
                question_id=payload.question_id,
                question_text=payload.question_text,
                answer=answer,
                collection_id=payload.collection_id,
            )
        )

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
        response = OpenAIChat.strip_source_footer(response)
        sources = self.openai_chat.format_sources(re_ranked_pairs)
        if sources:
            response += sources
        return self._save_answer(payload, response)

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
                had_footer = "sumber konteks" in accumulated_answer.lower()
                accumulated_answer = OpenAIChat.strip_source_footer(accumulated_answer)
                if sources:
                    accumulated_answer += sources
                    if not had_footer:
                        yield {"data": sources}
            else:
                accumulated_answer = "Maaf, saya tidak memiliki informasi yang cukup untuk menjawab pertanyaan ini."
                yield {"data": accumulated_answer}

            await run_in_threadpool(self._save_answer, payload, accumulated_answer)
        except Exception as e:
            logger.error(f"Error in question_stream: {str(e)}")
            yield {"data": "Could not generate an answer."}

    def clear_all(self):
        """
        Clear all questions from the database.
        """
        self.question_repository.clear_all()
