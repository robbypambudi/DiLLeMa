# DiLLeMa v2 pilot — setup and operation

The pilot adds reviewed knowledge extraction to RAGforge. It requires the existing PostgreSQL/Qdrant application environment and an inference endpoint. There is no new mandatory Python dependency and no mandatory Neo4j service in this slice.

## 1. Configure and migrate

From `apps/RAGforge`, use the existing `.venv` or synchronize the app environment with `uv sync`. The root DiLLeMa environment serves models; the app environment runs RAGforge and the extraction worker.

Ensure `.env` contains the existing PostgreSQL connection values and LLM settings. New optional settings:

```dotenv
KG_ENABLED=true
# These inherit LLM_BASE_URL, LLM_API_KEY and LLM_MODEL unless overridden:
# KG_LLM_BASE_URL=http://localhost:8000/v1
# KG_LLM_API_KEY=any
# KG_LLM_MODEL=qwen-7b
KG_MAX_CHUNKS=200
KG_MAX_OUTPUT_TOKENS=4096
KG_RETRIEVAL_LIMIT=12
KG_EXTRACTION_FORMAT=text
# Optional: json_schema, only for endpoints supporting this response format.
```

The model name must match the serving endpoint. Choose a model that can follow the extraction schema on Indonesian text; no quality claim has been established for the default model alias.

Preview migration SQL, then apply migrations to the intended application database:

```bash
.venv/bin/python -m knowledge.migrate --sql
.venv/bin/python -m knowledge.migrate
```

The new revision follows `a1b2c3d4e5f6`. It creates `kg_profiles`, `kg_jobs`, `kg_documents`, `kg_chunks`, `kg_entities`, `kg_claims`, and `kg_aliases`. Parent files/collections/users must come from the existing migration chain. The preview renders the full upgrade chain from base; the actual command applies only unapplied revisions.

Restart the backend with its normal command and build/start the frontend as usual. Global enablement is read at process startup. Apply migrations before serving with `KG_ENABLED=true`.

## 2. Configure a collection and extract

1. Sign in as admin and open a collection.
2. In **Knowledge graph**, enable extraction and save the settings.
3. Optionally edit the extraction schema. The default covers programs, organizations, people, procedures, requirements, and concepts. Only explicitly declared relation types are extracted.
4. Upload documents and wait until normal indexing completes. New uploads in an enabled collection automatically enqueue extraction.
5. For existing documents, select an indexed document and choose **Extract knowledge**.
6. Start the worker in a separate process:

```bash
.venv/bin/python -m knowledge.worker
```

To process at most one queued job:

```bash
.venv/bin/python -m knowledge.worker --once
```

The worker uses a 300-second lease. Each model request has a 120-second timeout with SDK retries disabled; validation permits one repair attempt. A crashed job becomes available after lease expiry, up to three lease acquisitions. Completed chunk results are reused when source/profile/model/output-format/prompt/pipeline/parser provenance and the parsed chunks match. A job explicitly marked failed requires re-enqueueing; this starts a new extraction generation.

If the job remains queued, check that a worker is running against the same database and has `KG_ENABLED=true`. If extraction fails, inspect the job message and model configuration. Empty PDF pages produce an OCR-required failure in this baseline parser. DOCX conversion requires pandoc to be installed; no automatic binary download occurs.

## 3. Review and ask questions

Review each extracted claim together with its source text, conditions, exceptions, and scope. **Approve** only when the source supports the complete claim. Reject unsupported interpretations even when their quotation exists verbatim.

Chat combines existing vector evidence with approved graph claims from that collection. It reranks candidates, passes original text and qualifiers, and includes source labels/locations in the answer. The source footer identifies the context supplied to the model; it does not independently certify every generated claim.

`merge_by_name` controls exact-name linking across documents. Default `[]` scopes identities to each file. For a domain where program/organization names are unique, explicitly set `["Program", "Organization"]`. People cannot opt into this name-only merge. Aliases must appear in the source and can seed retrieval; fuzzy matching and entity merge/split review are future work.

Example materials in `apps/RAGforge/knowledge/examples` are fictional and intended only for a local smoke test. Expected real-model output should be inspected; the model is not guaranteed to reproduce the fixture's wording.

For the example, paste `academic-profile.json` into the collection's schema editor, save, upload `pilot.txt`, and run the worker. Inspect the extracted `MANAGED_BY`, `REQUIRES`, and `HAS_PROCEDURE` claims and their qualifiers before approving them.

## 4. API contracts

All knowledge routes require admin authentication with the application's bearer token. Base path: `/api/v1/knowledge/{collection_id}`.

| Method/path | Request | Response/use |
| --- | --- | --- |
| `GET /profile` | None | Global availability, current profile, revision. Disabled global mode does not query the graph tables. |
| `PUT /profile` | `KnowledgeProfile` JSON | Save validated schema. A changed revision makes previous extraction unavailable until re-extracted. |
| `POST /files/{file_id}/extract` | None | HTTP 202 with job ID/status; only completed files in this collection qualify. Repeated calls reuse an active same-schema job. |
| `GET /jobs` | None | Most recent 100 extraction jobs, status, attempts, and sanitized error. |
| `GET /claims?status=pending&offset=0&limit=20` | Status: pending/approved/rejected | Evidence, qualifiers, source text, page, and review information. Limit maximum 100. |
| `PATCH /claims/{claim_id}` | `{"status":"approved","note":"Source checked"}` or rejected | Records the current decision and authenticated reviewer. |
| `GET /graph?offset=0&limit=50` | Pagination | Nodes and approved claim edges with evidence; a page of the graph, not the entire graph. |

Changing an ontology or re-extracting a document can invalidate claim IDs. A stale review returns 404; refresh the view. Raw filenames, quotations, and conditions are rendered as text in the admin UI and escaped in answer footers.

## 5. Lifecycle and rollback

- Deleting a file cascades its jobs, graph document, chunks, claims, and aliases. Entity rows that have lost all support may remain internally; retrieval considers only entities in visible approved claims. Physical orphan cleanup is on the backlog.
- The SQL graph publishes per document in one transaction. Readers see the previous successful graph or the complete replacement. New claims require review again.
- Changing a profile makes old graph records ineligible via the schema revision join. Re-enqueue the collection's documents explicitly; there is no automatic collection-wide backfill yet.
- Source files are assumed immutable after upload. The worker hashes contents and checks again before publication. Upload a changed source as a new document; retire old sources deliberately.
- `KG_ENABLED=false` restores the existing vector-only path and stops the worker from starting. Stored knowledge is retained. Per-collection disablement stops graph use for that collection.
- A graph retrieval failure logs a warning and falls back to vector evidence. It does not convert pending/rejected claims into usable evidence.
- Stable Qdrant IDs apply to future writes. Retry already removes a failed file's previous vector points; existing legacy points are not rewritten by the schema migration.

## 6. Verification boundaries

The offline tests use a real disposable SQLite database with foreign keys enabled and fake model responses. They exercise queueing, extraction validation, publication, review, retrieval, and deletion. API tests use the ASGI application boundary; chat tests replace model/vector clients. Frontend production build checks TypeScript and bundling.

The latest local run passed 44 tests and skipped 23 opt-in PostgreSQL tests. The configured model did not pass the fictional live pilot; see [recorded findings](DILLEMA_V2_VALIDATION.md). Before rollout, complete the PostgreSQL tests and real-corpus quality benchmark. Docling/OCR, Neo4j, BM25, conversation memory, and corpus-level publication remain planned milestones.

## 7. Repeat the live-model smoke test

From `apps/RAGforge`:

```bash
.venv/bin/python -m knowledge.smoke --output /tmp/dillema-v2-smoke.json
# When supported by the serving endpoint:
KG_EXTRACTION_FORMAT=json_schema .venv/bin/python -m knowledge.smoke --output /tmp/dillema-v2-structured.json
```

This sends the fictional `knowledge/examples/pilot.txt` to the configured extraction endpoint. It does not require `KG_ENABLED=true`, start a worker, or write to a database. It checks the four annotated relations and exact expected qualifiers from `pilot.expected.json`. Exit status is nonzero for extraction errors, missing claims, or missing qualifiers. The checks are deliberately small and deterministic; they do not replace semantic review or a representative benchmark.

For a separate document, use `--source path/to/document.pdf --profile path/to/profile.json --expectations path/to/expectations.json`. Expectations are optional for custom sources; without them only schema/evidence validation and nonempty output are checked. Reports contain source/model output and should be treated like the source document. Credentials and endpoint URLs are not included. Diagnostic responses are written locally on validation failure, not exposed through job APIs. Server rejection of `json_schema` does not silently fall back; use `text` explicitly if unsupported.

## 8. Run PostgreSQL validation in a disposable database

From repository root, with access to Docker Compose:

```bash
docker compose -p dillema-kg-tests -f apps/RAGforge/tests/compose.knowledge.yml up -d --wait
KG_TEST_DATABASE_URL=postgresql+psycopg2://kg_test:kg_test_local_only@127.0.0.1:55439/kg_test PYTHONPATH=apps/RAGforge apps/RAGforge/.venv/bin/python -m unittest discover -s apps/RAGforge/tests -p test_knowledge_postgres.py -v
docker compose -p dillema-kg-tests -f apps/RAGforge/tests/compose.knowledge.yml down
```

Run the final cleanup command even when tests fail. The dedicated service binds localhost and stores data in tmpfs; its static credentials are test-only. Use a separate Compose project and an unused port when running multiple suites simultaneously. The test URL is explicit and never falls back to application settings. Each test creates, migrates, and drops its own random `kg_test_*` schema; do not point it at the production database.

The suite inherits the persistence regressions and adds actual `SKIP LOCKED`, concurrent claim/enqueue/publication, delete-versus-publication and schema-versus-publication tests. Race tests observe PostgreSQL lock contention before releasing the conflicting transaction. Migration tests use the full real revision chain through an injected connection, not `metadata.create_all()`.

On the current machine, Docker remained inaccessible after sandbox escalation and passwordless sudo was unavailable. These 23 tests are prepared but have no recorded PostgreSQL pass yet.
