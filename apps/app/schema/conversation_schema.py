from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_serializer


class CreateConversation(BaseModel):
    collection_id: UUID


class HistoryTimestamps(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def serialize_utc(self, value: datetime) -> str:
        # SQLite omits timezone information; both database dialects store UTC.
        return value.replace(tzinfo=value.tzinfo or timezone.utc).isoformat()


class ConversationSummary(HistoryTimestamps):
    id: UUID
    collection_id: UUID | None
    collection_name: str
    title: str


class SourceSnippet(BaseModel):
    page: int | None = None
    page_label: str | None = None
    quote: str = ""


class SourceRef(BaseModel):
    """A cited document, as the chat panel needs it to open the original PDF."""

    index: int
    file_id: str | None = None
    file_name: str
    # Physical indices the viewer scrolls to, and the labels printed on those
    # pages, in the same order. Turns stored before labels existed have none.
    pages: list[int] = []
    page_labels: list[str | None] = []
    quote: str = ""
    snippets: list[SourceSnippet] = []


class ConversationTurn(HistoryTimestamps):
    id: UUID
    question_id: str
    sequence: int
    question_text: str
    answer: str
    sources: list[SourceRef] = []
    status: Literal["pending", "completed", "failed", "interrupted"]


class ConversationDetail(ConversationSummary):
    turns: list[ConversationTurn]


class ConversationList(BaseModel):
    data: list[ConversationSummary]
    total: int
