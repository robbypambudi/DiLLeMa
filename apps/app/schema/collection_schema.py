import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.schema.base_schema import FindBase


class FindCollection(FindBase):
    collection_name: Optional[str] = None
    vectordb_collection_name: Optional[str] = None
    description: Optional[str] = None


class CreateCollectionRequest(BaseModel):
    collection_name: str
    description: Optional[str] = None


class UpdateCollectionRequest(BaseModel):
    collection_name: Optional[str] = None
    description: Optional[str] = None


class ListCollection(BaseModel):
    id: uuid.UUID
    collection_name: str
    vectordb_collection_name: str
    description: Optional[str] = None
    file_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CollectionDetail(ListCollection):
    file_status_counts: dict[str, int] = {}
