# DiLLeMa v2 — implementation plan and agent handoff

Updated: 2026-09-17. Read this file before continuing v2 work.

## Current delivery

The repository now contains an **opt-in Knowledge Graph pilot** inside `apps/`. This is an executable first slice of the [target design](DILLEMA_V2_DESIGN.md), not the complete production v2 release. The graph is stored as normalized SQL tables in the existing PostgreSQL database. Neo4j remains a future derived projection.

The working flow is: configure collection schema → index/upload document → queue extraction → run worker → review source-backed claims → use approved graph evidence in chat. See the [runbook](DILLEMA_V2_RUNBOOK.md) for commands and endpoint contracts.

### Implemented

- Collection-specific, validated entity/relation schemas with deterministic revision hashes.
- Structured extraction via the configured LLM endpoint; bounded JSON repair with field/direction feedback; validation of entity references, endpoint types, exact mentions, aliases, and evidence quotations. Optional `json_schema` response format constrains entity/relation enums when supported by the server.
- Qualifiers for conditions, exceptions, actor scope, negation, modality, values/units, and validity text.
- Page-aware PDF parsing, exact-text chunk offsets, content hashes, and deterministic chunk IDs. Markdown/DOCX heading context is preserved. Parser dependency versions and the parsed chunk fingerprint invalidate incompatible checkpoints. DOCX uses installed pandoc.
- SQL graph containing documents, chunks, entities, aliases, and reviewed claims. Name merging is explicit per type and collection; `Person` never merges across files solely by name.
- Durable SQL extraction jobs, leases, bounded lease recovery, chunk checkpoints, and atomic publication of one document's graph.
- Stale worker/schema/source checks; foreign-key cascades on source deletion; active-source checks at retrieval.
- Admin APIs and a collection UI for schema configuration, extraction jobs, evidence inspection, approval, and rejection.
- Bounded graph traversal over approved claims, combined with existing dense retrieval and reranking.
- Source labels and escaped source footers, stricter answer grounding, and complete streaming-answer persistence.
- Deterministic Qdrant point IDs for future writes. Existing vectors are not rewritten automatically.
- Self-contained Alembic revision `b2d3e4f5a601` and a migration CLI that does not depend on ignored `alembic.ini` files.
- Database-free live-model smoke CLI with an annotated fictional fixture and relation/qualifier completeness checks; inspectable failure reports.
- Opt-in PostgreSQL suite and disposable Compose database. Tests use a random schema per test, run the actual migration chain, and exercise concurrent leases, enqueue, publication, deletion, and schema changes. Execution remains blocked by Docker access on this machine.

### Explicit limitations

- The configured live model has **not passed the fictional pilot**: initial output omitted the requirement; later output reversed its relation and repeated the error during repair. Invalid output is rejected. See [validation evidence](DILLEMA_V2_VALIDATION.md). The user's real corpus has not been benchmarked; do not claim quality gains or deploy unattended extraction from fixture tests.
- PostgreSQL is the production target. SQLite transactional tests and PostgreSQL SQL generation are not a substitute for PostgreSQL concurrency/load testing.
- PDF tables/layout and OCR are not yet handled by Docling. A page with no extractable text fails with an OCR-required message; pages with partial or garbled extraction still require inspection.
- Hybrid lexical/BM25 retrieval, multilingual model migration, and learned entity resolution remain pending. Current answering combines the existing dense retriever with graph evidence.
- Review establishes semantic acceptance. Exact quote validation alone does not prove a model's interpretation. New/re-extracted claims begin as `pending`.
- Review records the latest decision, reviewer, time, and note. Append-only decision history and editing/splitting/merging entities need a follow-up migration.
- Graph publication is atomic per document, not a corpus-wide snapshot coordinated with Qdrant. The graph can remain on the previous successful document extraction while replacement is processing.
- Text chunks used by the graph parser are separate from legacy vector chunks. Shared canonical chunk IDs across stores require an indexing migration.
- A graph contains only explicit extracted claims. Conditions are preserved as text; there is no formal eligibility/rule evaluator.
- UI provides relationship/evidence review, not an interactive node-link visualization. The graph API can support one later.
- Conversation-aware query rewriting is not implemented; streaming persistence is fixed as a prerequisite.
- Corpus summary/community reports, multimodal diagram interpretation, and fine-tuning are deferred.

## Code map

| Responsibility | Files |
| --- | --- |
| Ontology and extraction contracts | `apps/knowledge/contracts.py` |
| Source parsing and chunk identity | `apps/knowledge/documents.py` |
| Model boundary and bounded validation/repair | `apps/knowledge/extraction.py` |
| Canonical graph schema | `apps/knowledge/tables.py` |
| Jobs, publication, review, traversal | `apps/knowledge/repository.py` |
| Worker and migration commands | `apps/knowledge/worker.py`, `migrate.py` |
| Live model smoke and annotated expectations | `apps/knowledge/smoke.py`, `knowledge/examples/pilot.expected.json` |
| API and DI | `apps/app/api/v1/endpoints/knowledge.py`, `apps/app/core/container.py` |
| Upload integration | `apps/app/pipeline/pipeline_service.py` |
| Chat integration | `apps/app/services/question_service.py`, `apps/rag/llm/chat_model.py`, `apps/rag/llm/re_rank.py` |
| Admin review | `apps/web/src/components/KnowledgePanel.tsx` |
| Tests | `apps/tests/test_knowledge*.py` |

## Invariants for subsequent agents

1. Every published claim points to an existing source chunk; quote offsets must reproduce the exact stored quotation.
2. Collection IDs constrain schema, jobs, review, graph expansion, and evidence. Never seed a collection's graph from another collection's data.
3. Only `approved` claims participate in answering. Pending/rejected claims remain visible only to admin review.
4. A graph path is a retrieval path, not proof. Preserve qualifiers and original text through reranking and generation.
5. A worker can publish only while it owns an unexpired lease for the same job ID, source file, and schema revision. Deletion and replacement invalidate old jobs.
6. Re-extraction publishes all chunks/claims atomically, resets review for the new generation, and preserves the previous successful graph if replacement fails.
7. Exact-name merge is an explicit schema policy, not a generic similarity threshold. Keep the default conservative; do not automatically merge people.
8. Keep migrations frozen and self-contained. Once a revision is deployed, add a new migration rather than editing it.
9. Qdrant/Neo4j are future projections of canonical data. Do not introduce an assumption of a shared transaction across stores.
10. Preserve v1 availability with `KG_ENABLED=false`. Missing graph infrastructure must not require downloading or starting extra services for legacy chat.

## Ordered backlog

Task IDs are stable handoff references. Update status, tests, and limitations when completing a task.

| ID | Status | Deliverable | Acceptance criteria |
| --- | --- | --- | --- |
| V2-01 | Implemented, offline verification | Schema, source evidence, SQL graph, jobs, review, chat integration. | Offline regression suite passes; production frontend builds; migration SQL emits. Live deployment remains a runbook step. |
| V2-02 | Next | Representative pilot and extraction evaluation. | Annotated entities/claims/evidence/qualifiers for real documents; at least 50 real questions; held-out split; extraction precision/recall and answer correctness reported. No fabricated benchmark gains. |
| V2-03 | Harness implemented; live model failed, PostgreSQL pending | PostgreSQL and real-model smoke/concurrency tests. | Two workers cannot process/publish the same lease; expiry, delete, schema change, and retry races pass against disposable PostgreSQL. Real endpoint produces valid reviewed evidence from sample docs. |
| V2-04 | Parser fingerprint/heading groundwork implemented; Docling pending | Docling parser adapter and OCR/table corpus. | Stable page/block provenance; preserved table headers/units/footnotes; scanned and multicolumn PDF tests; no silent partial extraction; parser-version cache invalidation. |
| V2-05 | Planned | Canonical vector index and lexical retrieval. | Same source IDs in SQL/Qdrant; dense and BM25/sparse branches fused and reranked; multilingual embedding benchmark; new collection dimensions; backfill/rollback without mixing vector spaces. |
| V2-06 | Planned | Entity review and resolution. | Persist mentions; explicit merge/split decisions and redirects; no false person merges; alias deletion and cross-document resolution tests; append-only review audit. |
| V2-07 | Planned | Neo4j projection. | Outbox committed with canonical changes; replayable idempotent projector; deletion handling; collection scoping; export/import contract; SQL/Neo4j retrieval parity tests; pinned deployment version. |
| V2-08 | Planned | Conversation and evidence verification. | Session IDs and stored history; standalone query rewrite; no cross-session leakage; citation identifiers checked against retrieved evidence; unsupported claims detected or abstained. |
| V2-09 | Planned | Retrieval quality and scale. | Replace 2,000-name scan and fixed traversal caps with indexed entity linking and measured candidate ranking; Recall@k and multi-hop coverage measured; latency/memory budgets set from baseline. |
| V2-10 | Planned | Corpus lifecycle and operational tooling. | Cross-store publication manifests; outbox recovery; retained revisions; orphan cleanup; processing metrics; job pagination/backfill; backup/restore and worker deployment recipe. |
| V2-11 | Optional after evidence | Community summaries/global search, multimodal extraction, formal rule execution. | Improvement shown on the relevant question classes with additional cost reported. |

V2-02 and V2-03 establish evidence for selecting models and capacity. V2-04 improves the source representation before broad graph backfill. V2-05 and V2-07 must agree on canonical IDs and publication semantics. Avoid choosing a distributed job framework solely because Ray is already used for inference; the SQL lease contract remains the source of job ownership.

## Validation commands

From repository root, using the existing dashboard environment:

```bash
PYTHONPATH=apps apps/.venv/bin/python -m unittest discover -s apps/tests -v
PYTHONPATH=apps apps/.venv/bin/python -m knowledge.migrate --sql
apps/.venv/bin/python -m compileall -q apps/knowledge apps/app apps/rag apps/migrations
git diff --check
```

From `apps/web`, run `npm run build`. These commands do not call a live extraction model or apply migrations to a running database. `knowledge.migrate` without `--sql` does apply migrations.

Core regression cases: unsupported quotation, invalid ontology endpoints, qualifier preservation, alias scope, deterministic IDs, exact page offsets, interrupted-worker resume, expired lease fencing, replacement publication, deletion cascades, cross-collection isolation, review authorization, graph-to-chat evidence, and streamed-answer persistence.

### Recorded verification (2026-09-17)

| Check | Result |
| --- | --- |
| Offline unit/integration suite | 44 tests passed, including real SQLite persistence, parser checkpoint invalidation, constrained-output validation, and ASGI authorization/review paths. 23 PostgreSQL tests explicitly skipped without `KG_TEST_DATABASE_URL`; 67 discovered in total. |
| Frontend production build | `tsc` and Vite build passed. Existing browser-data freshness warnings remain. |
| Migration | Frozen revision upgrade/downgrade passed on disposable SQLite; complete PostgreSQL migration SQL generated successfully. |
| Python compilation and whitespace | `compileall` and `git diff --check` passed. |
| Live model | Configured model alias `qwen-7b` was reachable. Current prompt `evidence-extraction-5` with `json_schema` failed ontology validation on the fictional pilot after two attempts. Raw normalized evidence is checked in under `docs/validation/`. Alias does not establish the underlying model size/version. |
| PostgreSQL | Suite prepared but not run. Docker socket permission denied outside the sandbox too; `sudo -n docker` required interactive authentication. No application database was migrated or used as a test substitute. |

The environment's sandbox stalled the TestClient thread portal. A traceback identified the portal wait; the same suite passed outside the sandbox using the execution approval mechanism. Treat that as an environment constraint when reproducing these tests, not as permission to bypass sandbox controls.

## Suggested next-agent assignment

> Read the plan, runbook, and `docs/DILLEMA_V2_VALIDATION.md`. Preserve current git changes. Complete V2-03: run the prepared PostgreSQL suite in its disposable database once Docker access is available. Investigate the live model's repeated reversed `REQUIRES` edge: check serving conversation/repair handling and the actual deployed model, then compare extraction approaches on additional annotated documents. Keep validation/review gates; do not reverse edges automatically just to pass the fixture. Do not use the application database as a test substitute. Add real-corpus evaluation before reporting quality improvement.

For V2-04, extend parser provenance to stable block references and table/page spans before integrating a converter. Review the official [Docling converter](https://docling-project.github.io/docling/reference/document_converter/), [document traversal](https://docling-project.github.io/docling/reference/docling_document/), and [table export](https://docling-project.github.io/docling/_generated/examples/export_tables/) interfaces. Pin and validate an isolated parser environment; reject partial conversions, preserve table headings/units/footnotes, and test scanned/multicolumn PDFs. No Docling dependency or runtime adapter has been installed in this delivery.

Do not report DiLLeMa v2 as production-ready based only on SQL/fixture tests. Do not assume the version string already present in the FastAPI app represents completion of this roadmap.
