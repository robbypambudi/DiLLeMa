import uuid
from typing import Protocol, Any


class RepositoryProtocol(Protocol):
    def read_by_options(self, schema: Any) -> Any: ...

    def read_by_id(self, id: uuid.UUID) -> Any: ...

    def create(self, schema: Any) -> Any: ...

    def update(self, id: uuid.UUID, schema: Any) -> Any: ...

    def update_attr(self, id: uuid.UUID, attr: str, value: Any) -> Any: ...

    def whole_update(self, id: uuid.UUID, schema: Any) -> Any: ...

    def delete_by_id(self, id: uuid.UUID) -> Any: ...

    def close_scoped_session(self):
        pass


class BaseService:
    """
    Base service class for all services.
    """
    _repository: RepositoryProtocol

    def __init__(self, repository: RepositoryProtocol) -> None:
        self._repository = repository

    def get_list(self, schema: Any) -> Any:
        return self._repository.read_by_options(schema)

    def get_by_id(self, id: uuid.UUID) -> Any:
        return self._repository.read_by_id(id)

    def add(self, schema: Any) -> Any:
        return self._repository.create(schema)

    def patch(self, id: uuid.UUID, schema: Any) -> Any:
        return self._repository.update(id, schema)

    def patch_attr(self, id: uuid.UUID, attr: str, value: Any) -> Any:
        return self._repository.update_attr(id, attr, value)

    def put_update(self, id: uuid.UUID, schema: Any) -> Any:
        return self._repository.whole_update(id, schema)

    def remove_by_id(self, id: uuid.UUID) -> Any:
        return self._repository.delete_by_id(id)

    def close_scoped_session(self):
        self._repository.close_scoped_session()
