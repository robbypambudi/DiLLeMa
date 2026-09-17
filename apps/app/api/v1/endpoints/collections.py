import uuid

from dependency_injector.wiring import Provide
from fastapi import APIRouter, Depends

from app.core.container import Container
from app.core.dependencies import get_current_user, require_admin
from app.core.middleware import inject
from app.models.users import Users
from app.schema.base_schema import BaseResponse, PaginatedResponse
from app.schema.collection_schema import (
    CollectionDetail,
    CreateCollectionRequest,
    FindCollection,
    ListCollection,
    UpdateCollectionRequest,
)
from app.services.collection_service import CollectionsService

router = APIRouter(prefix="/collection", tags=["collection"])


@router.get("", tags=["get"], response_model=PaginatedResponse[ListCollection])
@inject
def index(
        query: FindCollection = Depends(),
        service: CollectionsService = Depends(Provide[Container.collection_service])):
    collection = service.list_collections(query)
    return PaginatedResponse(
        message="Collections retrieved successfully",
        **collection
    )


@router.post("", tags=["create"], summary="Create a new collection", response_model=BaseResponse[ListCollection])
@inject
def create(
        request: CreateCollectionRequest,
        _admin: Users = Depends(require_admin),
        service: CollectionsService = Depends(Provide[Container.collection_service])):
    collection = service.create(request)
    return BaseResponse(
        message="Collection created successfully",
        data=ListCollection(
            id=collection.id,
            collection_name=collection.collection_name,
            vectordb_collection_name=collection.vectordb_collection_name,
            description=collection.description,
            file_count=0,
            created_at=collection.created_at,
            updated_at=collection.updated_at,
        )
    )


@router.get("/{collection_id}", tags=["get"], response_model=BaseResponse[CollectionDetail])
@inject
def get_collection_by_id(
        collection_id: uuid.UUID,
        _user: Users = Depends(get_current_user),
        service: CollectionsService = Depends(Provide[Container.collection_service])):
    return BaseResponse(
        message="Collection retrieved successfully",
        data=service.get_detail(collection_id),
    )


@router.patch("/{collection_id}", tags=["update"], response_model=BaseResponse[CollectionDetail])
@inject
def update_collection(
        collection_id: uuid.UUID,
        request: UpdateCollectionRequest,
        _admin: Users = Depends(require_admin),
        service: CollectionsService = Depends(Provide[Container.collection_service])):
    service.update_collection(collection_id, request)
    return BaseResponse(
        message="Collection updated successfully",
        data=service.get_detail(collection_id),
    )


@router.delete("/{collection_id}", tags=["delete"])
@inject
def delete_collection_by_id(
        collection_id: uuid.UUID,
        _admin: Users = Depends(require_admin),
        service: CollectionsService = Depends(Provide[Container.collection_service])):
    service.delete_collection_by_id(collection_id)
    return BaseResponse(
        message="Collection deleted successfully",
        data=None
    )


@router.get("/by-name/{collection_name}", tags=["get"])
@inject
def get_collection_documents(
        collection_name: str,
        _admin: Users = Depends(require_admin),
        service: CollectionsService = Depends(Provide[Container.collection_service])):
    collection = service.get_documents(collection_name=collection_name)
    return BaseResponse(
        message="Collection retrieved successfully",
        data=collection
    )


@router.delete("/by-name/{collection_name}", tags=["delete"])
@inject
def delete_collection_by_name(
        collection_name: str,
        _admin: Users = Depends(require_admin),
        service: CollectionsService = Depends(Provide[Container.collection_service])):
    service.delete_collection(collection_name=collection_name)
    return BaseResponse(
        message="Collection deleted successfully",
        data=None
    )
