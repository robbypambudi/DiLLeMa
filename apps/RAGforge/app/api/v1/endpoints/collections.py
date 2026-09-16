from dependency_injector.wiring import Provide
from fastapi import APIRouter, Depends

from app.core.container import Container
from app.core.middleware import inject
from app.schema.base_schema import BaseResponse, PaginatedResponse
from app.schema.collection_schema import FindCollection, CreateCollectionRequest, BaseCollection, ListCollection
from app.services.collection_service import CollectionsService

router = APIRouter(prefix="/collection", tags=["collection"])


@router.get("", tags=["get"], response_model=PaginatedResponse[ListCollection])
@inject
def index(
        query: FindCollection = Depends(),
        service: CollectionsService = Depends(Provide[Container.collection_service])):
    """
    Get a list of collections
    """
    collection = service.get_list(query)
    return PaginatedResponse(
        message="Collections retrieved successfully",
        **collection
    )


@router.post("", tags=["create"], summary="Create a new collection", response_model=BaseResponse[BaseCollection])
@inject
def create(request: CreateCollectionRequest = Depends(),
           service: CollectionsService = Depends(Provide[Container.collection_service])):
    collection = service.create(request)

    return BaseResponse(
        message="Collection created successfully",
        data=collection
    )


@router.get("/{collection_name}", tags=["get"])
@inject
def get_collection(
        collection_name: str,
        service: CollectionsService = Depends(Provide[Container.collection_service])):
    """
    Get a collection by name
    """
    collection = service.get_documents(collection_name=collection_name)

    return BaseResponse(
        message="Collection retrieved successfully",
        data=collection
    )


@router.delete("/{collection_name}", tags=["delete"])
@inject
def delete_collection(
        collection_name: str,
        service: CollectionsService = Depends(Provide[Container.collection_service])):
    """
    Delete a collection by name
    """
    service.delete_collection(collection_name=collection_name)

    return BaseResponse(
        message="Collection deleted successfully",
        data=None
    )
