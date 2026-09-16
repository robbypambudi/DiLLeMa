import uuid
from typing import Optional

from fastapi import UploadFile, File, Form
from pydantic import BaseModel

from app.schema.base_schema import FindBase


class BaseFile(BaseModel):
    file_name: str = None
    file_path: Optional[str] = None
    file_type: Optional[str] = None
    file_size: Optional[int] = None
    collection_id: Optional[uuid.UUID] = None

    class Config:
        from_attributes = True


class FindFiles(FindBase, BaseFile): ...


class CreateFileRequest:
    def __init__(
            self,
            collection_id: uuid.UUID = Form(...),
            file: UploadFile = File(...)
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
