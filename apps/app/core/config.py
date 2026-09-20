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


# One .env for the whole repository (DiLLeMa/.env): the serving CLI, this API
# and the web app all read it. apps/.env is still honoured for installs that
# predate the move, but the repository file wins.
APPS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
REPO_ENV_FILE = os.path.join(os.path.dirname(APPS_DIR), ".env")
LEGACY_ENV_FILE = os.path.join(APPS_DIR, ".env")


def load_env() -> None:
    """Load the repository .env, then the legacy apps/.env for missing keys.

    Variables already set in the process environment always take precedence.
    """
    from dotenv import load_dotenv

    for path in (REPO_ENV_FILE, LEGACY_ENV_FILE):
        if not os.path.isfile(path):
            continue
        load_dotenv(path, override=False)
        if path == LEGACY_ENV_FILE:
            logging.warning(
                "Reading legacy %s; move its settings into %s", path, REPO_ENV_FILE
            )


load_env()


class Settings(BaseSettings):
    # load_env() has already exported both files; listed here as well so the
    # repository file is also what pydantic-settings resolves (later wins).
    model_config = SettingsConfigDict(
        env_file=(LEGACY_ENV_FILE, REPO_ENV_FILE),
        env_ignore_empty=True,
        extra="ignore",
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
    # Rewrite each question with the LLM (English translation + keywords)
    # before searching, unless the request says otherwise. It is what reaches
    # English passages from an Indonesian question; it costs one short LLM call.
    QUERY_AUGMENTATION: bool = True
    # Stop a question the corpus cannot answer before it costs the rewrite
    # call and a full rerank: the cheap probe below decides, not the LLM.
    SCOPE_GATE_ENABLED: bool = True
    # Hits from the probe search scored by the cross-encoder to decide scope.
    # Small on purpose -- the full rerank scores RETRIEVAL_CANDIDATES per query.
    SCOPE_PROBE_CANDIDATES: int = Field(default=8, ge=1, le=50)
    # Calibrated, then corrected by a real false rejection. The 29-question
    # sample suggested 0.1 was safe, but it held no aggregate questions: on the
    # live index "Apa saja matakuliah pada semester 3?" scores 0.0285 and was
    # refused as out of scope, while the highest genuinely out-of-scope pair
    # measured 0.0554. A legitimate question scoring BELOW an out-of-scope one
    # means no threshold separates the two classes, so this one is set to fail
    # open: the gate is a cost optimisation, and telling a user their valid
    # question is out of scope costs far more than reranking a hopeless one,
    # which the relevance floor and the grounded prompt still refuse to answer.
    # At 0.01: 0 false rejections that another branch does not already handle,
    # and 27 of 29 out-of-scope questions still stopped early.
    SCOPE_GATE_MIN_SCORE: float = Field(default=0.01, ge=0.0, le=1.0)
    # Above this, the question retrieves well on its own and the conversation
    # is left out of the search entirely. Carrying a topic into a question that
    # already has one is what drags a topic switch back to the old document.
    # Measured on real traffic: self-contained questions scored 0.418-0.999 and
    # the one real elliptic follow-up scored 0.007, so 0.3 sits in a wide gap.
    SCOPE_SELF_SUFFICIENT_SCORE: float = Field(default=0.3, ge=0.0, le=1.0)
    # A question that retrieves nothing alone but retrieves well once the
    # conversation's topic is restored: a real follow-up, worth a rewrite.
    # Below it the question is neither answerable nor a follow-up. Weakest of
    # the three: only one real follow-up exists in this deployment's history
    # (it scored 0.837), so re-run the calibration as conversations accumulate.
    SCOPE_FOLLOWUP_MIN_SCORE: float = Field(default=0.5, ge=0.0, le=1.0)
    # Rewrite follow-ups into standalone questions with the LLM. Off falls back
    # to carrying the earlier questions, which is weaker on topic switches.
    FOLLOWUP_REWRITE: bool = True

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
