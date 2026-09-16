import uuid
from contextlib import AbstractContextManager
from typing import Callable

from sqlalchemy.orm import Session

from app.models.files import Files
from app.repositories.base_repository import BaseRepository
from app.services.base_service import RepositoryProtocol


class FilesRepository(BaseRepository, RepositoryProtocol):
    def __init__(self, session_factory: Callable[..., AbstractContextManager[Session]]):
        self.session_factory = session_factory
        super().__init__(session_factory, Files)

    def get_collection_name(self, collection_id: uuid.UUID) -> str:
        """
        Get the collection name from the database using the collection ID.
        """
        with self.session_factory() as session:
            file_entry = session.query(Files).filter(Files.collection_id == collection_id).join(
                Files.collection
            ).first()
            if file_entry and file_entry.collection:
                return file_entry.collection.collection_name
            else:
                raise ValueError(f"Collection with ID {collection_id} not found.")
            
    def get_vectordb_collection_name(self, collection_id: uuid.UUID) -> str:
        """
        Get the vector DB collection name using the collection ID.
        """
        with self.session_factory() as session:
            file_entry = (
                session.query(Files)
                .filter(Files.collection_id == collection_id)
                .join(Files.collection)
                .first()
            )
            if file_entry and file_entry.collection:
                return file_entry.collection.vectordb_collection_name
            raise ValueError(f"Collection with ID {collection_id} not found.")
