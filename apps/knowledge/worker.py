"""Run with: python -m knowledge.worker [--once]. Jobs survive process restarts."""

import argparse
import hashlib
import json
import logging
import time
from contextlib import contextmanager
from pathlib import Path

from knowledge.contracts import Extraction, KnowledgeProfile, PIPELINE_VERSION
from knowledge.documents import chunks_fingerprint, parse_document, parser_provenance
from knowledge.extraction import KnowledgeExtractor, PROMPT_VERSION

logger = logging.getLogger(__name__)


class KnowledgeWorker:
    def __init__(self, repository, extractor, max_chunks=200, lease_seconds=300):
        self.repository = repository
        self.extractor = extractor
        self.max_chunks = max_chunks
        self.lease_seconds = lease_seconds

    def process_next(self):
        job = self.repository.claim_job(lease_seconds=self.lease_seconds)
        if not job:
            return "idle"
        try:
            file = self.repository.file_for_job(job)
            profile = KnowledgeProfile.model_validate(job["profile"])
            content_hash, chunks = parse_document(
                file["file_path"], file["file_type"], file["id"], self.max_chunks
            )
            provenance = dict(
                pipeline=PIPELINE_VERSION,
                prompt=PROMPT_VERSION,
                model=self.extractor.model,
                max_tokens=self.extractor.max_tokens,
                output_format=getattr(self.extractor, "output_format", "text"),
                content_hash=content_hash,
                parser=parser_provenance(file["file_path"], file["file_type"]),
                chunks_fingerprint=chunks_fingerprint(chunks),
                schema_revision=profile.revision,
            )
            fingerprint = hashlib.sha256(
                json.dumps(provenance, sort_keys=True).encode()
            ).hexdigest()
            checkpoint = job["checkpoint"]
            if checkpoint.get("fingerprint") != fingerprint:
                checkpoint = {"fingerprint": fingerprint, "results": {}}
            results = []
            self.repository.checkpoint(job, checkpoint, self.lease_seconds)
            for chunk in chunks:
                key = str(chunk.id)
                if key in checkpoint["results"]:
                    result = Extraction.model_validate(checkpoint["results"][key])
                else:
                    result = self.extractor.extract(chunk, profile)
                    checkpoint["results"][key] = result.model_dump()
                results.append(result)
                self.repository.checkpoint(job, checkpoint, self.lease_seconds)
            if (
                hashlib.sha256(Path(file["file_path"]).read_bytes()).hexdigest()
                != content_hash
            ):
                raise ValueError("Source file changed during extraction; enqueue again")
            self.repository.publish(job, content_hash, chunks, results, provenance)
            return "completed"
        except Exception as exc:
            # Provider exception messages can contain endpoints/credentials; keep them out of job APIs.
            message = (
                str(exc)
                if isinstance(exc, (ValueError, LookupError))
                else f"Extraction failed ({type(exc).__name__}); check worker configuration"
            )
            self.repository.fail(job, message)
            logger.warning("Knowledge job %s failed: %s", job["id"], type(exc).__name__)
            return "failed"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--once", action="store_true", help="Process at most one queued job and exit"
    )
    parser.add_argument("--poll-seconds", type=float, default=3)
    args = parser.parse_args()
    if args.poll_seconds <= 0:
        parser.error("--poll-seconds must be positive")

    from openai import OpenAI
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.core.config import settings
    from knowledge.repository import KnowledgeRepository

    if not settings.KG_ENABLED:
        parser.error(
            "Set KG_ENABLED=true and apply database migrations before starting the worker"
        )
    engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI), pool_pre_ping=True)
    sessions = sessionmaker(bind=engine)

    @contextmanager
    def session_factory():
        with sessions() as session:
            yield session

    client = OpenAI(
        base_url=settings.KG_LLM_BASE_URL,
        api_key=settings.KG_LLM_API_KEY,
        timeout=120,
        max_retries=0,
    )
    worker = KnowledgeWorker(
        KnowledgeRepository(session_factory),
        KnowledgeExtractor(
            client,
            settings.KG_LLM_MODEL,
            settings.KG_MAX_OUTPUT_TOKENS,
            settings.KG_EXTRACTION_FORMAT,
        ),
        max_chunks=settings.KG_MAX_CHUNKS,
    )
    logging.basicConfig(level=logging.INFO)
    try:
        while True:
            result = worker.process_next()
            if args.once:
                return 1 if result == "failed" else 0
            if result == "idle":
                time.sleep(args.poll_seconds)
    except KeyboardInterrupt:
        return 0
    finally:
        client.close()
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
