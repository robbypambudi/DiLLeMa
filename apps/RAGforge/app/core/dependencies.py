from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.container import Container
from app.core.exceptions import AuthError, NotFoundError, UnauthorizedError
from app.core.security import decode_access_token
from app.models.users import UserRole, Users
from app.repositories.users_repository import UsersRepository
from dependency_injector.wiring import Provide, inject

_bearer = HTTPBearer(auto_error=False)


@inject
def get_current_user(
        credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
        users_repository: UsersRepository = Depends(Provide[Container.users_repository]),
) -> Users:
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise UnauthorizedError()
    payload = decode_access_token(credentials.credentials)
    sub = payload.get("sub")
    if not sub:
        raise UnauthorizedError()
    try:
        user_id = UUID(str(sub))
    except ValueError:
        raise UnauthorizedError()
    try:
        user = users_repository.read_by_id(user_id)
    except NotFoundError:
        raise UnauthorizedError()
    return user


def require_admin(user: Users = Depends(get_current_user)) -> Users:
    if user.role != UserRole.admin.value:
        raise AuthError(detail="Forbidden")
    return user
