import uuid
from typing import Optional

from pydantic import BaseModel

from app.schema.base_schema import FindBase
from app.utils.schema import as_form


class BaseCollection(BaseModel):
    collection_name: str
    vectordb_collection_name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class FindCollection(FindBase, BaseCollection): ...


class ListCollection(BaseCollection):
    id: uuid.UUID


@as_form
class CreateCollectionRequest(BaseCollection): ...
