"""HTTP request contracts for collection knowledge administration."""

from typing import Literal

from pydantic import BaseModel, Field

ClaimStatus = Literal["pending", "approved", "rejected"]


class ReviewRequest(BaseModel):
    status: Literal["approved", "rejected"]
    note: str = Field(default="", max_length=2000)
