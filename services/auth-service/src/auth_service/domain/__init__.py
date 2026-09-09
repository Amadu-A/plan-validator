# services/auth-service/src/auth_service/domain/__init__.py

"""Domain layer Authentication Service."""

from auth_service.domain.exceptions import (
    AuthDomainError,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidSessionError,
    UserInactiveError,
)
from auth_service.domain.session import AuthSession
from auth_service.domain.user import User

__all__ = [
    "AuthDomainError",
    "AuthSession",
    "EmailAlreadyRegisteredError",
    "InvalidCredentialsError",
    "InvalidSessionError",
    "User",
    "UserInactiveError",
]
