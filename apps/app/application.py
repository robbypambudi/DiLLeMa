"""Application composition and resource lifetime, separate from the ASGI entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger
from starlette.middleware.cors import CORSMiddleware

from app.api.v1.routes import routers as v1_routers
from app.core.config import settings
from app.core.container import Container
from app.core.exception_handlers import register_exception_handlers


def create_app(container: Container | None = None) -> FastAPI:
    container = container if container is not None else Container()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        logger.info("Starting up the application...")
        db = container.db()
        try:
            container.qdrant_client()
            container.embedding_model()
            container.auth_service().seed_admin_if_empty()
            yield
        finally:
            logger.info("Shutting down the application...")
            db.close()
            container.unwire()

    app = FastAPI(
        title=settings.PROJECT_NAME,
        openapi_url=f"{settings.API_V1_STR}/openapi.json",
        version="2.1.0",
        lifespan=lifespan,
    )
    app.state.container = container
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
    return app
