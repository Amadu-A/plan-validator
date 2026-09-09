# services/auth-service/src/auth_service/application/dto.py

"""Transport-neutral DTO Authentication application layer."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from auth_service.domain.user import User


@dataclass(frozen=True, slots=True)
class UserView:
    """Безопасное представление пользователя без password hash."""

    id: UUID
    email: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AuthSessionResult:
    """Результат login/register с raw token только для internal boundary."""

    user: UserView
    session_token: str = field(repr=False)
    expires_at: datetime


def user_to_view(user: User) -> UserView:
    """Преобразует Domain User в безопасный Application DTO."""
    return UserView(
        id=user.id,
        email=user.email,
        created_at=user.created_at,
    )
