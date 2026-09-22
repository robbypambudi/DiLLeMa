# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

DiLLeMa is a distributed LLM serving system built on **Ray** (orchestration) and **vLLM** (inference). It exposes a `dillema` CLI that manages a Ray cluster and deploys models behind an OpenAI-compatible API via Ray Serve. Published to PyPI as `DiLLeMa`.

## Environment constraint

Runtime dependencies (`ray[default,serve]==2.55.0`, `vllm==0.18.0`) require Linux + a CUDA GPU and **do not install on macOS**. This means `uv sync`, `uv run pytest`, and anything importing `dillema.serve`/`dillema.cli` will fail on a Mac dev machine. Do package-level edits and reasoning locally; run/test the serving stack on a Linux GPU host (see `install.sh`).

## Commands

```bash
# Install (editable) + dev tooling
uv sync                      # runtime + dev deps from pyproject.toml / uv.lock

# Tests (CI runs `uv run pytest test`)
uv run pytest test
uv run pytest test/test_example.py::test_example   # single test

# Format (CI runs black over the whole tree)
uv run black .

# Build wheel/sdist
uv build                     # or: ./build.sh  (uninstalls, builds, reinstalls locally)
```

**Known-broken test:** `test/test_example.py` imports `from dillema import example`, but no `dillema/example.py` exists — the test suite fails to collect. Add the module or fix the import before relying on `pytest`.

## CLI (the primary interface)

Entry point is `dillema.cli:main` (registered as the `dillema` console script). Subcommands:

- `dillema head [--node-ip-address IP]` — runs `ray start --head` via subprocess, prints the worker join address.
- `dillema worker --address ip:port [--node-ip-address IP]` — runs `ray start --address=...`. On a multi-homed/VPN host, pass `--node-ip-address` on both head and worker so Ray advertises the VPN IP instead of the default-route one.
- `dillema stop [--force]` — runs `ray stop` (`--force` kills stale Ray processes with SIGKILL).
- `dillema serve --model-id ... --model-source ...` — `ray.init(address=...)`, builds an `LLMServe` app, and `serve.run(..., blocking=True)`.

The head/worker/stop commands are thin wrappers that **shell out to the `ray` CLI**; the real serving logic lives in `serve`. When `RAY_TMPDIR` is set (in `.env`), every `ray start` the CLI runs gets `--temp-dir=$RAY_TMPDIR/ray` — needed on workers too, since a worker without it reuses the head's temp dir path. Use it when `/tmp` is a tmpfs, otherwise Ray logs live in RAM.

## Securing the endpoint

The served `/v1` OpenAI endpoint has **no authentication** — Ray Serve LLM has no built-in API-key support and no official in-process middleware pattern ([ray#59578](https://github.com/ray-project/ray/issues/59578)). Do **not** expose `dillema serve` directly on a public interface. The supported pattern (see `deploy/auth-proxy/`) is to bind DiLLeMa to localhost (`--app-host 127.0.0.1 --app-port 8001`) and put a bearer-token reverse proxy (Caddy) in front on the public port. The dashboard authenticates with `LLM_API_KEY` / `LLM_BASE_URL`.

## Docker

`Dockerfile` builds the serving image on `rayproject/ray:2.55.0-py312-cu128` (Ray + Python 3.12 + CUDA 12.8) and uses `uv sync` to install `vllm` + the package. Notes:
- vLLM is installed from `uv.lock` (the `ray-llm` image has no py312 build). uv installs CPython 3.12.9 to match `requires-python` in `pyproject.toml`. Pairing is Ray 2.55.0 + vLLM 0.18.0 so Qwen3.5 (`qwen3_5`) is supported.
- Running needs the NVIDIA Container Toolkit and `--gpus all`; the build itself is GPU-free.
- `dillema serve` calls `ray.init(address="auto")`, so start a cluster first in the container (`ray start --head && dillema serve ...`) — see the header comment in `Dockerfile`.

## Architecture

The package is intentionally small — a CLI dispatcher over a single serving wrapper — plus standalone research code:

- **`dillema/cli.py`** — argparse dispatcher. For `serve`, translates `--network-interface` into a Ray `runtime_env` that sets `GLOO_SOCKET_IFNAME` / `NCCL_SOCKET_IFNAME` (required for multi-node collective comms to bind the right NIC), then delegates to `LLMServe`.

- **`dillema/serve/llm.py`** — `LLMServe` wraps Ray Serve's `LLMConfig` + `build_openai_app`. `build_app()` assembles engine kwargs (`tensor_parallel_size`, `pipeline_parallel_size`, `trust_remote_code`), an autoscaling config (`min_replicas`/`max_replicas`), and a runtime env that always sets `VLLM_USE_V1=1` and injects `HF_TOKEN` (arg or `HF_TOKEN` env). This is the public Python API: `from dillema.serve import LLMServe`.

Cluster management is done via the `ray` CLI (`dillema head/worker/stop`) and observed through the Ray Dashboard (`:8265`); there is no bundled web UI. Application/UI concerns live in the dashboard app (see below).

**Parallelism model:** tensor parallelism (`--tensor-parallel`) splits a model across GPUs on a node; pipeline parallelism (`--pipeline-parallel`) splits across nodes. Both feed straight into vLLM engine kwargs.

## Non-package directories

These are research/benchmarking artifacts, **not** part of the shipped package (excluded from the build):

- `evaluation/` — standalone multi-node deployment + benchmark scripts (`ray_model_deployer.py`, `ray_model_evaluator.py`, VPN/dual-node setup shells). See `evaluation/README.txt`. Note: an `.pem` private key is checked in here — do not add more secrets.
- `analysis/` — Ray/vLLM experiment notebook and scratch scripts.
- `apps/` — the DiLLeMa dashboard (FastAPI + web + knowledge graph); it lives directly in this repo as a separate project, not as a submodule.

## apps/ (dashboard)

A **self-contained RAG dashboard** (`rag-template` package metadata, originally from `https://github.com/robbypambudi/RAGforge.git`), vendored into this repo with its own `pyproject.toml` and `uv.lock`; configuration comes from the single repository `.env` (see below). It is the *consumer* side: a Retrieval-Augmented Generation app that talks to an OpenAI-compatible LLM endpoint (via `langchain-openai` `ChatOpenAI`) — the same kind of endpoint `dillema serve` exposes.

It was previously a git submodule; it is now a plain directory at `apps/`, so edits are tracked directly by this repo and no longer sync with the upstream RAGforge repo. It has its own toolchain (`uv`, Ruff) and is excluded from both the DiLLeMa Python package build and the `Dockerfile` image.

### Stack & services

- **Backend:** FastAPI (Python), managed with `uv`. Postgres (metadata/structured) + **Qdrant** (vectors). SQLAlchemy/SQLModel with Alembic migrations. Embeddings default to `intfloat/multilingual-e5-small`.
- **Frontend:** React + TypeScript + Vite + Tailwind in `web/` (port 3000).
- **Infra:** `docker-compose.yml` brings up Postgres (5432) and Qdrant (6333/6334).

**Configuration:** one `.env` at the repository root (template `.env.example`) is read by the `dillema` CLI (`dillema/env.py`), the API (`app/core/config.py`) and the web app (`web/vite.config.ts` loads the root `.env` itself and exports its `VITE_*` keys, mapping `BACKEND_URL` → `VITE_BACKEND_URL`; empty means same-origin `/api` via the Vite proxy — it deliberately does not set `envDir` to the repo root, because Vite watches `envDir` recursively and would hit the inotify limit on `.venv`). A legacy `apps/.env` is still read for missing keys, with a warning; `apps/web/.env` is ignored.

### Running it (from `apps/`)

```bash
cp ../.env.example ../.env
uv sync
docker compose up -d                   # Postgres + Qdrant
uv run alembic upgrade head             # DB migrations
uv run uvicorn app.main:app             # API on :8000, docs at /docs
cd web && npm install && npm run dev    # frontend on :3000
```

### Backend architecture

Classic layered design wired by **`dependency-injector`**:

- **`app/`** — `main.py` builds a singleton `App` that constructs `app/core/container.py::Container` (the DI graph: DB, Qdrant client, embedding model, repositories, services, pipeline). Request flow is `api/v1/endpoints/*` → `controllers/` → `services/` → `repositories/` (over `models/`). Config is Pydantic-settings in `app/core/config.py` (reads the repository `.env`, then legacy `apps/.env`; `SQLALCHEMY_DATABASE_URI` is computed from `POSTGRES_*`).
- **`app/pipeline/pipeline_service.py`** — document ingestion: reads PDF/DOCX (DOCX via `pypandoc`, auto-downloads pandoc)/text, then cleans → chunks → embeds → stores in Qdrant.
- **`rag/`** — the reusable RAG core, independent of the web layer: `embedding/` (factory pattern), `llm/` (`chat_model.py` OpenAI chat, `re_rank.py`), `nlp/` (`doc_chunking.py`, `doc_cleaner.py`, `query.py`), and `qdrant/` + `chroma/` vector-store clients.
- **`agents/augment_query_generated.py`** — query augmentation/expansion using OpenAI (`OPENAI_API_KEY`).

Note: the dashboard app uses **Ruff** (see its `pyproject.toml`), unlike the DiLLeMa package which uses Black.

## CI/CD

`.github/workflows/build.yml`: on push/PR to `main` → `uv sync --only-group dev`, `uv run pytest test`, `uv run black .`, `uv build`. On push to `main`, a `deploy` job publishes to PyPI via `uv publish` (`PYPI_API_TOKEN` secret). Version is read dynamically from `dillema.__version__` in `dillema/__init__.py` — bump it there when releasing.
