from fastapi import APIRouter, Depends

from app.core.container import Container
from app.core.dependencies import get_current_user
from app.core.middleware import inject
from app.models.users import Users
from app.schema.auth_schema import LoginRequest, LoginResponse, UserPublic
from app.services.auth_service import AuthService
from dependency_injector.wiring import Provide

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
@inject
def login(
        payload: LoginRequest,
        service: AuthService = Depends(Provide[Container.auth_service]),
):
    return service.login(payload.email, payload.password)


@router.get("/me", response_model=UserPublic)
def me(user: Users = Depends(get_current_user)):
    return UserPublic.model_validate(user)
