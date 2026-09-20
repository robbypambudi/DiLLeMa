import asyncio
import json
import queue
from functools import cached_property
from uuid import UUID

import anyio

from starlette.concurrency import run_in_threadpool
from loguru import logger

from agents.augment_query_generated import AugmentQueryGenerated
from app.core.exceptions import UnauthorizedError
from app.models.users import Users
from app.repositories.conversations_repository import ConversationsRepository
from app.models.questions import Questions
from app.repositories import CollectionsRepository
from app.repositories.questions_repository import QuestionsRepository
from app.schema.question_schema import CreateQuestion
from app.services.base_service import BaseService
from app.services.retrieval_service import RetrievalService
from rag.qdrant.client import QdrantHttpClient
from rag.llm.chat_model import OpenAIChat

# How often the streaming turn looks for progress from the retrieval thread.
STAGE_POLL_SECONDS = 0.05


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
        conversations_repository: ConversationsRepository | None = None,
    ) -> None:
        self.question_repository = questions_repository
        self.conversations_repository = conversations_repository
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

    def _before_question(
        self, payload: CreateQuestion, using_augment_query=False, on_stage=None
    ):
        return self.retrieval_service.retrieve(payload, using_augment_query, on_stage)

    def start_turn(self, payload: CreateQuestion, user: Users | None) -> UUID | None:
        if payload.conversation_id is None:
            return None
        if user is None:
            raise UnauthorizedError()
        return self.conversations_repository.begin_turn(
            payload.conversation_id, user.id, payload
        )

    def _save_answer(
        self,
        payload: CreateQuestion,
        answer: str,
        turn_id: UUID | None = None,
        sources: list | None = None,
    ):
        question = Questions(
            question_id=payload.question_id,
            question_text=payload.question_text,
            answer=answer,
            collection_id=payload.collection_id,
        )
        if turn_id is not None:
            self.conversations_repository.finish_turn(
                turn_id, answer, "completed", sources or []
            )
            return question
        return self.question_repository.create(question)

    def question_no_stream(self, payload: CreateQuestion, turn_id: UUID | None = None):
        try:
            return self._question_no_stream(payload, turn_id)
        except Exception:
            if turn_id is not None:
                self.conversations_repository.finish_turn(
                    turn_id, "Could not generate an answer.", "failed"
                )
            raise

    def _question_no_stream(self, payload: CreateQuestion, turn_id: UUID | None):
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
        # Attribution reads the finished answer, so the footer is built from the
        # stripped text -- a model-written source list must not count as a citation.
        sources = self.openai_chat.source_items(re_ranked_pairs, response)
        footer = self.openai_chat.format_sources(re_ranked_pairs, response)
        if footer:
            response += footer
        return self._save_answer(payload, response, turn_id, sources)

    async def _retrieve_with_stages(self, payload: CreateQuestion):
        """Report retrieval progress while the blocking pipeline runs in a thread.

        Yields ``("stage", event)`` as each step starts and finally
        ``("evidence", pairs)``. The thread cannot reach the event loop, so
        stages travel through a queue the turn drains between polls.
        """
        stages: queue.SimpleQueue = queue.SimpleQueue()
        task = asyncio.ensure_future(
            run_in_threadpool(
                self._before_question,
                payload,
                payload.using_augment_query,
                lambda stage, **detail: stages.put({"stage": stage, "detail": detail}),
            )
        )
        try:
            while True:
                await asyncio.wait({task}, timeout=STAGE_POLL_SECONDS)
                while True:
                    try:
                        yield "stage", stages.get_nowait()
                    except queue.Empty:
                        break
                if task.done():
                    break
        finally:
            # A disconnected client stops the turn; the worker thread finishes
            # on its own, but nothing should await its result any more.
            if not task.done():
                task.cancel()
        yield "evidence", task.result()

    @staticmethod
    def _stage_event(stage: str, **detail):
        """A named SSE event, so progress never lands in the answer text."""
        return {
            "event": "status",
            "data": json.dumps({"stage": stage, "detail": detail}),
        }

    async def question_stream(
        self, payload: CreateQuestion, turn_id: UUID | None = None
    ):
        """
        Stream the question and answer pairs.
        """
        accumulated_answer = ""
        sources: list = []
        status = "interrupted"
        try:
            re_ranked_pairs = []
            async for kind, item in self._retrieve_with_stages(payload):
                if kind == "stage":
                    yield {
                        "event": "status",
                        "data": json.dumps(item, ensure_ascii=False),
                    }
                else:
                    re_ranked_pairs = item
            if re_ranked_pairs:
                yield self._stage_event("generating", documents=len(re_ranked_pairs))
                async for chunk in self.openai_chat.chat_with_stream(
                    question=payload.question_text,
                    context_pairs=re_ranked_pairs,
                ):
                    if chunk:
                        accumulated_answer += chunk
                        yield {"data": chunk}
                # The client lists the cited files itself, so a rendered footer
                # inside the answer would only repeat them.
                accumulated_answer = OpenAIChat.strip_source_footer(accumulated_answer)
                # Only the sources the finished answer cites, with quotes chosen
                # against what it claims.
                sources = self.openai_chat.source_items(
                    re_ranked_pairs, accumulated_answer
                )
                if not sources:
                    footer = self.openai_chat.format_sources(
                        re_ranked_pairs, accumulated_answer
                    )
                    if footer:
                        accumulated_answer += footer
                        yield {"data": footer}
                else:
                    # A named event keeps the citation metadata out of the answer
                    # text the client is concatenating.
                    yield {
                        "event": "sources",
                        "data": json.dumps(sources, ensure_ascii=False),
                    }
            else:
                accumulated_answer = "Maaf, saya tidak memiliki informasi yang cukup untuk menjawab pertanyaan ini."
                yield {"data": accumulated_answer}

            await run_in_threadpool(
                self._save_answer, payload, accumulated_answer, turn_id, sources
            )
            status = "completed"
        except Exception as e:
            logger.error(f"Error in question_stream: {str(e)}")
            status = "failed"
            accumulated_answer = accumulated_answer or "Could not generate an answer."
            yield {"data": "Could not generate an answer."}
        finally:
            if turn_id is not None and status != "completed":
                # Client disconnects cancel the stream. Preserve the question and
                # whatever answer arrived without letting cancellation abort saving.
                with anyio.CancelScope(shield=True):
                    await run_in_threadpool(
                        self.conversations_repository.finish_turn,
                        turn_id,
                        accumulated_answer,
                        status,
                        sources,
                    )

    def clear_all(self):
        """
        Clear all questions from the database.
        """
        self.question_repository.clear_all()
