# services/auth-service/src/auth_service/application/ports/session_repository.py

"""Application port repository opaque sessions."""

from datetime import datetime
from typing import Protocol

from auth_service.domain.session import AuthSession


class SessionRepository(Protocol):
    """Определяет persistence operations authentication sessions."""

    async def add(
        self,
        session: AuthSession,
    ) -> None:
        """Добавляет session в текущую transaction."""

    async def get_by_token_hash(
        self,
        token_hash: str,
    ) -> AuthSession | None:
        """Возвращает session по SHA-256 token hash."""

    async def revoke(
        self,
        *,
        token_hash: str,
        revoked_at: datetime,
    ) -> None:
        """Помечает существующую session revoked."""
