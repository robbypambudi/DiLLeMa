from enum import Enum

from sqlmodel import Field, String

from app.models import BaseModel


class UserRole(str, Enum):
    admin = "admin"
    user = "user"


class Users(BaseModel, table=True):
    __tablename__ = "users"

    email: str = Field(sa_type=String, nullable=False, unique=True, index=True)
    password_hash: str = Field(sa_type=String, nullable=False)
    role: str = Field(sa_type=String, nullable=False, default=UserRole.user.value)
