import uuid
from typing import Optional

import sqlalchemy as sa
from sqlmodel import Field, Column, JSON, Relationship

from app.models import BaseModel


class Files(BaseModel, table=True):
    __tablename__ = 'files'
    file_name: str = Field(max_length=255, nullable=False)
    file_path: str = Field(max_length=255, nullable=False)
    file_type: str = Field(max_length=50, nullable=False)
    file_size: int = Field(nullable=False)
    metadatas: dict = Field(sa_column=Column(JSON), default={})
    status: str = Field(default="pending",
                        sa_column=Column(sa.Enum("pending", "processing", "completed", "failed", "deleted", "archived"),
                                         nullable=False))
    processing_started_at: str = Field(default=None, nullable=True)
    processing_ended_at: str = Field(default=None, nullable=True)
    collection_id: uuid.UUID = Field(foreign_key="collections.id", nullable=False)

    collection: Optional["Collections"] = Relationship(
        back_populates="files",
    )

    def normalize(self):
        self.file_name = self.file_name.lower()
