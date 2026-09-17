# DiLLeMa v2 validation evidence

Date: 2026-09-17. This records observed outcomes, not production readiness.

## Verified locally

- 44 offline unit/integration tests passed. They exercise real SQLite transactions and ASGI routes while replacing external model/vector calls with fixtures.
- 23 PostgreSQL tests were discovered and explicitly skipped because `KG_TEST_DATABASE_URL` was not set. Total discovery: 67 tests. Skipped tests are not counted as passes.
- Frontend TypeScript/Vite production build passed during the implementation. No frontend changes were made during the subsequent extraction validation work.
- Migration upgrade/downgrade passed on disposable SQLite; full PostgreSQL SQL generation, Python compilation, and whitespace checks passed.

## Live extraction findings

The configured endpoint responded to model discovery and extraction requests. The registered alias was `qwen-7b`; this does not establish the actual model family, parameter count, quantization, or serving version. Only the fictional pilot was sent; no application database was changed.

The pilot contains four expected relationships: two management relationships, one procedure relationship, and Program A's 80-SKS requirement for regular students from 2026. These expectations are stored separately from the text sent to the model.

An initial text-mode run with prompt version 2 returned three structurally valid claims but omitted the requirement. A later run with requirement guidance produced unknown references. Requests using `json_schema` were accepted, but the model still reversed the requirement edge. Acceptance of that request does not prove complete schema enforcement by the serving stack.

The final recorded run used `evidence-extraction-5`, `json_schema`, temperature 0, and a 4,096-token output cap. It produced `Requirement --REQUIRES--> Program`, although the ontology requires `Program/Procedure --REQUIRES--> Requirement`. The repair request included the failing claim index, actual endpoint types, and allowed types. Both attempts returned the same invalid direction, so extraction failed and nothing was published.

The returned requirement also omitted actor scope and the numeric value/unit qualifiers, and its quotation did not include the following validity sentence. These are source-review findings; schema validity alone would not detect all of them.

The final responses and machine validation errors are retained in [the fictional pilot report](validation/dillema-v2-live-pilot.json). Responses are parsed into JSON objects for readability; no facts or model outputs were corrected. Earlier exploratory prompt outputs are summarized here rather than treated as comparable benchmark trials.

## What this means for the next agent

1. Keep the publication/review gate and exact-evidence checks. Do not silently reverse an edge or fill omitted qualifiers just to pass the smoke test.
2. Verify that the serving path respects all conversation messages, including the repair turn; repeated outputs are an observation, not proof of a server bug. Identify the actual deployed model and inference configuration.
3. Compare a dedicated extraction model or staged entity/claim extraction on a small annotated development set, then evaluate on held-out real documents. A single tuned synthetic example cannot establish general quality.
4. Run the prepared PostgreSQL suite once Docker access is available. The current OS denied Docker socket access even outside the sandbox, and `sudo -n docker` required interactive authentication. No production database was used as a substitute.
5. Complete Docling/OCR/table provenance before broad document backfill. Current parser improvements cover page/heading context and versioned cache invalidation, not document-layout fidelity.

Commands and operating details are in the [runbook](DILLEMA_V2_RUNBOOK.md); task IDs and acceptance criteria are in the [implementation plan](DILLEMA_V2_PLAN.md).
