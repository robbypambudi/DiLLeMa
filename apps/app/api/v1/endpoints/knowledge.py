"""Collection-scoped configuration, extraction jobs and evidence review."""

from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.config import settings
from app.core.container import Container
from app.core.dependencies import require_admin
from app.models.users import Users
from knowledge.contracts import KnowledgeProfile
from app.schema.knowledge_schema import ClaimStatus, ReviewRequest
from app.services.knowledge_service import KnowledgeService

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


def enabled():
    if not settings.KG_ENABLED:
        raise HTTPException(
            503,
            "Knowledge extraction is disabled. Set KG_ENABLED=true after applying migrations.",
        )


@router.get("/{collection_id}/profile")
@inject
def profile(
    collection_id: UUID,
    _admin: Users = Depends(require_admin),
    service: KnowledgeService = Depends(Provide[Container.knowledge_service]),
):
    return service.get_profile(collection_id)


@router.put("/{collection_id}/profile", dependencies=[Depends(enabled)])
@inject
def save_profile(
    collection_id: UUID,
    payload: KnowledgeProfile,
    _admin: Users = Depends(require_admin),
    service: KnowledgeService = Depends(Provide[Container.knowledge_service]),
):
    return service.save_profile(collection_id, payload)


@router.post(
    "/{collection_id}/files/{file_id}/extract",
    dependencies=[Depends(enabled)],
    status_code=202,
)
@inject
def extract(
    collection_id: UUID,
    file_id: UUID,
    _admin: Users = Depends(require_admin),
    service: KnowledgeService = Depends(Provide[Container.knowledge_service]),
):
    return service.extract(collection_id, file_id)


@router.get("/{collection_id}/jobs", dependencies=[Depends(enabled)])
@inject
def jobs(
    collection_id: UUID,
    _admin: Users = Depends(require_admin),
    service: KnowledgeService = Depends(Provide[Container.knowledge_service]),
):
    return service.list_jobs(collection_id)


@router.get("/{collection_id}/claims", dependencies=[Depends(enabled)])
@inject
def claims(
    collection_id: UUID,
    status: ClaimStatus = "pending",
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    _admin: Users = Depends(require_admin),
    service: KnowledgeService = Depends(Provide[Container.knowledge_service]),
):
    return service.list_claims(collection_id, status, offset, limit)


@router.patch("/{collection_id}/claims/{claim_id}", dependencies=[Depends(enabled)])
@inject
def review(
    collection_id: UUID,
    claim_id: UUID,
    payload: ReviewRequest,
    admin: Users = Depends(require_admin),
    service: KnowledgeService = Depends(Provide[Container.knowledge_service]),
):
    return service.review(collection_id, claim_id, payload, admin.id)


@router.get("/{collection_id}/graph", dependencies=[Depends(enabled)])
@inject
def graph(
    collection_id: UUID,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    _admin: Users = Depends(require_admin),
    service: KnowledgeService = Depends(Provide[Container.knowledge_service]),
):
    return service.graph(collection_id, offset, limit)
