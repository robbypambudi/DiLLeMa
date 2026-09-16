import uuid
from datetime import datetime
from typing import Optional

from fastapi import File, Form, UploadFile
from pydantic import BaseModel

from app.schema.base_schema import FindBase


class BaseFile(BaseModel):
    file_name: Optional[str] = None
    file_path: Optional[str] = None
    file_type: Optional[str] = None
    file_size: Optional[int] = None
    collection_id: Optional[uuid.UUID] = None
    status: Optional[str] = None

    class Config:
        from_attributes = True


class FindFiles(FindBase, BaseFile):
    ...


class CreateFileRequest:
    def __init__(
            self,
            collection_id: uuid.UUID = Form(...),
            file: UploadFile = File(...),
    ):
        self.file = file
        self.collection_id = collection_id


class ResponseFiles(BaseModel):
    id: uuid.UUID
    file_name: str
    file_path: str
    file_type: str
    file_size: int
    status: str
    collection_id: uuid.UUID
    processing_started_at: Optional[datetime] = None
    processing_ended_at: Optional[datetime] = None

    class Config:
        from_attributes = True
