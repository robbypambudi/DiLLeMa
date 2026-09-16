import uuid

from app.core.config import settings
from app.models.files import Files
from app.repositories.files_repository import FilesRepository
from app.schema.file_schema import CreateFileRequest
from app.services.base_service import BaseService
from app.utils.random_name_generator import random_name_generator


class FilesService(BaseService):
    """
    Files service class for handling file-related operations.
    """

    def __init__(self, files_repository: FilesRepository) -> None:
        self.files_repository = files_repository
        super().__init__(files_repository)

    def _save_to_local(self, file, full_path):
        """
        Save the file to the local filesystem.
        """
        with open(full_path, "wb") as f:
            f.write(file.file.read())
        return full_path

    def create(self, file: CreateFileRequest):
        """
        Create a new file.
        """
        # Generate random file name
        file.file_name = file.file.filename
        file.file_path = str(settings.FILE_PATH) + "/" + random_name_generator(file.file.filename.split(".")[-1])
        file.file_type = file.file.content_type
        file.file_size = file.file.size

        # Save file to local storage
        try:
            self._save_to_local(file.file, file.file_path)
        except Exception as e:
            raise ValueError(f"Failed to save file: {e}")

        files = self.files_repository.create(
            Files(
                file_name=file.file_name,
                file_path=file.file_path,
                file_type=file.file_type,
                file_size=file.file_size,
                collection_id=file.collection_id,
            )
        )

        return files

    def update_status(self, file_id: uuid.UUID, status: str):
        """
        Update the status of a file.
        """
        self.files_repository.update_attr(file_id, "status", status)
