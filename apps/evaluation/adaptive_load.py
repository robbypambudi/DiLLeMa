"""Closed-loop HTTP load test; --mock measures plumbing, never model quality.

Live authentication comes from ADAPTIVE_LOAD_TOKEN, not a command-line secret.
"""

import argparse
import asyncio
import json
import math
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx


def percentile(values, percent):
    values = sorted(values)
    return values[max(0, math.ceil(len(values) * percent) - 1)] if values else 0


def mock_application():
    from fastapi import FastAPI
    from app.api.v1.endpoints.answer import router, get_runtime
    from app.core.dependencies import get_current_user
    from app.services.adaptive.config import AdaptiveConfig
    from app.services.adaptive.contracts import Document, GenerationResult
    from app.services.adaptive.orchestrator import AdaptiveAnswerService
    from app.services.adaptive.resilience import BoundedWorker

    class Retriever:
        async def retrieve(self, query, top_k, filters, trace, **kwargs):
            trace.retrieval()
            await asyncio.sleep(0.005)
            # Initial comparison retrieves A only. Decomposition must find B.
            which = "B" if query == "product B" else "A"
            return [
                Document(
                    id=which,
                    file_id=which,
                    text=f"The product {which} capacity is 20 units.",
                    score=0.95,
                    score_kind="reranker",
                )
            ]

    class Generator:
        async def generate(self, messages, max_tokens):
            await asyncio.sleep(0.01)
            evidence = json.loads(messages[-1]["content"])["evidence"]
            return GenerationResult(
                content=json.dumps(
                    {
                        "claims": [
                            {"text": d["text"], "source_ids": [d["label"]]}
                            for d in evidence
                        ]
                    }
                ),
                input_tokens=200,
                output_tokens=60,
            )

    cfg = AdaptiveConfig(metrics_logging=False)
    service = AdaptiveAnswerService(cfg, Retriever(), Generator())
    db = BoundedWorker(4)
    runtime = SimpleNamespace(
        config=cfg,
        service=service,
        db=db,
        container=SimpleNamespace(
            collections_repository=lambda: SimpleNamespace(
                read_by_id=lambda _: SimpleNamespace(
                    vectordb_collection_name="load-fixture"
                )
            )
        ),
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=UUID(int=2), role="user"
    )
    app.dependency_overrides[get_runtime] = lambda: runtime
    return app, db


async def run(args):
    db = None
    transport = None
    if args.mock:
        app, db = mock_application()
        transport = httpx.ASGITransport(app=app)
    headers = {}
    if not args.mock:
        token = os.environ.get("ADAPTIVE_LOAD_TOKEN")
        if not token:
            raise SystemExit("Set ADAPTIVE_LOAD_TOKEN for a live test")
        headers["Authorization"] = "Bearer " + token
    results = {
        "mode": "mock_http" if args.mock else "live_http",
        "requests_per_strategy": args.requests,
        "concurrency": args.concurrency,
        "warmup": args.warmup,
        "note": "Closed-loop client latency; mock uses synthetic 5ms retrieval/10ms generation, not production capacity or answer quality.",
        "strategies": {},
    }
    try:
        async with httpx.AsyncClient(
            transport=transport,
            base_url=args.base_url,
            headers=headers,
            timeout=args.timeout,
        ) as client:
            for strategy in ("rag", "agentic_rag"):
                body = {
                    "query": args.query,
                    "filters": {"collection_id": str(args.collection_id)},
                    "options": {"force_strategy": strategy},
                }
                for _ in range(args.warmup):
                    response = await client.post("/v1/answer", json=body)
                    if response.status_code != 200:
                        raise RuntimeError(
                            f"Warmup failed: HTTP {response.status_code}"
                        )
                slots = asyncio.Semaphore(args.concurrency)
                rows = []

                async def request_one():
                    async with slots:
                        began = time.monotonic()
                        try:
                            response = await client.post("/v1/answer", json=body)
                            data = (
                                response.json() if response.status_code == 200 else {}
                            )
                            rows.append(
                                {
                                    "latency_ms": (time.monotonic() - began) * 1000,
                                    "http_error": response.status_code != 200,
                                    "metadata": data.get("metadata", {}),
                                }
                            )
                        except (httpx.HTTPError, ValueError):
                            rows.append(
                                {
                                    "latency_ms": (time.monotonic() - began) * 1000,
                                    "http_error": True,
                                    "metadata": {},
                                }
                            )

                start = time.monotonic()
                await asyncio.gather(*(request_one() for _ in range(args.requests)))
                elapsed = time.monotonic() - start
                latencies = [r["latency_ms"] for r in rows]
                stats = {
                    "p50_ms": percentile(latencies, 0.5),
                    "p95_ms": percentile(latencies, 0.95),
                    "p99_ms": percentile(latencies, 0.99),
                    "throughput_rps": len(rows) / elapsed,
                    "http_error_rate": sum(r["http_error"] for r in rows) / len(rows),
                    "degraded_or_abstained_rate": sum(
                        r["metadata"].get("status") in {"degraded", "abstained"}
                        for r in rows
                    )
                    / len(rows),
                }
                for field in (
                    "retrieval_calls",
                    "llm_calls",
                    "agent_steps",
                    "input_tokens",
                    "output_tokens",
                ):
                    stats["mean_" + field] = sum(
                        r["metadata"].get(field, 0) for r in rows
                    ) / len(rows)
                results["strategies"][strategy] = stats
                print(strategy, json.dumps(stats), flush=True)
    finally:
        if db:
            db.close()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--collection-id", type=UUID, default=UUID(int=1))
    parser.add_argument("--query", default="Compare product A and product B")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if min(args.requests, args.concurrency) < 1 or args.warmup < 0:
        parser.error("requests/concurrency must be positive; warmup cannot be negative")
    asyncio.run(run(args))
