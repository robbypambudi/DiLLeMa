from loguru import logger

from app.core.config import settings
from app.core.exceptions import UnauthorizedError
from app.core.security import create_access_token, hash_password, verify_password
from app.models.users import UserRole, Users
from app.repositories.users_repository import UsersRepository
from app.schema.auth_schema import LoginResponse, UserPublic
from app.services.base_service import BaseService


class AuthService(BaseService):
    def __init__(self, users_repository: UsersRepository) -> None:
        self.users_repository = users_repository
        super().__init__(users_repository)

    def login(self, email: str, password: str) -> LoginResponse:
        user = self.users_repository.get_by_email(email)
        if not user or not verify_password(password, user.password_hash):
            raise UnauthorizedError(detail="Email or password is wrong.")
        token = create_access_token(user_id=user.id, role=user.role)
        return LoginResponse(
            access_token=token,
            expires_in=settings.JWT_EXPIRE_SECONDS,
            user=UserPublic.model_validate(user),
        )

    def seed_admin_if_empty(self) -> None:
        if self.users_repository.count() > 0:
            return
        email = (settings.ADMIN_EMAIL or "").strip().lower()
        password = settings.ADMIN_PASSWORD or ""
        if not email or not password:
            logger.error(
                "users table is empty and ADMIN_EMAIL/ADMIN_PASSWORD are not set; login will fail until configured"
            )
            return
        self.users_repository.create(
            Users(
                email=email,
                password_hash=hash_password(password),
                role=UserRole.admin.value,
            )
        )
        logger.info("Seeded admin user {}", email)
