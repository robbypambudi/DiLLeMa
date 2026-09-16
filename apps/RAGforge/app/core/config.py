import logging
import os
import secrets
from typing import Any, Literal, Annotated, ClassVar

from pydantic import (AnyUrl, BeforeValidator, computed_field, HttpUrl)
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

    env_path = os.path.join(os.path.dirname(__file__), '../../.env')
    load_dotenv(env_path)
    logging.log(1, f"Loaded environment variables from {env_path}")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file='../../.env',
        env_ignore_empty=True,
        extra='ignore'
    )

    FILE_PATH: ClassVar['str'] = os.path.dirname(__file__) + "/../files"

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

    BACKEND_CORS_ORIGINS: Annotated[
        list[AnyUrl] | str, BeforeValidator(parse_cors)
    ] = [
        "http://localhost:8501",
        "http://localhost:3000",
    ]

    @computed_field
    @property
    def all_cors_origins(self) -> list[str]:
        return [str(origin).rstrip("/") for origin in self.BACKEND_CORS_ORIGINS] + [self.FRONTEND_HOST]

    PROJECT_NAME: str = "RAG API"
    SENTRY_DSN: HttpUrl | None = None
    POSTGRES_SERVER: str
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str

    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333

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


load_env()
settings = Settings()  # type: ignore
