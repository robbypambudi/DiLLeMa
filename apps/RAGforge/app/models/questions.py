import uuid
from typing import Optional

import sqlalchemy as sa
from sqlmodel import Field, Relationship

from app.models import BaseModel


class Questions(BaseModel, table=True):
    __tablename__ = 'questions'
    question_id: str = Field(max_length=255, nullable=False)
    question_text: str = Field(sa_type=sa.Text, nullable=False)
    answer: str = Field(sa_type=sa.Text, nullable=True)
    collection_id: uuid.UUID = Field(foreign_key="collections.id", nullable=False)

    collection: Optional["Collections"] = Relationship(
        back_populates="questions",
    )

    def normalize(self):
        self.question_text = self.question_text.lower()
