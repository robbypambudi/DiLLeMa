from sqlmodel import String, Text, Field, Relationship

from app.models import BaseModel


class Collections(BaseModel, table=True):
    __tablename__ = 'collections'
    collection_name: str = Field(sa_type=String, nullable=True, unique=True)
    description: str = Field(sa_type=Text, nullable=True)
    vectordb_collection_name: str = Field(sa_type=String, nullable=True, unique=True)
    files: list["Files"] = Relationship(
        back_populates="collection",
    )
    questions: list["Questions"] = Relationship(
        back_populates="collection",
    )

    def normalize(self):
        self.collection_name = self.collection_name.lower()
