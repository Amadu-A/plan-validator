# services/auth-service/src/auth_service/domain/user.py

"""Domain entity пользователя Authentication Service."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class User:
    """Представляет пользователя независимо от SQLAlchemy/HTTP."""

    id: UUID
    email: str
    password_hash: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
