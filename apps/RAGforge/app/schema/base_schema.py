from typing import Generic, TypeVar, Optional
from typing import Union

from pydantic import BaseModel


class FindBase(BaseModel):
    ordering: Optional[str] = None
    page: int = None
    page_size: Optional[Union[int, str]] = 10


class Metadata(BaseModel):
    total_count: int
    page: int
    page_size: int


T = TypeVar("T")


class BaseResponse(BaseModel, Generic[T]):
    data: Optional[T]
    status: str = "success"
    message: Optional[str] = None


class PaginatedResponse(BaseModel, Generic[T]):
    data: Optional[list[T]]
    metadata: Metadata
    status: str = "success"
    message: Optional[str] = None
