"""Background task boundary for document ingestion."""

from loguru import logger

from app.models.files import Files
from app.pipeline.pipeline_service import PipelineService


def run_pipeline_with_error_handling(service: PipelineService, document: Files) -> None:
    try:
        service.run_pipeline(document)
    except Exception:
        # PipelineService persists the failed status before propagating errors.
        logger.exception("Background pipeline failed for file {}", document.id)
