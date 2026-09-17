"""Collection-scoped configuration, extraction jobs and evidence review."""

from typing import Literal
from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.container import Container
from app.core.dependencies import require_admin
from app.models.users import Users
from knowledge.contracts import KnowledgeProfile
from knowledge.repository import KnowledgeRepository

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


def enabled():
    if not settings.KG_ENABLED:
        raise HTTPException(
            503,
            "Knowledge extraction is disabled. Set KG_ENABLED=true after applying migrations.",
        )


class ReviewRequest(BaseModel):
    status: Literal["approved", "rejected"]
    note: str = Field(default="", max_length=2000)


@router.get("/{collection_id}/profile")
@inject
def profile(
    collection_id: UUID,
    _admin: Users = Depends(require_admin),
    repository: KnowledgeRepository = Depends(Provide[Container.knowledge_repository]),
):
    if not settings.KG_ENABLED:
        return {"available": False, "profile": KnowledgeProfile().model_dump()}
    result = repository.get_profile(collection_id)
    return {
        "available": True,
        "revision": result.revision,
        "profile": result.model_dump(),
    }


@router.put("/{collection_id}/profile", dependencies=[Depends(enabled)])
@inject
def save_profile(
    collection_id: UUID,
    payload: KnowledgeProfile,
    _admin: Users = Depends(require_admin),
    repository: KnowledgeRepository = Depends(Provide[Container.knowledge_repository]),
):
    try:
        result = repository.save_profile(collection_id, payload)
        return {"revision": result.revision, "profile": result.model_dump()}
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


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
    repository: KnowledgeRepository = Depends(Provide[Container.knowledge_repository]),
):
    try:
        job = repository.enqueue(collection_id, file_id)
        return {"id": job["id"], "file_id": job["file_id"], "status": job["status"]}
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/{collection_id}/jobs", dependencies=[Depends(enabled)])
@inject
def jobs(
    collection_id: UUID,
    _admin: Users = Depends(require_admin),
    repository: KnowledgeRepository = Depends(Provide[Container.knowledge_repository]),
):
    return {"data": repository.list_jobs(collection_id)}


@router.get("/{collection_id}/claims", dependencies=[Depends(enabled)])
@inject
def claims(
    collection_id: UUID,
    status: Literal["pending", "approved", "rejected"] = "pending",
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    _admin: Users = Depends(require_admin),
    repository: KnowledgeRepository = Depends(Provide[Container.knowledge_repository]),
):
    return {"data": repository.list_claims(collection_id, status, offset, limit)}


@router.patch("/{collection_id}/claims/{claim_id}", dependencies=[Depends(enabled)])
@inject
def review(
    collection_id: UUID,
    claim_id: UUID,
    payload: ReviewRequest,
    admin: Users = Depends(require_admin),
    repository: KnowledgeRepository = Depends(Provide[Container.knowledge_repository]),
):
    try:
        repository.review(
            collection_id, claim_id, payload.status, admin.id, payload.note
        )
        return {"id": claim_id, "status": payload.status}
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/{collection_id}/graph", dependencies=[Depends(enabled)])
@inject
def graph(
    collection_id: UUID,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    _admin: Users = Depends(require_admin),
    repository: KnowledgeRepository = Depends(Provide[Container.knowledge_repository]),
):
    rows = repository.list_claims(collection_id, "approved", offset, limit)
    nodes = {}
    edges = []
    for row in rows:
        for role in ("subject", "object"):
            nodes[str(row[f"{role}_id"])] = {
                "id": row[f"{role}_id"],
                "label": row[f"{role}_name"],
            }
        edges.append(
            {
                key: row[key]
                for key in (
                    "id",
                    "subject_id",
                    "object_id",
                    "predicate",
                    "qualifiers",
                    "quote",
                    "file_name",
                    "page",
                    "chunk_id",
                )
            }
        )
    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "offset": offset,
        "limit": limit,
    }
