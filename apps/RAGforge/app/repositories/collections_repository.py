from contextlib import AbstractContextManager
from typing import Callable

from sqlalchemy.orm import Session

from app.models.collections import Collections
from app.repositories.base_repository import BaseRepository
from app.services.base_service import RepositoryProtocol


class CollectionsRepository(BaseRepository, RepositoryProtocol):
    def __init__(self, session_factory: Callable[..., AbstractContextManager[Session]]):
        self.session_factory = session_factory
        super().__init__(session_factory, Collections)

    def get_by_name(self, name: str) -> Collections:
        """
        Get a collection by name.
        """
        with self.session_factory() as session:
            return session.query(Collections).filter(Collections.collection_name == name).first()
