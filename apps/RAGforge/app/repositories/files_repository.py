from contextlib import AbstractContextManager
from typing import Callable, List
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.collections import Collections
from app.models.files import Files
from app.repositories.base_repository import BaseRepository
from app.services.base_service import RepositoryProtocol


class FilesRepository(BaseRepository, RepositoryProtocol):
    def __init__(self, session_factory: Callable[..., AbstractContextManager[Session]]):
        self.session_factory = session_factory
        super().__init__(session_factory, Files)

    def read_by_options(self, schema, eager: bool = False) -> dict:
        dumped = schema.model_dump(exclude_none=True)
        if "status" not in dumped:
            dumped["status__notin"] = "deleted,archived"

            class _Query:
                def model_dump(self, exclude_none: bool = True):
                    return dumped

            return super().read_by_options(_Query(), eager)
        return super().read_by_options(schema, eager)

    def list_by_collection(self, collection_id: UUID) -> List[Files]:
        with self.session_factory() as session:
            return (
                session.query(Files)
                .filter(
                    Files.collection_id == collection_id,
                    ~Files.status.in_(("deleted", "archived")),
                )
                .order_by(Files.created_at.desc())
                .all()
            )

    def get_collection_name(self, collection_id: UUID) -> str:
        with self.session_factory() as session:
            collection = session.query(Collections).filter(Collections.id == collection_id).first()
            if not collection:
                raise ValueError(f"Collection with ID {collection_id} not found.")
            return collection.collection_name

    def get_vectordb_collection_name(self, collection_id: UUID) -> str:
        with self.session_factory() as session:
            collection = session.query(Collections).filter(Collections.id == collection_id).first()
            if not collection:
                raise ValueError(f"Collection with ID {collection_id} not found.")
            return collection.vectordb_collection_name

    def update_fields(self, file_id: UUID, values: dict) -> Files:
        with self.session_factory() as session:
            session.query(Files).filter(Files.id == file_id).update(values, synchronize_session=False)
            session.commit()
        return self.read_by_id(file_id)
