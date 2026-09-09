# services/api-gateway/src/api_gateway/application/auth_service.py

"""Application port trusted Authentication Service."""

from dataclasses import (
    dataclass,
    field,
)
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class AuthUser:
    """Safe authenticated user returned by Auth bounded context."""

    id: UUID
    email: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AuthSession:
    """Auth result containing raw token only until cookie creation."""

    user: AuthUser
    session_token: str = field(repr=False)
    expires_at: datetime


class AuthServiceClient(Protocol):
    """Transport-neutral Gateway port Authentication Service."""

    async def register_user(
        self,
        *,
        email: str,
        password: str,
    ) -> AuthSession:
        """Регистрирует user через trusted internal service."""

    async def login_user(
        self,
        *,
        email: str,
        password: str,
    ) -> AuthSession:
        """Аутентифицирует credentials и создаёт session."""

    async def logout_session(
        self,
        *,
        session_token: str,
    ) -> None:
        """Отзывает session через internal Auth API."""

    async def get_current_user(
        self,
        *,
        session_token: str,
    ) -> AuthUser:
        """Разрешает opaque session в safe user."""

    async def aclose(self) -> None:
        """Освобождает owned HTTP resources."""
