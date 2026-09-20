from enum import Enum
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Strategy(str, Enum):
    DIRECT = "direct"
    RAG = "rag"
    AGENTIC = "agentic_rag"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Filters(StrictModel):
    collection_id: UUID | None = None
    file_ids: list[UUID] = Field(default_factory=list, max_length=50)
    page: int | None = Field(None, ge=1)


class Options(StrictModel):
    force_strategy: Strategy | None = None


class AnswerRequest(StrictModel):
    query: str = Field(min_length=1, max_length=32000)
    # Explicit user-provided material makes self-contained transformations
    # unambiguous. It never comes from a retrieved document's instructions.
    text: str | None = Field(None, max_length=32000)
    conversation_id: UUID | None = None
    filters: Filters = Field(default_factory=Filters)
    options: Options = Field(default_factory=Options)

    @field_validator("query")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("query cannot be blank")
        return value.strip()


class Document(BaseModel):
    id: str
    text: str
    file_id: str = ""
    file_name: str = "sumber"
    page: int | None = None
    section: str = ""
    context: str = ""
    document_version: str = ""
    score: float = Field(0, allow_inf_nan=False)
    score_kind: Literal["reranker", "cosine", "rrf"] = "rrf"


class EvidenceEvaluation(BaseModel):
    sufficient: bool = False
    confidence: float = Field(0, ge=0, le=1)
    evidence_coverage: float = Field(0, ge=0, le=1)
    missing_information: list[str] = Field(default_factory=list)
    potential_conflict: bool = False
    next_action: Literal["retrieve", "answer", "stop"] = "retrieve"
    signals: dict[str, float] = Field(default_factory=dict)


class AgentState(BaseModel):
    original_query: str
    current_goal: str
    subqueries: list[str] = Field(default_factory=list)
    retrieved_evidence: list[Document] = Field(default_factory=list)
    completed_steps: list[dict] = Field(default_factory=list)
    remaining_questions: list[str] = Field(default_factory=list)
    iteration: int = 0


class Claim(StrictModel):
    text: str = Field(min_length=1, max_length=6000)
    source_ids: list[str] = Field(min_length=1, max_length=8)


class GroundedOutput(StrictModel):
    # The first slice deliberately uses extractive claims. Free paraphrases
    # cannot be proven supported by a deterministic overlap check.
    claims: list[Claim] = Field(default_factory=list, max_length=8)


class GenerationResult(BaseModel):
    content: str
    input_tokens: int | None = Field(None, ge=0)
    output_tokens: int | None = Field(None, ge=0)
    finish_reason: str = "stop"


class Source(BaseModel):
    id: str
    evidence_id: str
    file_id: str
    file_name: str
    page: int | None
    document_version: str
    quote: str
    context: str = ""


class AnswerResponse(BaseModel):
    answer: str
    strategy: Strategy
    sources: list[Source] = Field(default_factory=list)
    metadata: dict


class Retriever(Protocol):
    async def retrieve(
        self,
        query: str,
        top_k: int,
        filters: Filters,
        trace,
        *,
        collection_name: str = "",
    ) -> list[Document]: ...


class Generator(Protocol):
    async def generate(
        self, messages: list[dict], max_tokens: int
    ) -> GenerationResult: ...
