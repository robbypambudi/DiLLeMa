"""Private conversation history, independent of the legacy question log."""

from datetime import datetime, timezone
from uuid import UUID

import sqlalchemy as sa
from sqlmodel import Column, Field, JSON

from app.models import BaseModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Conversations(BaseModel, table=True):
    __tablename__ = "conversations"
    __table_args__ = (
        sa.Index("ix_conversations_user_updated", "user_id", "updated_at"),
    )

    user_id: UUID = Field(foreign_key="users.id", ondelete="CASCADE")
    collection_id: UUID | None = Field(
        default=None, foreign_key="collections.id", ondelete="SET NULL"
    )
    collection_name: str = Field(max_length=255)
    title: str = Field(default="New chat", max_length=120)
    created_at: datetime = Field(
        default_factory=utcnow, sa_type=sa.DateTime(timezone=True)
    )
    updated_at: datetime = Field(
        default_factory=utcnow, sa_type=sa.DateTime(timezone=True)
    )


class ConversationTurns(BaseModel, table=True):
    __tablename__ = "conversation_turns"
    __table_args__ = (
        sa.UniqueConstraint(
            "conversation_id", "question_id", name="uq_conversation_request"
        ),
        sa.UniqueConstraint(
            "conversation_id", "sequence", name="uq_conversation_sequence"
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'completed', 'failed', 'interrupted')",
            name="ck_conversation_turn_status",
        ),
    )

    conversation_id: UUID = Field(foreign_key="conversations.id", ondelete="CASCADE")
    question_id: str = Field(max_length=255)
    sequence: int
    question_text: str = Field(sa_type=sa.Text)
    answer: str = Field(default="", sa_type=sa.Text)
    # Cited files with page + quote, so a reopened chat can still open its PDFs.
    sources: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False, server_default="[]"))
    status: str = Field(default="pending", max_length=16)
    created_at: datetime = Field(
        default_factory=utcnow, sa_type=sa.DateTime(timezone=True)
    )
    updated_at: datetime = Field(
        default_factory=utcnow, sa_type=sa.DateTime(timezone=True)
    )
