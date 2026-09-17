# Knowledge subsystem

Read `docs/DILLEMA_V2_PLAN.md` and `docs/DILLEMA_V2_RUNBOOK.md` at repository root before changing this subsystem. The target architecture is in `docs/DILLEMA_V2_DESIGN.md`; the plan records what is actually implemented.

Read `docs/DILLEMA_V2_VALIDATION.md` before changing the extractor or interpreting test results. The configured live model has not passed the fictional pilot. PostgreSQL tests are opt-in and skipped results must never be counted as passes.

- Keep this package importable without downloading models, starting services, or loading credentials. Worker CLI runtime configuration is imported inside `main()`.
- PostgreSQL holds the canonical graph. SQLite is an offline test backend. Preserve compatible SQL where practical; validate concurrency changes on PostgreSQL.
- Preserve exact source text, stable IDs, collection scope, qualifiers, source visibility, and the approved-claims retrieval gate.
- Publication must check job identity, lease ownership/expiry, schema revision, and active source inside a transaction. Add a regression for changes affecting retries, deletion, or replacement.
- Never equate JSON validity or quotation overlap with semantic truth. Review remains required until an evaluated alternative is explicitly designed.
- Do not edit deployed Alembic revisions. Add a revision after the current head.
- Run the relevant offline tests using the RAGforge environment. The full command from root is `PYTHONPATH=apps/RAGforge apps/RAGforge/.venv/bin/python -m unittest discover -s apps/RAGforge/tests -v`.
- Update the plan's implementation status, limitations, and validation evidence when completing a task. Keep test fixtures and live-model results clearly distinguished.
