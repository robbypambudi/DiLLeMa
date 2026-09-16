import os
import uuid

from loguru import logger

from app.core.config import settings
from app.core.exceptions import ConflictError, ValidationError
from app.models.files import Files
from app.repositories.collections_repository import CollectionsRepository
from app.repositories.files_repository import FilesRepository
from app.schema.file_schema import CreateFileRequest
from app.services.base_service import BaseService
from app.utils.random_name_generator import random_name_generator
from rag.qdrant.client import QdrantHttpClient

ALLOWED_EXTENSIONS = {".pdf", ".txt", ".docx", ".md"}
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "text/plain",
    "text/markdown",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class FilesService(BaseService):
    def __init__(
            self,
            files_repository: FilesRepository,
            collections_repository: CollectionsRepository,
            qdrant_client: QdrantHttpClient,
    ) -> None:
        self.files_repository = files_repository
        self.collections_repository = collections_repository
        self.qdrant_client = qdrant_client
        super().__init__(files_repository)

    def _save_to_local(self, file, full_path):
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "wb") as f:
            f.write(file.file.read())
        return full_path

    def _validate_upload(self, filename: str, content_type: str | None) -> None:
        ext = os.path.splitext(filename or "")[1].lower()
        mime = (content_type or "").split(";")[0].strip().lower()
        if ext not in ALLOWED_EXTENSIONS and mime not in ALLOWED_MIME_TYPES:
            raise ValidationError(detail="File type is not allowed. Use PDF, Word, Markdown, or text.")

    def create(self, file: CreateFileRequest):
        filename = file.file.filename or "upload"
        self._validate_upload(filename, file.file.content_type)
        self.collections_repository.read_by_id(file.collection_id)

        file.file_name = filename
        ext = filename.split(".")[-1] if "." in filename else "bin"
        file.file_path = str(settings.FILE_PATH) + "/" + random_name_generator(ext)
        file.file_type = file.file.content_type or "application/octet-stream"
        file.file_size = file.file.size or 0

        try:
            self._save_to_local(file.file, file.file_path)
        except Exception as e:
            raise ValueError(f"Failed to save file: {e}")

        return self.files_repository.create(
            Files(
                file_name=file.file_name,
                file_path=file.file_path,
                file_type=file.file_type,
                file_size=file.file_size,
                collection_id=file.collection_id,
                status="pending",
            )
        )

    def update_status(self, file_id: uuid.UUID, status: str):
        self.files_repository.update_attr(file_id, "status", status)

    def retry(self, file_id: uuid.UUID) -> Files:
        file_row = self.files_repository.read_by_id(file_id)
        if file_row.status != "failed":
            raise ConflictError(detail="Only failed files can be retried.")
        collection = self.collections_repository.read_by_id(file_row.collection_id)
        self.qdrant_client.delete_points_by_file_id(
            collection.vectordb_collection_name,
            str(file_row.id),
        )
        return self.files_repository.update_fields(
            file_id,
            {
                "status": "pending",
                "processing_started_at": None,
                "processing_ended_at": None,
                "metadatas": {},
            },
        )

    def delete_file(self, file_id: uuid.UUID) -> None:
        file_row = self.files_repository.read_by_id(file_id)
        collection = self.collections_repository.read_by_id(file_row.collection_id)
        self.qdrant_client.delete_points_by_file_id(
            collection.vectordb_collection_name,
            str(file_row.id),
        )
        if file_row.file_path and os.path.exists(file_row.file_path):
            try:
                os.remove(file_row.file_path)
            except OSError as e:
                logger.warning("Could not delete file {}: {}", file_row.file_path, e)
        self.files_repository.delete_by_id(file_id)
