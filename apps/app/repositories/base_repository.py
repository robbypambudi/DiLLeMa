import uuid
from contextlib import AbstractContextManager
from typing import Callable, Type, TypeVar

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import NotFoundError, DuplicatedError
from app.models import BaseModel
from app.utils.query_builder import dict_to_sqlalchemy_query

T = TypeVar("T", bound=BaseModel)


class BaseRepository:

    def __init__(self, session_factory: Callable[..., AbstractContextManager[Session]], model: Type[T]) -> None:
        self.session_factory = session_factory
        self.model = model

    def read_by_options(self, schema: T, eager: bool = False) -> dict:
        with self.session_factory() as session:
            schema_as_dict = schema.model_dump(exclude_none=True)
            # Ordering ID
            # ordering: str = schema_as_dict.get("ordering", "id")
            # order_query = (
            #     getattr(self.model, ordering[1:]).desc()
            #     if ordering.startswith("-")
            #     else getattr(self.model, ordering)
            # )

            page = schema_as_dict.get("page", 1)
            page_size = schema_as_dict.get("page_size", 10)

            filter_options = dict_to_sqlalchemy_query(self.model, schema_as_dict)
            query = session.query(self.model)

            if eager:
                for eager in getattr(self.model, "eagers", []):
                    query = query.options(joinedload(self.model, eager))

            query = query.filter(filter_options)
            total_count = query.count()
            if page_size == 'all':
                query = query.all()
            else:
                page_size = int(page_size)
                query = query.limit(page_size).offset((page - 1) * page_size).all()

            return {
                "metadata": {
                    "total_count": total_count,
                    "page_size": page_size,
                    "page": page
                },
                "data": query
            }

    def read_by_id(self, id: uuid.UUID, eager: bool = False) -> T:
        with self.session_factory() as session:
            query = session.query(self.model)
            if eager:
                for eager in getattr(self.model, "eagers", []):
                    query = query.options(joinedload(self.model, eager))
            query = query.filter(self.model.id == id).first()
            if not query:
                raise NotFoundError(detail=f"{self.model.__name__} with id {id} not found")
            return query

    def create(self, schema: T) -> T:
        with self.session_factory() as session:
            query = self.model(**schema.model_dump(exclude_none=True))
            try:
                session.add(query)
                session.commit()
                session.refresh(query)
            except IntegrityError as e:
                raise DuplicatedError(detail=str(e.orig))
            return query

    def update(self, id: uuid.UUID, schema: T) -> T:
        with self.session_factory() as session:
            session.query(self.model).filter(self.model.id == id).update(
                schema.model_dump(exclude_none=True, exclude={"id", "created_at"})
            )
            session.commit()
            return self.read_by_id(id)

    def delete_by_id(self, id: uuid.UUID):
        with self.session_factory() as session:
            query = session.query(self.model).filter(self.model.id == id).first()
            if not query:
                raise NotFoundError(detail=f"{self.model.__name__} with id {id} not found")
            session.delete(query)
            session.commit()

    def update_attr(self, id: uuid.UUID, attr: str, value: str) -> T:
        with self.session_factory() as session:
            query = session.query(self.model).filter(self.model.id == id).first()
            if not query:
                raise NotFoundError(detail=f"{self.model.__name__} with id {id} not found")
            setattr(query, attr, value)
            session.commit()
            session.refresh(query)
            return query

    def whole_update(self, id: uuid.UUID, schema: T) -> T:
        with self.session_factory() as session:
            session.query(self.model).filter(self.model.id == id).update(schema.model_dump(exclude_none=True))
            session.commit()
            return self.read_by_id(id)

    def clear_all(self):
        with self.session_factory() as session:
            session.query(self.model).delete()
            session.commit()
