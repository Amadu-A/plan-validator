# services/auth-service/src/auth_service/application/ports/user_repository.py

"""Application port repository пользователей."""

from typing import Protocol
from uuid import UUID

from auth_service.domain.user import User


class UserRepository(Protocol):
    """Определяет data-access operations aggregate User."""

    async def get_by_email(
        self,
        email: str,
    ) -> User | None:
        """Возвращает пользователя по normalized email."""

    async def get_by_id(
        self,
        user_id: UUID,
    ) -> User | None:
        """Возвращает пользователя по identifier."""

    async def add(
        self,
        user: User,
    ) -> None:
        """Добавляет нового пользователя в текущую transaction."""

    async def update_password_hash(
        self,
        *,
        user_id: UUID,
        password_hash: str,
    ) -> None:
        """Обновляет password hash при rehash после успешного login."""
