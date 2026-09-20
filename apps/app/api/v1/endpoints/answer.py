"""Authenticated JSON answering; no dependency exception text in responses."""

import asyncio
import time
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.responses import Response

from app.core.dependencies import get_current_user, require_admin
from app.services.adaptive.contracts import AnswerRequest, AnswerResponse
from app.services.adaptive.runtime import AdaptiveRuntime
from app.services.adaptive.telemetry import Trace

router = APIRouter(prefix="/v1", tags=["adaptive-answer"])


async def with_disconnect(request, operation, poll_ms):
    """HTTP disconnect cancels pending network IO and the bounded agent loop."""

    stopped = asyncio.Event()

    async def disconnected():
        while not stopped.is_set():
            if await request.is_disconnected():
                return
            if stopped.is_set():
                return
            await asyncio.sleep(poll_ms / 1000)

    task = asyncio.create_task(operation)
    monitor = asyncio.create_task(disconnected())
    try:
        done, _ = await asyncio.wait(
            [task, monitor], return_when=asyncio.FIRST_COMPLETED
        )
        if task in done:
            return await task
        raise asyncio.CancelledError()
    finally:
        stopped.set()
        task.cancel()
        monitor.cancel()
        await asyncio.gather(task, monitor, return_exceptions=True)


async def get_runtime(request: Request):
    runtime = getattr(request.app.state, "adaptive_runtime", None)
    if runtime is None:
        runtime = AdaptiveRuntime(
            request.app.state.container,
            request.app.state.adaptive_config,
            request.app.state.adaptive_metrics,
        )
        request.app.state.adaptive_runtime = runtime
    return runtime


@router.post("/answer", response_model=AnswerResponse)
async def answer(
    payload: AnswerRequest,
    request: Request,
    user=Depends(get_current_user),
    runtime=Depends(get_runtime),
):
    trace = Trace(
        runtime.config,
        request_id=getattr(request.state, "adaptive_request_id", str(uuid4())),
        started=getattr(request.state, "adaptive_started", time.monotonic()),
    )
    request.state.adaptive_traced = True
    service_called = False
    try:
        async with asyncio.timeout(trace.remaining_ms / 1000):
            # Do not let user input select a physical Qdrant collection name.
            filters = payload.filters.model_copy(deep=True)
            if payload.conversation_id is not None:
                conversation = await runtime.db.run(
                    runtime.container.conversations_repository().answer_scope,
                    payload.conversation_id,
                    user.id,
                )
                collection_id = conversation.get("collection_id")
                if collection_id is None or (
                    filters.collection_id and filters.collection_id != collection_id
                ):
                    raise HTTPException(
                        422, "Conversation collection is unavailable or does not match"
                    )
                filters.collection_id = collection_id
                # Conversation identifies scope only in v1. Earlier generated
                # answers are never silently promoted to factual evidence.
            collection_name = ""
            if filters.collection_id:
                collection = await runtime.db.run(
                    runtime.container.collections_repository().read_by_id,
                    filters.collection_id,
                )
                collection_name = collection.vectordb_collection_name
            scoped = payload.model_copy(update={"filters": filters})
            service_called = True
            result = await with_disconnect(
                request,
                runtime.service.answer(
                    scoped, collection_name=collection_name, trace=trace
                ),
                runtime.config.latency.disconnect_poll_ms,
            )
        return result
    except asyncio.CancelledError:
        trace.status = "cancelled"
        raise
    except HTTPException:
        trace.status = "rejected"
        raise
    except Exception as exc:
        # Repository NotFoundError is an HTTPException in the existing app;
        # other failures are opaque and carry a request ID for operators.
        trace.status = "unavailable"
        trace.error("scope_resolution", isinstance(exc, TimeoutError))
        raise HTTPException(
            503,
            {
                "message": "Answer service temporarily unavailable",
                "request_id": trace.request_id,
            },
        ) from None
    finally:
        if not service_called:
            runtime.service.metrics.record(trace)


@router.get("/metrics", include_in_schema=False)
async def metrics(_admin=Depends(require_admin), runtime=Depends(get_runtime)):
    return Response(
        runtime.service.metrics.render(), media_type="text/plain; version=0.0.4"
    )
