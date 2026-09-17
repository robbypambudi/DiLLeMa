from contextlib import AbstractContextManager
from datetime import timedelta
from typing import Callable
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.models.collections import Collections
from app.models.conversations import Conversations, ConversationTurns, utcnow


class ConversationsRepository:
    def __init__(self, session_factory: Callable[..., AbstractContextManager[Session]]):
        self.session_factory = session_factory

    @staticmethod
    def _owned(session: Session, conversation_id: UUID, user_id: UUID, *, lock=False):
        query = session.query(Conversations).filter_by(
            id=conversation_id, user_id=user_id
        )
        if lock:
            query = query.with_for_update()
        conversation = query.first()
        if conversation is None:
            raise NotFoundError("Conversation not found")
        return conversation

    @staticmethod
    def _expire_pending(session: Session, conversation_id: UUID):
        session.query(ConversationTurns).filter(
            ConversationTurns.conversation_id == conversation_id,
            ConversationTurns.status == "pending",
            ConversationTurns.updated_at < utcnow() - timedelta(minutes=10),
        ).update({"status": "interrupted"}, synchronize_session=False)

    def create(self, user_id: UUID, collection_id: UUID) -> dict:
        with self.session_factory() as session:
            collection = session.get(Collections, collection_id)
            if collection is None:
                raise NotFoundError("Collection not found")
            conversation = Conversations(
                user_id=user_id,
                collection_id=collection_id,
                collection_name=collection.collection_name,
            )
            session.add(conversation)
            session.commit()
            session.refresh(conversation)
            return {**conversation.model_dump(), "turns": []}

    def list(self, user_id: UUID, offset: int, limit: int) -> dict:
        with self.session_factory() as session:
            query = session.query(Conversations).filter_by(user_id=user_id)
            total = query.count()
            rows = (
                query.order_by(Conversations.updated_at.desc(), Conversations.id.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            return {"data": [row.model_dump() for row in rows], "total": total}

    def get(self, conversation_id: UUID, user_id: UUID) -> dict:
        with self.session_factory() as session:
            conversation = self._owned(session, conversation_id, user_id)
            self._expire_pending(session, conversation_id)
            session.commit()
            session.refresh(conversation)
            turns = (
                session.query(ConversationTurns)
                .filter_by(conversation_id=conversation_id)
                .order_by(ConversationTurns.sequence)
                .all()
            )
            return {
                **conversation.model_dump(),
                "turns": [turn.model_dump() for turn in turns],
            }

    def delete(self, conversation_id: UUID, user_id: UUID) -> None:
        with self.session_factory() as session:
            conversation = self._owned(session, conversation_id, user_id, lock=True)
            session.query(ConversationTurns).filter_by(
                conversation_id=conversation_id
            ).delete(synchronize_session=False)
            session.delete(conversation)
            session.commit()

    def begin_turn(self, conversation_id: UUID, user_id: UUID, payload) -> UUID:
        with self.session_factory() as session:
            conversation = self._owned(session, conversation_id, user_id, lock=True)
            if conversation.collection_id != payload.collection_id:
                raise ConflictError(
                    "This conversation's collection is no longer available or does not match."
                )
            self._expire_pending(session, conversation_id)
            query = session.query(ConversationTurns).filter_by(
                conversation_id=conversation_id
            )
            if query.filter_by(question_id=payload.question_id).first():
                raise ConflictError("This question has already been submitted.")
            if query.filter_by(status="pending").first():
                raise ConflictError(
                    "An answer is still being generated for this conversation."
                )
            sequence = (
                session.query(func.max(ConversationTurns.sequence))
                .filter(ConversationTurns.conversation_id == conversation_id)
                .scalar()
                or 0
            )
            turn = ConversationTurns(
                conversation_id=conversation_id,
                sequence=sequence + 1,
                question_id=payload.question_id,
                question_text=payload.question_text,
            )
            session.add(turn)
            if sequence == 0:
                conversation.title = " ".join(payload.question_text.split())[:120]
            conversation.updated_at = utcnow()
            session.commit()
            session.refresh(turn)
            return turn.id

    def finish_turn(self, turn_id: UUID, answer: str, status: str) -> None:
        with self.session_factory() as session:
            conversation_id = (
                session.query(ConversationTurns.conversation_id)
                .filter_by(id=turn_id)
                .scalar()
            )
            if conversation_id is None:
                return
            # Match begin/delete's lock order: conversation first, then its turns.
            # Completion racing a deletion must not deadlock or recreate history.
            conversation = (
                session.query(Conversations)
                .filter_by(id=conversation_id)
                .with_for_update()
                .first()
            )
            if conversation is None:
                return
            turn = session.get(ConversationTurns, turn_id)
            if turn is None:
                return  # The owner may have deleted the conversation while streaming.
            if turn.status != "pending":
                return
            turn.answer = answer
            turn.status = status
            turn.updated_at = utcnow()
            conversation.updated_at = turn.updated_at
            session.commit()
