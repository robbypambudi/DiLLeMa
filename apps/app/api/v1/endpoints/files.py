import uuid

from dependency_injector.wiring import Provide
from fastapi import APIRouter, BackgroundTasks, Depends
from loguru import logger

from app.core.container import Container
from app.core.dependencies import get_current_user, require_admin
from app.core.middleware import inject
from app.models.users import Users
from app.pipeline.pipeline_service import PipelineService
from app.schema.base_schema import BaseResponse, PaginatedResponse
from app.schema.file_schema import CreateFileRequest, FindFiles, ResponseFiles
from app.services.files_service import FilesService

router = APIRouter(prefix="/files", tags=["files"])


@router.get("", tags=["get"], response_model=PaginatedResponse[ResponseFiles])
@inject
def index(
        query: FindFiles = Depends(),
        _user: Users = Depends(get_current_user),
        service: FilesService = Depends(Provide[Container.files_service])
):
    result = service.get_list(query)
    return PaginatedResponse(
        message="Files retrieved successfully",
        **result,
    )


def run_pipeline_with_error_handling(pipeline_service, files):
    try:
        pipeline_service.run_pipeline(files)
    except Exception as e:
        logger.error(f"Background pipeline failed for file {files.id}: {e}")
        logger.exception("Full traceback:")


@router.post("", tags=["post"], response_model=BaseResponse[ResponseFiles])
@inject
def create(
        background_tasks: BackgroundTasks,
        payload: CreateFileRequest = Depends(),
        _admin: Users = Depends(require_admin),
        service: FilesService = Depends(Provide[Container.files_service]),
        pipeline_service: PipelineService = Depends(Provide[Container.pipeline_service])
):
    response = service.create(payload)
    background_tasks.add_task(
        run_pipeline_with_error_handling,
        pipeline_service,
        response
    )
    return BaseResponse(
        message="File created successfully",
        data=response
    )


@router.post("/{file_id}/retry", tags=["post"], response_model=BaseResponse[ResponseFiles])
@inject
def retry(
        file_id: uuid.UUID,
        background_tasks: BackgroundTasks,
        _admin: Users = Depends(require_admin),
        service: FilesService = Depends(Provide[Container.files_service]),
        pipeline_service: PipelineService = Depends(Provide[Container.pipeline_service])
):
    response = service.retry(file_id)
    background_tasks.add_task(
        run_pipeline_with_error_handling,
        pipeline_service,
        response
    )
    return BaseResponse(
        message="File queued for retry",
        data=response
    )


@router.delete("/{file_id}", tags=["delete"])
@inject
def delete(
        file_id: uuid.UUID,
        _admin: Users = Depends(require_admin),
        service: FilesService = Depends(Provide[Container.files_service])
):
    service.delete_file(file_id)
    return BaseResponse(
        message="File deleted successfully",
        data=None,
    )


@router.get("/{file_id}", tags=["get"], response_model=BaseResponse[ResponseFiles])
@inject
def get_file(
        file_id: uuid.UUID,
        _user: Users = Depends(get_current_user),
        service: FilesService = Depends(Provide[Container.files_service])
):
    file = service.get_by_id(file_id)
    return BaseResponse(
        message="File retrieved successfully",
        data=file
    )
