# services/auth-service/src/auth_service/application/ports/security.py

"""Application security ports password hashing и opaque tokens."""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class IssuedSessionToken:
    """Содержит raw token и безопасный hash для разных boundaries."""

    raw_token: str = field(repr=False)
    token_hash: str


class PasswordHasher(Protocol):
    """Абстрагирует expensive password hashing algorithm."""

    def hash_password(
        self,
        password: str,
    ) -> str:
        """Создаёт password hash для persistent storage."""

    def verify_password(
        self,
        *,
        password: str,
        password_hash: str | None,
    ) -> bool:
        """Проверяет password или выполняет fake verify для неизвестного user."""

    def needs_rehash(
        self,
        password_hash: str,
    ) -> bool:
        """Определяет необходимость upgrade параметров сохранённого hash."""


class SessionTokenManager(Protocol):
    """Абстрагирует генерацию и hashing opaque session tokens."""

    def issue_token(self) -> IssuedSessionToken:
        """Создаёт новый cryptographically secure session token."""

    def hash_token(
        self,
        raw_token: str,
    ) -> str:
        """Преобразует raw token в deterministic storage hash."""
