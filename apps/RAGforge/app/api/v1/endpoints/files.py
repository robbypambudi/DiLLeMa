import uuid

from dependency_injector.wiring import Provide
from fastapi import APIRouter, Depends, BackgroundTasks

from app.core.container import Container
from app.core.middleware import inject
from app.pipeline.pipeline_service import PipelineService
from app.schema.base_schema import BaseResponse
from app.schema.file_schema import FindFiles, CreateFileRequest, ResponseFiles
from app.services.files_service import FilesService

router = APIRouter(prefix="/files", tags=["files"])


@router.get("", tags=["get"])
@inject
def index(
        query: FindFiles = Depends(),
        service: FilesService = Depends(Provide[Container.files_service])
):
    """
    Get all files
    """
    return service.get_list(query)


def run_pipeline_with_error_handling(pipeline_service, files):
    """Wrapper to handle pipeline errors in background tasks"""
    try:
        pipeline_service.run_pipeline(files)
    except Exception as e:
        from loguru import logger
        logger.error(f"Background pipeline failed for file {files.id}: {e}")
        logger.exception("Full traceback:")

# Create a new file
@router.post("", tags=["post"], response_model=BaseResponse[ResponseFiles])
@inject
def create(
        background_tasks: BackgroundTasks,
        payload: CreateFileRequest = Depends(),
        service: FilesService = Depends(Provide[Container.files_service]),
        pipeline_service: PipelineService = Depends(Provide[Container.pipeline_service])
):
    """
    Create a new file
    """
    response = service.create(payload)

    # Add the file to the pipeline with error handling
    background_tasks.add_task(
        run_pipeline_with_error_handling,
        pipeline_service,
        response
    )

    return BaseResponse(
        message="File created successfully",
        data=response
    )


@router.delete("/{file_id}", tags=["delete"])
@inject
def delete(
        file_id: uuid.UUID,
        service: FilesService = Depends(Provide[Container.files_service])
):
    """
    Delete a file
    """
    return service.remove_by_id(file_id)


@router.get("/{file_id}", tags=["get"])
@inject
def get_file(
        file_id: uuid.UUID,
        service: FilesService = Depends(Provide[Container.files_service])
):
    """
    Get a file by ID
    """
    file = service.get_by_id(file_id)

    return BaseResponse(
        message="File retrieved successfully",
        data=file
    )
