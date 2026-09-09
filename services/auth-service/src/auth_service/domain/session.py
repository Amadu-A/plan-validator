# services/auth-service/src/auth_service/domain/session.py

"""Domain entity opaque authentication session."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class AuthSession:
    """Представляет сохранённый hash opaque session token."""

    id: UUID
    user_id: UUID
    token_hash: str
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None

    def is_valid(self, *, now: datetime) -> bool:
        """Проверяет, что session не revoked и ещё не истекла."""
        return self.revoked_at is None and self.expires_at > now
