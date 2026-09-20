"""One bounded control loop; planning/evaluation never call another LLM."""

import asyncio
import hashlib
import time

from .config import AdaptiveConfig
from .contracts import AgentState, AnswerRequest, AnswerResponse, Document, Strategy
from .generation import (
    ABSTENTION,
    DIRECT_FAILURE,
    fallback,
    messages_for,
    token_bound,
    validate,
)
from .resilience import BudgetExceeded, CircuitOpen, TTLCache
from .routing import analyze, evaluate, normalize, route, terms
from .telemetry import Metrics, Trace


class AdaptiveAnswerService:
    def __init__(
        self,
        config: AdaptiveConfig,
        retriever,
        generator,
        metrics: Metrics | None = None,
    ):
        self.config = config
        self.retriever = retriever
        self.generator = generator
        self.metrics = metrics or Metrics(config)
        self.inflight = asyncio.Semaphore(config.max_inflight_requests)
        self.normalized = TTLCache(
            config.cache.normalized_query_entries, config.cache.embedding_ttl_seconds
        )

    async def answer(
        self,
        request: AnswerRequest,
        *,
        collection_name: str = "",
        trace: Trace | None = None,
    ) -> AnswerResponse:
        trace = trace or Trace(self.config)
        state = AgentState(original_query=request.query, current_goal=request.query)
        analysis = analyze(request, self.config.routing)
        selected = route(analysis, request.options.force_strategy, self.config.routing)
        trace.route = trace.initial_route = selected.value
        trace.route_reason = analysis.reasons + (
            ["forced_strategy"] if request.options.force_strategy else []
        )
        response = (
            (DIRECT_FAILURE, []) if selected == Strategy.DIRECT else (ABSTENTION, [])
        )
        try:
            async with asyncio.timeout(trace.remaining_ms / 1000):
                async with self.inflight:
                    if len(request.query) > self.config.limits.max_query_chars:
                        raise BudgetExceeded("query_limit")
                    if selected != Strategy.DIRECT and (
                        not collection_name or not request.filters.collection_id
                    ):
                        trace.stop_reason = "collection_required"
                        trace.status = "abstained"
                        response = (
                            "Pilih koleksi dokumen untuk menjawab pertanyaan ini.",
                            [],
                        )
                    else:
                        response = await self._run(
                            request, collection_name, analysis, state, trace
                        )
        except asyncio.CancelledError:
            trace.status = "cancelled"
            trace.stop_reason = "client_cancelled"
            raise
        except Exception as exc:
            trace.error("request", isinstance(exc, TimeoutError))
            trace.fallback_count += 1
            trace.stop_reason = (
                "global_timeout"
                if isinstance(exc, TimeoutError)
                else (
                    "budget_exhausted"
                    if isinstance(exc, BudgetExceeded)
                    else "dependency_failure"
                )
            )
            response = (
                fallback(request.query, state.retrieved_evidence, self.config)
                if selected != Strategy.DIRECT
                else (DIRECT_FAILURE, [])
            )
            trace.status = "degraded" if response[1] else "abstained"
        finally:
            self.metrics.record(trace, request.query)
        return AnswerResponse(
            answer=response[0],
            strategy=Strategy(trace.route),
            sources=response[1],
            metadata=trace.snapshot(),
        )

    async def _retrieve(self, query, request, collection_name, trace, state, cache):
        key = hashlib.sha256(query.encode()).hexdigest()
        normalized = self.normalized.get(key)
        if normalized is None:
            normalized = normalize(query)
            self.normalized.put(key, normalized)
        if normalized in cache:
            trace.cache_hits += 1
            return []
        if trace.retrieval_calls >= self.config.limits.max_retrieval_calls:
            raise BudgetExceeded("retrieval_limit")
        if trace.remaining_ms <= self.config.latency.generation_reserve_ms:
            raise BudgetExceeded("generation_reserve")
        details = {"query": normalized} if self.config.content_logging else {}
        trace.event("retrieve", step=state.iteration, **details)
        before_calls = trace.retrieval_calls
        before_errors = trace.error_count
        before_latency = trace.retrieval_latency_ms
        began = time.monotonic()
        try:
            async with asyncio.timeout(
                min(
                    trace.remaining_ms - self.config.latency.generation_reserve_ms,
                    self.config.latency.dependency_timeout_ms,
                )
                / 1000
            ):
                docs = await self.retriever.retrieve(
                    normalized,
                    self.config.retrieval.top_k,
                    request.filters,
                    trace,
                    collection_name=collection_name,
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if trace.error_count == before_errors:
                trace.error("retrieval", isinstance(exc, TimeoutError))
            trace.fallback_count += 1
            raise
        finally:
            trace.retrieval_latency_ms = (
                before_latency + (time.monotonic() - began) * 1000
            )
            # Injected/future adapters must count attempts too; production
            # adapters additionally count every explicit retry.
            if trace.retrieval_calls == before_calls:
                trace.retrieval()
        # Typed parsing fences malformed adapters before they reach a prompt.
        docs = [Document.model_validate(d) for d in docs][
            : self.config.limits.max_documents_per_step
        ]
        allowed_files = {str(i) for i in request.filters.file_ids}
        docs = [
            d
            for d in docs
            if (not allowed_files or d.file_id in allowed_files)
            and (request.filters.page is None or d.page == request.filters.page)
        ]
        cache[normalized] = True
        trace.documents_retrieved += len(docs)
        ids = {d.id for d in state.retrieved_evidence}
        new = [
            d
            for d in docs
            if d.id not in ids and len(d.text) <= self.config.limits.max_document_chars
        ]
        capacity = self.config.limits.max_evidence_documents - len(
            state.retrieved_evidence
        )
        state.retrieved_evidence.extend(new[:capacity])
        trace.event(
            "retrieved",
            evidence_ids=[d.id for d in docs],
            new_documents=len(new[:capacity]),
        )
        return new[:capacity]

    async def _run(self, request, collection_name, analysis, state, trace):
        if trace.route == Strategy.DIRECT.value:
            return await self._generate(request, [], trace)
        cache = {}
        try:
            await self._retrieve(
                analysis.query, request, collection_name, trace, state, cache
            )
        except (BudgetExceeded, CircuitOpen):
            trace.stop_reason = "retrieval_unavailable_or_budget"
        except Exception:
            trace.stop_reason = "retrieval_unavailable"
        report = evaluate(
            analysis.query,
            analysis.goals,
            state.retrieved_evidence,
            self.config.routing,
        )
        if (
            report.sufficient
            and trace.route == Strategy.AGENTIC.value
            and request.options.force_strategy is None
        ):
            trace.route = Strategy.RAG.value
            trace.route_reason.append("single_pass_sufficient")
        if (
            not report.sufficient
            and trace.route == Strategy.RAG.value
            and request.options.force_strategy is None
            and not trace.stop_reason
        ):
            trace.escalated = True
            trace.route = Strategy.AGENTIC.value
            trace.route_reason.append("low_initial_retrieval_confidence")
        if (
            trace.route == Strategy.AGENTIC.value
            and not report.sufficient
            and not trace.stop_reason
        ):
            state.subqueries = list(
                dict.fromkeys(
                    analysis.goals + [" ".join(sorted(terms(analysis.query)))]
                )
            )
            queue = [
                g
                for g in state.subqueries
                if normalize(g).rstrip("?") != normalize(analysis.query).rstrip("?")
            ]
            agent_started = time.monotonic()
            no_progress = 0
            for goal in queue:
                if state.iteration >= self.config.limits.max_agent_steps:
                    trace.stop_reason = "max_agent_steps"
                    break
                elapsed = (time.monotonic() - trace.started) * 1000
                if (
                    elapsed + self.config.latency.generation_reserve_ms
                    >= self.config.latency.agentic_rag_target_ms
                    or (time.monotonic() - agent_started) * 1000
                    >= self.config.limits.timeout_ms
                ):
                    trace.stop_reason = "agent_latency_budget"
                    break
                state.iteration += 1
                trace.agent_steps = state.iteration
                state.current_goal = goal
                # A targeted search keeps the missing entity/clause, without
                # embedding all other entities into every decomposed query.
                try:
                    new = await self._retrieve(
                        goal, request, collection_name, trace, state, cache
                    )
                except Exception:
                    trace.stop_reason = "agent_dependency_or_budget"
                    break
                report = evaluate(
                    analysis.query,
                    analysis.goals,
                    state.retrieved_evidence,
                    self.config.routing,
                )
                state.remaining_questions = report.missing_information
                state.completed_steps.append(
                    {
                        "action": "retrieve",
                        "evidence_ids": [d.id for d in new],
                        "confidence": report.confidence,
                    }
                )
                trace.event(
                    "evaluate",
                    sufficient=report.sufficient,
                    confidence=report.confidence,
                    coverage=report.evidence_coverage,
                    potential_conflict=report.potential_conflict,
                )
                if report.sufficient:
                    trace.stop_reason = "sufficient_evidence"
                    break
                if not new:
                    no_progress += 1
                    if no_progress >= self.config.limits.max_no_progress_steps:
                        trace.stop_reason = "no_new_evidence"
                        break
                else:
                    no_progress = 0
            else:
                trace.stop_reason = "plan_exhausted"
        trace.retrieval_confidence = report.confidence
        trace.evidence_coverage = report.evidence_coverage
        trace.event(
            "evidence_decision",
            sufficient=report.sufficient,
            confidence=report.confidence,
            coverage=report.evidence_coverage,
            missing_goals=len(report.missing_information),
            potential_conflict=report.potential_conflict,
        )
        if not state.retrieved_evidence:
            trace.status = "abstained"
            trace.stop_reason = trace.stop_reason or "no_evidence"
            return ABSTENTION, []
        if not report.sufficient:
            # An LLM cannot repair insufficient/contradictory evidence. Preserve
            # the quotations and uncertainty without paying for another call.
            trace.fallback_count += 1
            trace.status = "degraded"
            return fallback(
                request.query,
                state.retrieved_evidence,
                self.config,
                report.potential_conflict,
            )
        return await self._generate(request, state.retrieved_evidence, trace)

    async def _generate(self, request, docs, trace):
        strategy = Strategy(trace.route)
        config = self.config
        selected = list(docs)
        messages = messages_for(request, strategy, selected)
        while selected and token_bound(messages) > config.limits.max_input_tokens:
            selected.pop()
            messages = messages_for(request, strategy, selected)
        if strategy != Strategy.DIRECT and not selected:
            trace.status = "abstained"
            return ABSTENTION, []
        inputs = token_bound(messages)
        outputs = min(
            config.limits.max_output_tokens,
            config.limits.max_total_tokens - trace.token_reservations - inputs,
        )
        if outputs <= 0 or inputs > config.limits.max_input_tokens:
            raise BudgetExceeded("input_budget")
        trace.reserve_llm(inputs, outputs)
        started = time.monotonic()
        target = {
            Strategy.DIRECT: config.latency.direct_llm_target_ms,
            Strategy.RAG: config.latency.rag_target_ms,
            Strategy.AGENTIC: config.latency.agentic_rag_target_ms,
        }[strategy]
        route_remaining = max(0, target - (started - trace.started) * 1000)
        try:
            async with asyncio.timeout(
                min(
                    trace.remaining_ms,
                    route_remaining,
                    config.latency.dependency_timeout_ms,
                )
                / 1000
            ):
                result = await self.generator.generate(messages, outputs)
            if result.input_tokens is not None and result.output_tokens is not None:
                trace.input_tokens += result.input_tokens - inputs
                trace.output_tokens += result.output_tokens - outputs
                trace.usage_estimated = False
            within_usage = (
                (result.output_tokens is None or result.output_tokens <= outputs)
                and (
                    result.input_tokens is None
                    or result.input_tokens <= config.limits.max_input_tokens
                )
                and trace.input_tokens + trace.output_tokens
                <= config.limits.max_total_tokens
            )
            checked = (
                validate(result.content, request, strategy, selected, config)
                if result.finish_reason == "stop" and within_usage
                else None
            )
            if checked is not None:
                trace.stop_reason = trace.stop_reason or "validated_answer"
                return checked
            trace.event("validation_failed", reason="unsupported_or_malformed_output")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            trace.error("llm", isinstance(exc, TimeoutError))
        finally:
            trace.generation_latency_ms += (time.monotonic() - started) * 1000
        trace.fallback_count += 1
        trace.status = "degraded" if selected else "abstained"
        trace.stop_reason = "generation_fallback"
        return (
            fallback(request.query, selected, config)
            if strategy != Strategy.DIRECT
            else (DIRECT_FAILURE, [])
        )
