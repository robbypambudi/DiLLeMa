from uuid import UUID

from pydantic import BaseModel


class LoginRequest(BaseModel):
    email: str
    password: str


class UserPublic(BaseModel):
    id: UUID
    email: str
    role: str

    class Config:
        from_attributes = True


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserPublic
