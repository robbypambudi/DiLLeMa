"""Application composition and resource lifetime, separate from the ASGI entrypoint."""

import threading
from contextlib import asynccontextmanager
import time
from uuid import uuid4

from fastapi import FastAPI
from loguru import logger
from starlette.middleware.cors import CORSMiddleware

from app.api.v1.routes import routers as v1_routers
from app.api.v1.endpoints.answer import router as answer_router
from app.core.config import settings
from app.core.container import Container
from app.core.exception_handlers import register_exception_handlers
from app.services.adaptive.config import AdaptiveConfig
from app.services.adaptive.telemetry import Metrics, Trace


def _warm_reranker(container: Container) -> None:
    """Load and exercise the cross-encoder without holding up startup.

    The embedder is already warmed above; the reranker is the larger model and
    was not, so every restart made one user wait seconds for it to load -- and
    on a CPU deployment that is the slowest thing in the request. One tiny
    scoring pass also forces the first forward pass, where a lazily
    initialised backend does its remaining setup.

    It runs on a daemon thread: the API should answer metadata and uploads
    while a 568M model loads, and a process that exits meanwhile must not wait
    for it. A reranker that cannot load is logged and retried on demand, since
    retrieval already degrades gracefully when its probe is unavailable.
    """

    def warm() -> None:
        try:
            reranker = container.re_ranking()
            reranker.best_score([["warm", "warm"]], "warm")
            if getattr(reranker, "prefilter", None) is not None:
                logger.info("Rerank prefilter warmed")
            logger.info("Reranker warmed and ready")
        except Exception as exc:
            logger.warning(
                "Reranker unavailable at startup ({}); it will be retried on demand",
                type(exc).__name__,
            )

    threading.Thread(target=warm, name="warm-reranker", daemon=True).start()


def create_app(container: Container | None = None) -> FastAPI:
    container = container if container is not None else Container()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        logger.info("Starting up the application...")
        db = container.db()
        try:
            container.qdrant_client()
            container.embedding_model()
            _warm_reranker(container)
            container.auth_service().seed_admin_if_empty()
            yield
        finally:
            logger.info("Shutting down the application...")
            try:
                adaptive = getattr(_app.state, "adaptive_runtime", None)
                if adaptive is not None:
                    await adaptive.close()
            finally:
                db.close()
                container.unwire()

    app = FastAPI(
        title=settings.PROJECT_NAME,
        openapi_url=f"{settings.API_V1_STR}/openapi.json",
        version="2.1.0",
        lifespan=lifespan,
    )
    app.state.container = container
    app.state.adaptive_config = AdaptiveConfig()
    app.state.adaptive_metrics = Metrics(app.state.adaptive_config)

    @app.middleware("http")
    async def adaptive_request_trace(request, call_next):
        if request.url.path != "/v1/answer":
            return await call_next(request)
        request.state.adaptive_request_id = str(uuid4())
        request.state.adaptive_started = time.monotonic()
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request.state.adaptive_request_id
            return response
        finally:
            if not getattr(request.state, "adaptive_traced", False):
                trace = Trace(
                    app.state.adaptive_config,
                    request_id=request.state.adaptive_request_id,
                    started=request.state.adaptive_started,
                    status="rejected",
                )
                app.state.adaptive_metrics.record(trace)

    if settings.BACKEND_CORS_ORIGINS:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.all_cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.get("/")
    def root():
        return {"message": "Welcome to the FastAPI application!"}

    register_exception_handlers(app)
    app.include_router(v1_routers, prefix="/api", tags=["v1"])
    app.include_router(answer_router)
    return app
