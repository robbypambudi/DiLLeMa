"""Knowledge use cases; routes only validate and dispatch HTTP requests."""

from uuid import UUID

from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError
from app.schema.knowledge_schema import ClaimStatus, ReviewRequest
from knowledge.contracts import KnowledgeProfile
from knowledge.repository import KnowledgeRepository


class KnowledgeService:
    def __init__(self, repository: KnowledgeRepository):
        self.repository = repository

    def get_profile(self, collection_id: UUID) -> dict:
        if not settings.KG_ENABLED:
            return {"available": False, "profile": KnowledgeProfile().model_dump()}
        result = self.repository.get_profile(collection_id)
        return {
            "available": True,
            "revision": result.revision,
            "profile": result.model_dump(),
        }

    def save_profile(self, collection_id: UUID, payload: KnowledgeProfile) -> dict:
        try:
            result = self.repository.save_profile(collection_id, payload)
        except LookupError as exc:
            raise NotFoundError(str(exc)) from exc
        return {"revision": result.revision, "profile": result.model_dump()}

    def extract(self, collection_id: UUID, file_id: UUID) -> dict:
        try:
            job = self.repository.enqueue(collection_id, file_id)
        except LookupError as exc:
            raise NotFoundError(str(exc)) from exc
        except ValueError as exc:
            raise ConflictError(str(exc)) from exc
        return {key: job[key] for key in ("id", "file_id", "status")}

    def list_jobs(self, collection_id: UUID) -> dict:
        return {"data": self.repository.list_jobs(collection_id)}

    def list_claims(
        self, collection_id: UUID, status: ClaimStatus, offset: int, limit: int
    ) -> dict:
        return {
            "data": self.repository.list_claims(collection_id, status, offset, limit)
        }

    def review(
        self,
        collection_id: UUID,
        claim_id: UUID,
        payload: ReviewRequest,
        admin_id: UUID,
    ) -> dict:
        try:
            self.repository.review(
                collection_id, claim_id, payload.status, admin_id, payload.note
            )
        except LookupError as exc:
            raise NotFoundError(str(exc)) from exc
        return {"id": claim_id, "status": payload.status}

    def graph(self, collection_id: UUID, offset: int, limit: int) -> dict:
        rows = self.repository.list_claims(collection_id, "approved", offset, limit)
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
