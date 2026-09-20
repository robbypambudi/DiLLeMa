"""One validated configuration boundary; prices are deployment inputs."""

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RoutingConfig(BaseModel):
    agentic_complexity_threshold: float = Field(0.65, ge=0, le=1)
    retrieval_confidence_threshold: float = Field(0.55, ge=0, le=1)
    coverage_threshold: float = Field(0.6, ge=0, le=1)
    long_query_words: int = Field(45, ge=5)
    conflict_overlap: float = Field(0.75, ge=0, le=1)
    max_subqueries: int = Field(4, ge=1, le=10)
    multiple_sources_min: int = Field(2, ge=2, le=10)


class Limits(BaseModel):
    max_agent_steps: int = Field(4, ge=1, le=20)
    max_retrieval_calls: int = Field(5, ge=1, le=20)
    max_llm_calls: int = Field(6, ge=1, le=10)
    max_input_tokens: int = Field(12000, ge=512)
    max_output_tokens: int = Field(768, ge=64)
    max_total_tokens: int = Field(20000, ge=1024)
    max_documents_per_step: int = Field(8, ge=1, le=30)
    max_evidence_documents: int = Field(16, ge=1, le=100)
    max_document_chars: int = Field(6000, ge=100, le=30000)
    max_answer_chars: int = Field(6000, ge=128)
    max_query_chars: int = Field(8000, ge=128, le=32000)
    max_no_progress_steps: int = Field(2, ge=1, le=10)
    timeout_ms: int = Field(15000, ge=50)


class LatencyConfig(BaseModel):
    direct_llm_target_ms: int = Field(3000, ge=10)
    rag_target_ms: int = Field(6000, ge=10)
    agentic_rag_target_ms: int = Field(12000, ge=10)
    global_request_timeout_ms: int = Field(15000, ge=50)
    generation_reserve_ms: int = Field(2000, ge=10)
    dependency_timeout_ms: int = Field(4000, ge=10)
    disconnect_poll_ms: int = Field(100, ge=10, le=1000)


class RetrievalConfig(BaseModel):
    top_k: int = Field(8, ge=1, le=30)
    candidates: int = Field(40, ge=1, le=200)
    rerank: bool = True
    min_rerank_score: float = Field(0.05, ge=0, le=1)
    retries: int = Field(1, ge=0, le=2)
    retry_backoff_ms: int = Field(100, ge=0, le=2000)
    vector_concurrency: int = Field(8, ge=1, le=64)
    embedding_concurrency: int = Field(1, ge=1, le=16)
    reranker_concurrency: int = Field(1, ge=1, le=16)
    llm_concurrency: int = Field(4, ge=1, le=64)
    db_concurrency: int = Field(4, ge=1, le=32)
    circuit_failures: int = Field(3, ge=1)
    circuit_cooldown_ms: int = Field(10000, ge=100)


class CacheConfig(BaseModel):
    embedding_entries: int = Field(128, ge=0, le=10000)
    embedding_ttl_seconds: float = Field(300, ge=0)
    normalized_query_entries: int = Field(128, ge=0, le=10000)
    # Evidence and collection metadata are request-local until index publication
    # provides a trustworthy generation/visibility version for invalidation.


class Pricing(BaseModel):
    input_per_million_usd: float | None = Field(None, ge=0)
    output_per_million_usd: float | None = Field(None, ge=0)
    embedding_call_usd: float | None = Field(None, ge=0)
    retrieval_operation_usd: float | None = Field(None, ge=0)
    reranker_operation_usd: float | None = Field(None, ge=0)


class AdaptiveConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ADAPTIVE_", env_nested_delimiter="__", extra="ignore"
    )
    routing: RoutingConfig = Field(default_factory=RoutingConfig)
    limits: Limits = Field(default_factory=Limits)
    latency: LatencyConfig = Field(default_factory=LatencyConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    pricing: Pricing = Field(default_factory=Pricing)
    content_logging: bool = False
    metrics_logging: bool = True
    metrics_enabled: bool = True
    max_inflight_requests: int = Field(32, ge=1, le=1000)

    @model_validator(mode="after")
    def coherent(self):
        if (
            self.limits.max_input_tokens + self.limits.max_output_tokens
            > self.limits.max_total_tokens
        ):
            raise ValueError("max_total_tokens must cover one input and output budget")
        if self.latency.generation_reserve_ms >= self.latency.global_request_timeout_ms:
            raise ValueError("generation reserve must be smaller than global timeout")
        return self
