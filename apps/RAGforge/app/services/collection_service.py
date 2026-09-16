import os
import re
import uuid
from collections import Counter

from loguru import logger

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.collections import Collections
from app.models.files import Files
from app.repositories import CollectionsRepository
from app.repositories.files_repository import FilesRepository
from app.schema.collection_schema import (
    CollectionDetail,
    CreateCollectionRequest,
    FindCollection,
    ListCollection,
    UpdateCollectionRequest,
)
from app.services.base_service import BaseService
from rag.qdrant.client import QdrantHttpClient


def slugify_collection_name(name: str) -> str:
    slug = name.strip().lower()
    slug = re.sub(r"[\s/]+", "_", slug)
    slug = re.sub(r"[^a-z0-9_-]", "", slug)
    slug = re.sub(r"_+", "_", slug).strip("_")
    if not slug:
        slug = "collection"
    return slug[:64]


class CollectionsService(BaseService):
    def __init__(
            self,
            collections_repository: CollectionsRepository,
            files_repository: FilesRepository,
            qdrant_client: QdrantHttpClient,
            embedding_model=None,
    ) -> None:
        self.collections_repository = collections_repository
        self.files_repository = files_repository
        self.qdrant_client = qdrant_client
        self.embedding_model = embedding_model
        super().__init__(collections_repository)

    def _unique_storage_id(self, base: str) -> str:
        candidate = base
        while self.collections_repository.get_by_storage_id(candidate):
            candidate = f"{base[:56]}_{uuid.uuid4().hex[:6]}"
        return candidate

    def list_collections(self, query: FindCollection) -> dict:
        result = self.collections_repository.list_with_file_count(query)
        result["data"] = [
            ListCollection(
                id=row.id,
                collection_name=row.collection_name,
                vectordb_collection_name=row.vectordb_collection_name,
                description=row.description,
                file_count=count,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row, count in result["data"]
        ]
        return result

    def create(self, payload: CreateCollectionRequest) -> Collections:
        name = payload.collection_name.strip()
        if not name:
            raise ValidationError(detail="Collection name is required")
        if self.collections_repository.get_by_name(name):
            raise ConflictError(detail="A collection with this name already exists.")
        storage_id = self._unique_storage_id(slugify_collection_name(name))
        collection = self.collections_repository.create(
            Collections(
                collection_name=name,
                description=payload.description,
                vectordb_collection_name=storage_id,
            )
        )
        try:
            self.qdrant_client.create_collection(collection_name=collection.vectordb_collection_name)
            return collection
        except Exception as e:
            self.collections_repository.delete_by_id(collection.id)
            raise ValidationError(detail=f"Collection creation failed: {str(e)}")

    def get_detail(self, collection_id: uuid.UUID) -> CollectionDetail:
        collection = self.collections_repository.read_by_id(collection_id)
        files = self.files_repository.list_by_collection(collection_id)
        counts = Counter(f.status for f in files)
        return CollectionDetail(
            id=collection.id,
            collection_name=collection.collection_name,
            vectordb_collection_name=collection.vectordb_collection_name,
            description=collection.description,
            file_count=len(files),
            created_at=collection.created_at,
            updated_at=collection.updated_at,
            file_status_counts={
                "pending": counts.get("pending", 0),
                "processing": counts.get("processing", 0),
                "completed": counts.get("completed", 0),
                "failed": counts.get("failed", 0),
            },
        )

    def update_collection(self, collection_id: uuid.UUID, payload: UpdateCollectionRequest) -> Collections:
        collection = self.collections_repository.read_by_id(collection_id)
        updates = {}
        if payload.collection_name is not None:
            name = payload.collection_name.strip()
            if not name:
                raise ValidationError(detail="Collection name is required")
            existing = self.collections_repository.get_by_name(name)
            if existing and existing.id != collection_id:
                raise ConflictError(detail="A collection with this name already exists.")
            updates["collection_name"] = name
        if payload.description is not None:
            updates["description"] = payload.description
        if not updates:
            return collection
        return self.collections_repository.update_fields(collection_id, updates)

    def get_documents(self, collection_name: str) -> list:
        collection = self.collections_repository.get_by_name(collection_name)
        if not collection:
            raise NotFoundError(detail=f"Collection '{collection_name}' not found")
        return self.qdrant_client.get_documents(collection_name=collection.vectordb_collection_name)

    def delete_collection_by_id(self, collection_id: uuid.UUID) -> None:
        collection = self.collections_repository.read_by_id(collection_id)
        files = self.files_repository.list_by_collection(collection_id)
        self.qdrant_client.delete_collection(collection_name=collection.vectordb_collection_name)
        for file_row in files:
            if file_row.file_path and os.path.exists(file_row.file_path):
                try:
                    os.remove(file_row.file_path)
                except OSError as e:
                    logger.warning("Could not delete file {}: {}", file_row.file_path, e)
        self.collections_repository.delete_by_id(collection.id)

    def delete_collection(self, collection_name: str) -> None:
        collection = self.collections_repository.get_by_name(collection_name)
        if not collection:
            raise NotFoundError(detail=f"Collection '{collection_name}' not found")
        self.delete_collection_by_id(collection.id)
