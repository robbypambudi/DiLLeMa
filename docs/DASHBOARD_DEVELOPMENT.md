# Dashboard development

The dashboard is the separate application in `apps/`: React/TypeScript in
`apps/web`, FastAPI in `apps/app`, and reusable retrieval/extraction code in
`apps/rag` and `apps/knowledge`.

## Frontend structure

```text
apps/web/src/
  App.tsx                  # Root providers and router
  app/                     # Route composition and application layouts
  pages/                   # General pages, such as the welcome page
  features/
    auth/                  # Login API, session state, provider and route guards
    chat/                  # Conversation state, streaming, formatting and export
    collections/           # Collection API, management hooks and pages
    files/                 # Upload, retry, deletion and document polling
    knowledge/             # Profile, extraction jobs and claim review
  shared/
    api/                   # HTTP client, token transport, response types and SSE
    components/            # Reusable controls and dialogs
    hooks/                 # Shared behavior such as theme selection
    lib/                   # Generic utilities
    config.ts              # Environment configuration
```

Each feature owns its API functions, domain types, stateful hooks and UI.
Pages compose components; hooks coordinate requests and state; `api.ts` modules
define URLs, payloads and response types. Reuse the shared HTTP client for JSON,
multipart uploads and streaming so authorization and errors behave consistently.

Development rules:

- Put domain-specific code in its feature. Put code in `shared` only when it is
  independent of application features. Shared modules must not import features,
  pages or application composition.
- Import domain types from their feature using `import type`. Do not export
  domain types from `App.tsx`. Use explicit types at API boundaries and `unknown`
  for untrusted values; backend validation remains authoritative.
- Keep API calls and polling out of reusable UI components. Feature hooks own
  loading, mutation and error state. Simple local forms can call their feature API.
- Clean up requests and timers when a component unmounts. Abort or ignore stale
  responses when the selected resource changes. Poll again after each completed
  request instead of accumulating overlapping interval requests.
- Use `shared/components/ui` and the existing Tailwind tokens. Keep labels,
  keyboard behavior, loading feedback and error feedback when extracting UI.
- Render assistant HTML through `sanitizeAnswer`. HTML exports must sanitize
  assistant output and escape user text. SSE events can span packets and contain
  multiple `data:` lines; the shared decoder preserves their line breaks.
- Treat chat responses as deltas. The backend normalizes model snapshots; a
  repeated frontend token is valid content. The chat session hook coordinates
  database history for authenticated users and local storage for guests. Auth
  is in session storage, and the theme is shared for the current page session.

ESLint enforces TypeScript imports, hook dependencies, Fast Refresh boundaries,
shared-module dependency boundaries and central use of `fetch`.

From `apps/web` (Node.js 18 or newer):

```bash
npm ci
npm run dev
npm run check        # lint, regression tests, TypeScript and production build
npm run typecheck   # TypeScript only
```

Frontend regression tests compile production TypeScript with the existing Vite
toolchain into ignored `.test-build/` artifacts, then use Node's test runner.
They exercise HTTP authentication/error handling and SSE packet boundaries,
Unicode, multiline content, reader cancellation and history restoration/storage.

## Chat history

`features/chat/hooks/useChatSession.ts` owns chat creation, streaming, restoration,
history pagination and deletion. `lib/history.ts` maps persisted turns to display
messages; `lib/historyStorage.ts` handles validated guest storage and active-chat
IDs. `ChatHistory` renders the conversation list inside the collection sidebar.

- Signed-in chats belong to the authenticated user and are stored in PostgreSQL.
  Each API operation checks ownership; admin status does not grant access to
  another user's conversations. Signing in or out remounts the chat session,
  aborts outstanding requests and isolates account state.
- Guest chats use the browser's `dillema:guest-conversations:v1` local storage key.
  Reloading restores saved messages, including partial answers. Browser data
  removal also removes guest history. Storage errors are shown without silently
  overwriting unreadable history. Guest chats are not imported into an account.
- New chat and collection selection create a fresh conversation. Opening history
  restores its collection and ordered messages; the selected conversation is
  remembered separately for each account and for guests.
- `conversations` stores owner, collection snapshot, title and UTC timestamps.
  `conversation_turns` stores ordered question/answer pairs with `pending`,
  `completed`, `failed` or `interrupted` status. A question is committed before
  generation starts. Completion, generation errors and client disconnects save
  the result. After a server crash, pending turns older than ten minutes become
  interrupted when reopened or when the next question is submitted.
- Deleting a conversation removes its turns. Deleting a collection retains the
  conversation for reading/export, with its collection ID set to null.
- Legacy `questions` records have no owner or conversation identifier and are not
  assigned to accounts. History saved from this feature onward can be restored;
  earlier in-memory chat sessions cannot be recovered. Generation continues to
  retrieve evidence for each question; saved turns are not additional LLM context.

The authenticated endpoints are `GET/POST /api/v1/conversations` and
`GET/DELETE /api/v1/conversations/{id}`. Lists accept `offset` and `limit` (1–100).
Both question endpoints accept an optional `conversation_id` form field; requests
that include it require its owner to be signed in. Requests without it retain
the public, legacy question behavior. Ownership/conflict errors are returned
before SSE starts.

Apply the additive migration before starting the updated backend:

```bash
cd apps
uv run alembic upgrade head
```

Revision `c3d4e5f6a702` adds the two history tables without changing existing data.
Ensure the Alembic database URL matches the application database in your environment.

## Backend structure

```text
apps/app/
  main.py                  # Stable ASGI entrypoint: app.main:app
  application.py           # create_app and startup/shutdown resource ownership
  api/v1/endpoints/        # HTTP validation, authorization and service dispatch
  core/                    # Configuration, DI, security and exception handlers
  schema/                  # Request and response contracts
  services/                # Collection/file/auth/question/knowledge use cases
  repositories/            # Persistence and transaction boundaries
  models/                  # Database models
  pipeline/                # Document ingestion and background task boundary
```

The request flow is `endpoint → service → repository / RAG adapter`. New routes
belong in `api/v1/routes.py`; register dependencies in `core/container.py`.
`KnowledgeService` handles profile changes, extraction dispatch, claim review
and graph projection. `RetrievalService` combines vector evidence and approved
graph evidence. `QuestionsService` coordinates generation, citations and saving.
Its existing direct-construction arguments remain supported for callers and tests.

Backend rules:

- Keep HTTP routes small. Put business decisions and orchestration in services,
  SQL in repositories, and reusable model/vector behavior in `rag/`.
- Keep synchronous endpoints as `def`. FastAPI runs them in its worker pool.
  Within an async stream, offload synchronous retrieval and persistence with
  `run_in_threadpool`. Do not wrap synchronous handlers in an async decorator.
- Repository context managers own database sessions. There is no endpoint-level
  session cleanup hook. Application startup/shutdown owns the database engine;
  cleanup must also happen if startup fails.
- Attribute citations from the finished answer, not from retrieval. Report only
  the sources whose `[Sn]` marker the answer wrote, keeping each source's
  original number so the markers still resolve; an answer with no valid markers
  reports no sources. Strip model-written source footers before attribution.
  Quotes are chosen at citation time against the claim that cites them and
  must stay verbatim slices of an individual source window, never concatenated
  excerpts from disjoint windows,
  because the viewer highlights a quote by searching the rendered page for it.
  A marker attributes a source; it does not establish semantic support.
- Packing and citation labels share file/version/parent identity. Keep all
  retrieved leaves of selected parents, including late leaves beyond the stored
  page prefix, and keep graph claims separate. New chunks carry `evidence-v2`
  metadata and verified Unicode offsets in the cleaned extraction unit.
- The answer prompt is versioned in `rag/llm/chat_model.py`. Keep demonstrations
  fictional and outside the final evidence message. Source text is escaped
  inside labelled elements; this preserves boundaries but does not guarantee
  that a model resists instructions inside a source. Prompt changes must be
  checked with actual generated answers, including missing evidence, negation,
  conflicting rules, and forged citation labels. Lexical overlap and valid
  citation numbers are not semantic validation. The small-model checks live in
  `evaluation/prompt_eval.py`; preserve earlier results when tuning templates.
- Cite the page label printed on the page and navigate by the physical index.
  `pages` carries the index, `page_labels` the label, in the same order.
- Evidence scoring below `RERANK_MIN_SCORE` is dropped, and empty retrieval must
  reach the user as "not enough information" rather than an unsupported answer.
- Preserve URL paths, payloads, response envelopes, authorization and source
  metadata during structural refactors. Central exception handlers retain
  `{ "errors": [{ "field": "...", "message": "..." }] }` for validation failures.
- Override DI providers with fakes in tests; do not download models or call live
  LLM/vector services in the offline suite. The application factory accepts a
  container so lifecycle and HTTP behavior can be tested independently.
- Knowledge storage changes have additional instructions in
  [`apps/knowledge/AGENTS.md`](../apps/knowledge/AGENTS.md). Follow those before
  changing extraction contracts, persistence or migrations.

From `apps`:

```bash
uv sync
uv run python -m unittest discover -s tests -v
uv run uvicorn app.main:app --host 127.0.0.1 --port 8080
```

With the existing environment, use `uv run python -m unittest discover -s tests -v`.
The suite uses SQLite and fake model/service boundaries. PostgreSQL concurrency
tests run only when `KG_TEST_DATABASE_URL` points to a disposable test database;
otherwise they are reported as skipped. Live model and browser end-to-end checks
remain separate from these offline regression tests.

History ownership, persistence, migration and cancellation tests run in the
offline suite. Set `CHAT_TEST_DATABASE_URL` to a disposable PostgreSQL database
to additionally run `test_conversations_postgres.py`; each test migrates and cleans
up its own random schema and checks concurrent submissions and deletion.

The unused legacy collection modals and `app/controllers` implementation were
removed. Collection administration uses the feature pages, and backend routes
call services directly. Historical versions remain in Git.
