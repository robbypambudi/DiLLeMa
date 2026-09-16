from contextlib import asynccontextmanager
from urllib.request import Request

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from loguru import logger
from pydantic import ValidationError
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from app.api.v1.routes import routers as v1_routers
from app.core.config import settings
from app.core.container import Container
from app.utils.class_object import singleton


@singleton
class App:
    def __init__(self):
        # Initialize the app
        self.container = Container()

        self.app = FastAPI(
            title=settings.PROJECT_NAME,
            openapi_url=f"{settings.API_V1_STR}/openapi.json",
            version="2.1.0",
            lifespan=self.lifespan,
        )

        if settings.BACKEND_CORS_ORIGINS:
            self.app.add_middleware(
                CORSMiddleware,
                allow_origins=settings.all_cors_origins,
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )

        @self.app.get("/")
        def root():
            return {"message": "Welcome to the FastAPI application!"}

        # Handle request body validation (e.g., missing fields, wrong types)
        @self.app.exception_handler(RequestValidationError)
        async def request_validation_exception_handler(request: Request, exc: RequestValidationError):
            print(exc.errors())
            errors = [
                {
                    "field": ".".join(str(loc) for loc in err["loc"][1:]),  # skip 'body'
                    "message": err["msg"]
                }
                for err in exc.errors()
            ]
            return JSONResponse(
                status_code=422,
                content={"errors": errors}
            )

        @self.app.exception_handler(ValidationError)
        async def pydantic_validation_exception_handler(request: Request, exc: ValidationError):
            print(exc.errors())
            errors = [
                {
                    "field": ".".join(str(loc) for loc in err["loc"]),
                    "message": err["msg"]
                }
                for err in exc.errors()
            ]
            return JSONResponse(
                status_code=422,
                content={"errors": errors}
            )

        # include routers
        self.app.include_router(v1_routers, prefix='/api', tags=["v1"])

    @asynccontextmanager
    async def lifespan(self, app: FastAPI):
        """
        Application startup and shutdown events.
        """
        logger.info("Starting up the application...")
        self.db = self.container.db()
        self.qdrant = self.container.qdrant_client()
        self.model = self.container.embedding_model()
        yield
        # Shutdown
        logger.info("Shutting down the application...")
        self.db.close()


app_creator = App()
app = app_creator.app
