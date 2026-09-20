import json
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from uuid import uuid4

from loguru import logger

from .config import AdaptiveConfig
from .resilience import BudgetExceeded


@dataclass
class Trace:
    config: AdaptiveConfig
    request_id: str = field(default_factory=lambda: str(uuid4()))
    started: float = field(default_factory=time.monotonic)
    route: str = "unrouted"
    initial_route: str = "unrouted"
    route_reason: list[str] = field(default_factory=list)
    status: str = "success"
    retrieval_calls: int = 0
    embedding_calls: int = 0
    reranker_operations: int = 0
    llm_calls: int = 0
    agent_steps: int = 0
    documents_retrieved: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    token_reservations: int = 0
    usage_estimated: bool = False
    retrieval_latency_ms: float = 0
    generation_latency_ms: float = 0
    latency_ms: float = 0
    retrieval_confidence: float = 0
    evidence_coverage: float = 0
    fallback_count: int = 0
    error_count: int = 0
    timeout_count: int = 0
    cache_hits: int = 0
    escalated: bool = False
    stop_reason: str = ""
    events: list[dict] = field(default_factory=list)

    @property
    def remaining_ms(self):
        return max(
            0,
            self.config.latency.global_request_timeout_ms
            - (time.monotonic() - self.started) * 1000,
        )

    def retrieval(self):
        if self.retrieval_calls >= self.config.limits.max_retrieval_calls:
            raise BudgetExceeded("retrieval_limit")
        self.retrieval_calls += 1

    def reserve_llm(self, inputs: int, outputs: int):
        limits = self.config.limits
        if (
            self.llm_calls >= limits.max_llm_calls
            or inputs > limits.max_input_tokens
            or outputs > limits.max_output_tokens
            or self.token_reservations + inputs + outputs > limits.max_total_tokens
        ):
            raise BudgetExceeded("token_or_llm_limit")
        self.llm_calls += 1
        self.token_reservations += inputs + outputs
        # On timeout the provider's usage is unknown; report the conservative
        # reservation rather than incorrectly claiming this call was free.
        self.input_tokens += inputs
        self.output_tokens += outputs
        self.usage_estimated = True

    def event(self, action: str, **data):
        self.events.append(
            {
                "action": action,
                "elapsed_ms": round((time.monotonic() - self.started) * 1000, 2),
                **data,
            }
        )

    def error(self, kind: str, timeout: bool = False):
        self.error_count += 1
        self.timeout_count += int(timeout)
        self.event("dependency_failure", dependency=kind, timeout=timeout)

    def snapshot(self) -> dict:
        self.latency_ms = (time.monotonic() - self.started) * 1000
        pricing = self.config.pricing
        charges = [
            (self.input_tokens / 1_000_000, pricing.input_per_million_usd),
            (self.output_tokens / 1_000_000, pricing.output_per_million_usd),
            (self.embedding_calls, pricing.embedding_call_usd),
            (self.retrieval_calls, pricing.retrieval_operation_usd),
            (self.reranker_operations, pricing.reranker_operation_usd),
        ]
        configured = all(price is not None for count, price in charges if count)
        data = {
            k: v
            for k, v in vars(self).items()
            if k not in {"config", "started", "events"}
        }
        data["estimated_cost_usd"] = (
            round(sum(count * (price or 0) for count, price in charges), 8)
            if configured
            else None
        )
        data["pricing_complete"] = configured
        targets = {
            "direct": self.config.latency.direct_llm_target_ms,
            "rag": self.config.latency.rag_target_ms,
            "agentic_rag": self.config.latency.agentic_rag_target_ms,
        }
        data["latency_target_ms"] = targets.get(self.route)
        data["latency_target_met"] = self.latency_ms <= targets.get(
            self.route, self.config.latency.global_request_timeout_ms
        )
        data["operations"] = self.events
        data["validation_mode"] = (
            "extractive_grounded" if self.route != "direct" else "direct_unverified"
        )
        return data


class Metrics:
    """Bounded-label Prometheus exposition, process-local; scrape each worker."""

    BUCKETS = (0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60)

    def __init__(self, config: AdaptiveConfig):
        self.config = config
        self.counts = Counter()
        self.histograms = defaultdict(lambda: [0] * (len(self.BUCKETS) + 2))

    def observe(self, name, route, value):
        h = self.histograms[(name, route)]
        for i, bound in enumerate(self.BUCKETS):
            h[i] += value <= bound
        h[-2] += 1
        h[-1] += value

    def record(self, trace: Trace, query: str = ""):
        data = trace.snapshot()
        if self.config.metrics_logging:
            record = dict(data)
            if self.config.content_logging:
                record["query"] = query
            logger.info("adaptive_request {}", json.dumps(record, ensure_ascii=False))
        if not self.config.metrics_enabled:
            return
        route = trace.route
        for name, value in {
            "request_count": 1,
            "retrieval_count": trace.retrieval_calls,
            "embedding_call_count": trace.embedding_calls,
            "reranker_operation_count": trace.reranker_operations,
            "llm_call_count": trace.llm_calls,
            "input_tokens": trace.input_tokens,
            "output_tokens": trace.output_tokens,
            "agent_steps": trace.agent_steps,
            "fallback_count": trace.fallback_count,
            "error_count": trace.error_count,
            "timeout_count": trace.timeout_count,
            "escalation_count": int(trace.escalated),
            "abstention_count": int(trace.status == "abstained"),
            "estimated_cost_usd": data["estimated_cost_usd"] or 0,
            "unknown_cost_count": int(data["estimated_cost_usd"] is None),
        }.items():
            self.counts[(name, route)] += value
        self.counts[("initial_route_count", trace.initial_route)] += 1
        for name, value in {
            "request_latency_seconds": trace.latency_ms / 1000,
            "retrieval_latency_seconds": trace.retrieval_latency_ms / 1000,
            "generation_latency_seconds": trace.generation_latency_ms / 1000,
            "retrieval_confidence": trace.retrieval_confidence,
        }.items():
            self.observe(name, route, value)

    def render(self):
        lines = []
        for (name, route), value in sorted(self.counts.items()):
            lines.append(f'adaptive_{name}_total{{route="{route}"}} {value}')
        for (name, route), hist in sorted(self.histograms.items()):
            for i, bound in enumerate(self.BUCKETS):
                lines.append(
                    f'adaptive_{name}_bucket{{route="{route}",le="{bound}"}} {hist[i]}'
                )
            lines.extend(
                [
                    f'adaptive_{name}_bucket{{route="{route}",le="+Inf"}} {hist[-2]}',
                    f'adaptive_{name}_count{{route="{route}"}} {hist[-2]}',
                    f'adaptive_{name}_sum{{route="{route}"}} {hist[-1]}',
                ]
            )
        return "\n".join(lines) + "\n"
