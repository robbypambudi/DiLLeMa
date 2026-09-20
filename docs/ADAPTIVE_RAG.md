# Adaptive RAG: first production slice

## Existing architecture and implementation decision

The dashboard is FastAPI (`apps/app`) with dependency-injector, SQLAlchemy
repositories, Qdrant dense/sparse RRF, SentenceTransformer embeddings, a
CrossEncoder reranker, parent evidence packing, and an OpenAI-compatible LLM.
`QuestionsService` also owns legacy streaming, local replies and conversation
history. Collections are shared by this application's users; conversations are
owner-scoped. There is no per-collection tenant ACL in the current data model.

Reusable: ingestion/index schema, sparse encoding, embedding and reranker model
providers, evidence identity, prompt assembly, and authentication/repositories.
Relevant debt: synchronous dependencies, implicit retrieval/rewrite calls,
unbounded SDK retries/default timeouts, uncalibrated cross-corpus confidence,
and streamed claims that cannot be validated before delivery. Sparse scoring is
TF with Qdrant IDF, not length-normalized BM25. An index version/atomic publication
contract is still needed before persistent retrieval or answer caching is safe.

The smallest addition is one service package, `app/services/adaptive`, with typed
contracts, deterministic routing/planning/evaluation, async retrieval and model
adapters, a bounded orchestrator, validator, and operational telemetry. No agent
framework, tool execution, router LLM, or LLM-based evaluator is required.

Implementation order: contracts/configuration and budgets; retrieval/model
adapters; routing and escalation; validation/fallback; authenticated endpoint
and metrics; failure-path/integration tests and a reproducible load harness.

`POST /v1/answer` will support direct generation, single-pass RAG and a bounded
retrieval loop. Default routing is conservative: unknown/factual questions use
RAG; direct generation is reserved for recognizable self-contained tasks.
Planner decisions are structured actions, never chain-of-thought. Low confidence
can escalate once; exhausted loops return available evidence or abstain.

The existing dashboard endpoints remain compatible. This slice provides a new
deployment path rather than changing the behavior of every existing chat client.

Dependency guidance: [Qdrant async client](https://github.com/qdrant/qdrant-client)
supports async filtered retrieval; [Python task cancellation](https://docs.python.org/3.12/library/asyncio-task.html)
provides deadlines for awaitable operations. Cancellation does not stop native
inference already executing in a worker thread; capacity must remain reserved
until that work actually ends.

## Implemented slice

| Component | Implementation |
| --- | --- |
| Router | English/Indonesian deterministic self-contained-task, comparison, multi-source, aggregation, length and temporal signals |
| Conventional RAG | One collection-scoped hybrid/dense retrieval, optional existing reranker, context budget, one generation call |
| Agentic RAG | Original search, deterministic clause/entity decomposition and keyword rewrite, incremental evidence evaluation, bounded additional searches |
| Escalation | Weak initial confidence/coverage or possible conflict escalates RAG; sufficient single-pass evidence can downgrade a predicted agentic route to RAG |
| Validation | Typed generated claims, valid source labels, exact complete-paragraph containment, query/goal coverage heuristic, output limits |
| Fallback | Cited, complete evidence paragraphs or explicit abstention; no generated paraphrase is silently treated as verified |
| Observability | Structured request trace, operation counters, timings, provider usage/reservations, configured cost, Prometheus exposition |
| Cache | Bounded TTL embedding and normalized-query caches; request-local retrieval deduplication; no final-answer cache |

This is an extractive first release. It can retrieve across sources and present
their supported passages, but does not claim to solve arbitrary implicit
multi-hop entity reasoning. No LLM is used to plan, route, or judge evidence.
Usually there is at most one generation call; insufficient evidence skips it.
There is no tool execution or external web/SQL access in this slice. Future
retrievers implement the typed `Retriever` protocol and must preserve scope,
count retries, honor cancellation and report their operations.

The confidence score is a heuristic in `[0,1]`, not a probability of truth.
It combines top/mean reranker relevance and lexical coverage, penalizes duplicate
evidence, and exposes source diversity/score gap separately. Cosine scores are
mapped to `[0,1]`; RRF magnitudes are never interpreted as probabilities. Numeric
and explicit-negation disagreements flag *possible* conflicts; disjoint explicit
years are handled as different periods. These rules require corpus calibration
and do not replace semantic review. Document truth, current applicability and
omitted qualifications outside the indexed chunk are not established by exact
quotation. Direct responses are explicitly marked `direct_unverified`.

## API and scope

Start the existing application (`app.main:app` on port 8080). The new JSON endpoint
is `/v1/answer`, separate from the legacy `/api/v1/questions` form/SSE endpoints.
It requires the existing bearer authentication. Collections follow the existing
shared-collection model; this is **not a new multi-tenant ACL system**. Requests
can restrict a collection further using file IDs and physical page. Unsupported
filter fields return 422, rather than being silently ignored.

```json
{
  "query": "Compare product A and product B based on our documentation",
  "filters": {
    "collection_id": "00000000-0000-0000-0000-000000000001",
    "file_ids": [],
    "page": null
  },
  "options": {"force_strategy": null}
}
```

Use an actual collection UUID from the collection API. Clients cannot supply
physical Qdrant collection names. RAG without a selected collection returns an
explicit request to select one and performs no search. `conversation_id` can
resolve its owner's collection, and mismatched/deleted scopes are rejected.
In this release it selects scope only: this endpoint does not replay or persist
conversation turns. Continue using the existing conversation/question endpoints
when persistent conversational interaction is required.

Self-contained transformation requests can provide their material explicitly:

```json
{
  "query": "Rewrite this politely",
  "text": "Send me the report today.",
  "options": {"force_strategy": "direct"}
}
```

`force_strategy` accepts `direct`, `rag`, or `agentic_rag`. Forced RAG disables
escalation so experiments can measure the conventional path independently.
Forced agentic retains the label but still stops if the initial evidence is
sufficient. Debug overrides never disable scope, validation, or resource limits.

The response contains `answer`, `strategy`, `sources` and `metadata`. Each source
has a request-local label, stable evidence/file IDs, page, document version and
exact quote; repeated table headers remain separate context. `X-Request-ID`
matches `metadata.request_id` for accepted requests. Rejected/unauthenticated
requests also get an ID and a content-free boundary trace. HTTP 200 may carry
`status=degraded` or `abstained`; clients should display that state, not interpret
all HTTP 200 responses as reliable generated answers. Render returned Markdown
and source metadata safely, as with every external document.

## Budgets, failures and operation

All adaptive settings use `ADAPTIVE_` environment variables with `__` for nested
fields, following the repository `.env` loading. The validated schema is
`apps/app/services/adaptive/config.py`; a deployable set of examples is in
[`adaptive.env.example`](adaptive.env.example). Thresholds are deployment inputs,
not corpus-independent production guarantees.

Defaults: 4 **additional** agent steps, 5 total retrieval attempts including
retries, 6 maximum LLM calls, 12,000 input-token reservation, 768 output tokens,
20,000 cumulative reserved tokens, 8 documents per step, 16 accumulated evidence
documents, and 15 seconds for the request/agent budget. Dependency timeout is
4 seconds. Targets are 3/6/12 seconds for direct/RAG/agentic; generation reserves
2 seconds, and extra agent work stops before the deadline. Repeated searches,
no new evidence, sufficient evidence, exhausted plans, steps, calls and token
budgets all stop the loop. Independent requests run concurrently; retrieval
within one agent remains sequential so an early sufficient result saves work.

| Failure | Behavior |
| --- | --- |
| Empty or inadequate evidence | Limited escalation, then excerpts or abstention; no unsupported generator call |
| Vector failure | At most one configured retry with exponential backoff, counted against retrieval budget; circuit opens after repeated failures |
| Reranker failure/timeout | Keep filtered search results, record degraded retrieval, use confidence/validation before answering |
| LLM timeout, malformed JSON, fabricated IDs, unsupported/truncated claims | No automatic expensive retry; return existing evidence excerpts |
| Agent failure or budget exhaustion | Keep accumulated evidence; never restart an unbudgeted conventional pipeline |
| Scope repository unavailable | Sanitized 503 and request ID; ownership/not-found errors retain their HTTP semantics |
| Client disconnect | Cancel agent and network waits; native model work retains its capacity permit until completion |

The deadline starts at HTTP entry and the service refuses new work after it.
Legacy authentication still uses the application's database dependency; configure
database connection/statement timeouts and reverse-proxy request limits as well.
Python cannot forcibly terminate native inference in a thread. For hard process
isolation, run local embedding/reranker inference behind separately supervised
workers. Existing dashboard traffic does not share these new admission counters;
operate the new endpoint in a dedicated API worker pool when enforcing an overall
GPU/CPU concurrency budget. Pre-provision model caches and warm model providers
before load; cold loading can exceed the dependency timeout and cause fallback.

Input reservations use UTF-8 byte length plus conservative chat framing for
byte-based tokenizers. Evidence is dropped as whole units when it does not fit;
it is not silently cut halfway through a condition. Returned provider token usage
replaces estimates after successful calls. Failed/timed-out calls retain reserved
usage with `usage_estimated=true`, because remote work may have incurred a cost.
Match the configured token ceilings to the deployed model/context window; these
reservations are not exact tokenizer measurements for every possible model.

Pricing is separate from logic: configure per-million input/output rates and
per-operation embedding/retrieval/reranker rates. Missing rates produce
`estimated_cost_usd=null` and `pricing_complete=false`, not a made-up public price.
Retrieval charges count logical search attempts, including layout lookup; rerank
charges count adapter invocations, including any configured internal prefilter.
Set zero explicitly for a dependency with no marginal charge. Token reservations
can overestimate failed-call cost; use provider billing for reconciliation.

## Caching and invalidation

Embedding cache keys are hashed query plus collection scope; the runtime owns a
single embedding provider, so changing model/config requires its restart and
clears the cache. Cache size/TTL are bounded and can be disabled with zero entries.
Normalized queries stay only in bounded process memory. Retrieval deduplication
and source metadata exist only within one request. Every new request rechecks the
database collection and Qdrant layout, so no persistent cache masks document
deletion. A concurrent delete can still race an already-running request.

Persistent retrieval/document-metadata caching should only be added with an
index publication generation and visibility/ACL revision in the key. Final
answer caching remains disabled until the same invalidation contract exists.
An embedding-model or sparse-encoder change still requires compatible reindexing.

## Metrics and diagnostics

`GET /v1/metrics` exposes Prometheus text and requires an admin bearer token.
Scrape each API worker/replica; counters and histograms are process-local and
restart with the process. Use one worker per scrape target to avoid randomly
scraping different workers through a shared socket.

`ADAPTIVE_CONTENT_LOGGING=false` is the default. Structured traces include routes,
fixed reason codes, action names, evidence IDs, confidence, budgets and timings;
no raw questions/documents or chain-of-thought. Turning content logging on adds
query/subquery text, so enable it only under an appropriate retention policy.
`ADAPTIVE_METRICS_LOGGING` controls trace logging independently of metrics
collection (`ADAPTIVE_METRICS_ENABLED`). No metric label contains a query, user,
file ID, collection ID, or exception string.

Useful PromQL (filter out `route="unrouted"` when measuring accepted requests):

```promql
# Percentage of requests using Agentic RAG; substitute direct/rag for others.
100 * sum(rate(adaptive_request_count_total{route="agentic_rag"}[5m]))
  / clamp_min(sum(rate(adaptive_request_count_total{route!="unrouted"}[5m])), 0.001)

# Percentage of initially conventional requests that escalated.
100 * sum(rate(adaptive_escalation_count_total[5m]))
  / clamp_min(sum(rate(adaptive_initial_route_count_total{route="rag"}[5m])), 0.001)

# p95 request latency for each final route.
histogram_quantile(0.95, sum by (le, route) (rate(adaptive_request_latency_seconds_bucket[5m])))

# LLM calls per accepted request, broken down by route.
sum by (route) (rate(adaptive_llm_call_count_total[5m]))
  / clamp_min(sum by (route) (rate(adaptive_request_count_total[5m])), 0.001)
```

Also exported: retrieval/embedding/reranker counts, input/output tokens, agent
steps, fallbacks, dependency errors/timeouts, abstentions, estimated/unknown cost,
retrieval/generation latency and confidence histograms. Join low-cardinality
metrics with request-ID traces when investigating a failure. To assess whether
the agent is worth its cost, compare fallback/abstention rates and human-reviewed
answer quality on matched traffic alongside additional retrievals, cost and p95.
Latency or citation validity alone cannot establish that benefit.

## Validation and load testing

Run offline application tests from `apps`:

```bash
.venv/bin/python -m unittest tests.test_adaptive_rag tests.test_adaptive_api -v
.venv/bin/python -m unittest discover -s tests -v
```

These cover actual FastAPI dispatch/authentication, the orchestrator, an actual
in-memory Qdrant hybrid collection, HTTP-mocked OpenAI-compatible usage responses,
timeouts, cancellation, malformed output, filter isolation, worker capacity,
cache deletion/expiry and cost/trace accounting. Model responses are controlled
fixtures, not a live-generator correctness benchmark. PostgreSQL opt-in suites
still require their disposable test database settings.

From the repository root, measure plumbing without deploying dependencies:

```bash
apps/.venv/bin/python apps/evaluation/adaptive_load.py --mock \
  --requests 100 --concurrency 8 \
  --out evaluation/results/adaptive-rag-rerun/mock-load.json
```

For a deployed staging environment, export `ADAPTIVE_LOAD_TOKEN` securely, then:

```bash
apps/.venv/bin/python apps/evaluation/adaptive_load.py \
  --base-url http://127.0.0.1:8080 --collection-id YOUR_COLLECTION_UUID \
  --query 'Compare product A and product B' --requests 100 --concurrency 8 \
  --out evaluation/results/adaptive-staging/load.json
```

Both modes report p50/p95/p99, throughput, HTTP error rate, degradation/abstention
rate and mean operation/token counts separately for forced conventional and
agentic routes. The mock uses 5ms retrieval and 10ms generation delays. Its
comparison fixture deliberately requires another search to find product B, so
forced conventional RAG returns incomplete evidence; it is not a fair corpus-wide
accuracy benchmark. The client is closed-loop and does not simulate open-loop
arrival-rate overload or real network/model latency.

The recorded [mock run](../evaluation/results/adaptive-rag-20260920/mock-load.json)
contains 100 measured requests per strategy after warm-up, concurrency 8. It
observed zero HTTP errors; conventional requests used one retrieval and returned
degraded evidence, while agentic requests used three retrievals, two additional
steps and one generation. No deployment, production reindex, live external model
accuracy test, or live service load test has been performed for this slice.

Final regression result: **247 tests run, 215 passed, 32 skipped**, including
44 adaptive tests. Skips are the opt-in PostgreSQL suites, not passes. The mock
run recorded p95 client latency of about **15ms conventional / 37ms agentic**;
these numbers describe the simulated workload above. See the
[validation record](../evaluation/results/adaptive-rag-20260920/validation.json)
and [code fingerprints](../evaluation/results/adaptive-rag-20260920/source-manifest.json).
