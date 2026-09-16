from contextlib import AbstractContextManager
from typing import Any, Callable, Optional
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.collections import Collections
from app.models.files import Files
from app.models.questions import Questions
from app.repositories.base_repository import BaseRepository
from app.schema.collection_schema import FindCollection
from app.services.base_service import RepositoryProtocol
from app.utils.query_builder import dict_to_sqlalchemy_query


class CollectionsRepository(BaseRepository, RepositoryProtocol):
    def __init__(self, session_factory: Callable[..., AbstractContextManager[Session]]):
        self.session_factory = session_factory
        super().__init__(session_factory, Collections)

    def get_by_name(self, name: str) -> Optional[Collections]:
        with self.session_factory() as session:
            return session.query(Collections).filter(Collections.collection_name == name).first()

    def get_by_storage_id(self, storage_id: str) -> Optional[Collections]:
        with self.session_factory() as session:
            return session.query(Collections).filter(
                Collections.vectordb_collection_name == storage_id
            ).first()

    def update_fields(self, collection_id: UUID, values: dict[str, Any]) -> Collections:
        with self.session_factory() as session:
            session.query(Collections).filter(Collections.id == collection_id).update(values)
            session.commit()
        return self.read_by_id(collection_id)

    def delete_with_children(self, collection_id: UUID) -> None:
        with self.session_factory() as session:
            collection = session.query(Collections).filter(Collections.id == collection_id).first()
            if not collection:
                raise NotFoundError(detail=f"Collections with id {collection_id} not found")
            session.query(Questions).filter(Questions.collection_id == collection_id).delete(
                synchronize_session=False
            )
            session.query(Files).filter(Files.collection_id == collection_id).delete(
                synchronize_session=False
            )
            session.delete(collection)
            session.commit()

    def list_with_file_count(self, schema: FindCollection) -> dict:
        with self.session_factory() as session:
            schema_as_dict = schema.model_dump(exclude_none=True)
            page = schema_as_dict.get("page") or 1
            page_size = schema_as_dict.get("page_size", 10)
            filters = dict_to_sqlalchemy_query(self.model, schema_as_dict)
            query = (
                session.query(Collections, func.count(Files.id))
                .outerjoin(Files, Files.collection_id == Collections.id)
                .filter(filters)
                .group_by(Collections.id)
                .order_by(Collections.created_at.desc())
            )
            total_count = session.query(Collections).filter(filters).count()
            if page_size == "all":
                rows = query.all()
            else:
                page_size = int(page_size)
                rows = query.limit(page_size).offset((int(page) - 1) * page_size).all()
            return {
                "metadata": {
                    "total_count": total_count,
                    "page_size": page_size,
                    "page": page,
                },
                "data": rows,
            }
