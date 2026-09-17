from contextlib import contextmanager
from typing import Any, Generator

from loguru import logger
from sqlalchemy import create_engine, orm
from sqlalchemy.ext.declarative import as_declarative, declared_attr
from sqlalchemy.orm import Session

from app.core.config import settings

DATABASE_URL = str(settings.SQLALCHEMY_DATABASE_URI)


@as_declarative()
class BaseModel:
    metadata = None
    id: Any
    __name__: str

    # Generate the table name from the class name
    @declared_attr
    def __tablename__(self) -> str:
        return self.__name__.lower() + "s"


class Database:
    def __init__(self, db_url: str):
        logger.info('Creating database engine with URL: %s', db_url)
        self._engine = create_engine(db_url, echo=True)
        self._session_factory = orm.scoped_session(
            orm.sessionmaker(
                autocommit=False, autoflush=False, bind=self._engine
            )
        )

    def create_database(self):
        BaseModel.metadata.create_all(bind=self._engine)

    @contextmanager
    def session(self) -> Generator[Session, Any, None]:
        """Provide a transactional scope around a series of operations."""
        session: Session = self._session_factory()
        try:
            yield session
        except Exception as e:
            session.rollback()
            raise
        finally:
            session.close()

    def close(self):
        """Close the database connection."""
        self._session_factory.remove()
        self._engine.dispose()
