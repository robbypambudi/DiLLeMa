from contextlib import AbstractContextManager
from typing import Callable, Optional

from sqlalchemy.orm import Session

from app.models.users import Users
from app.repositories.base_repository import BaseRepository
from app.services.base_service import RepositoryProtocol


class UsersRepository(BaseRepository, RepositoryProtocol):
    def __init__(self, session_factory: Callable[..., AbstractContextManager[Session]]):
        self.session_factory = session_factory
        super().__init__(session_factory, Users)

    def get_by_email(self, email: str) -> Optional[Users]:
        with self.session_factory() as session:
            return session.query(Users).filter(Users.email == email.lower().strip()).first()

    def count(self) -> int:
        with self.session_factory() as session:
            return session.query(Users).count()
