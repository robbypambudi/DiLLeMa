import logging
import os
import secrets
from typing import Any, Literal, Annotated, ClassVar

from pydantic import AnyUrl, BeforeValidator, computed_field, HttpUrl, Field
from pydantic_core import MultiHostUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


def parse_cors(v: Any) -> list[str] | str:
    if isinstance(v, str) and not v.startswith("["):
        return [i.strip() for i in v.split(",")]
    elif isinstance(v, list | str):
        return v
    raise ValueError(v)


def load_env() -> None:
    """
    Load environment variables from .env file
    """
    from dotenv import load_dotenv
    import os

    env_path = os.path.join(os.path.dirname(__file__), "../../.env")
    load_dotenv(env_path)
    logging.log(1, f"Loaded environment variables from {env_path}")


load_env()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="../../.env", env_ignore_empty=True, extra="ignore"
    )

    FILE_PATH: ClassVar["str"] = os.path.dirname(__file__) + "/../files"

    API_V1_STR: str = "/app"
    SECRET_KEY: str = secrets.token_urlsafe(32)
    JWT_EXPIRE_SECONDS: int = 28800
    ADMIN_EMAIL: str | None = None
    ADMIN_PASSWORD: str | None = None
    FRONTEND_HOST: str = "http://localhost:3000"
    ENVIRONMENT: Literal["local", "staging", "production"] = "local"

    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
    HUGGINGFACE_API_KEY: str = os.getenv("HUGGINGFACE_API_KEY", "")

    BACKEND_CORS_ORIGINS: Annotated[list[AnyUrl] | str, BeforeValidator(parse_cors)] = [
        "http://localhost:8501",
        "http://localhost:3000",
    ]

    @computed_field
    @property
    def all_cors_origins(self) -> list[str]:
        return [str(origin).rstrip("/") for origin in self.BACKEND_CORS_ORIGINS] + [
            self.FRONTEND_HOST
        ]

    PROJECT_NAME: str = "DiLLeMa"
    SENTRY_DSN: HttpUrl | None = None
    POSTGRES_SERVER: str
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str

    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    EMBED_MODEL_NAME: str = "intfloat/multilingual-e5-base"
    RERANK_MODEL_NAME: str = "BAAI/bge-reranker-v2-m3"
    # Cross-encoder relevance floor (sigmoid, 0..1). Evidence below this is
    # dropped, so an out-of-corpus question gets "not enough information"
    # instead of an answer built on the least-bad chunk. Calibrate per corpus.
    RERANK_MIN_SCORE: float = Field(default=0.05, ge=0.0, le=1.0)
    # Hybrid-search hits per query handed to the reranker. A term that recurs
    # across a long document (an acronym, a programme name) fills a small pool
    # with passing mentions before the passage that defines it.
    RETRIEVAL_CANDIDATES: int = Field(default=40, ge=5, le=200)
    # Evidence scoring below this fraction of the best match is not sent to
    # the generator: a small model reads every page it is given as an answer,
    # so a weak neighbour becomes a wrong fact. 0 disables the cut.
    RERANK_RELATIVE_FLOOR: float = Field(default=0.5, ge=0.0, le=1.0)

    KG_ENABLED: bool = False
    KG_LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "http://localhost:8000/v1")
    KG_LLM_API_KEY: str = os.getenv("LLM_API_KEY", "any")
    KG_LLM_MODEL: str = os.getenv("LLM_MODEL", "qwen-7b")
    KG_MAX_CHUNKS: int = Field(default=200, ge=1, le=2000)
    KG_MAX_OUTPUT_TOKENS: int = Field(default=4096, ge=256, le=16384)
    KG_RETRIEVAL_LIMIT: int = Field(default=12, ge=1, le=64)
    KG_EXTRACTION_FORMAT: Literal["text", "json_schema"] = "text"

    @computed_field
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> MultiHostUrl:
        return MultiHostUrl.build(
            scheme="postgresql",
            host=self.POSTGRES_SERVER,
            port=self.POSTGRES_PORT,
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            path=f"{self.POSTGRES_DB}",
        )


settings = Settings()  # type: ignore
