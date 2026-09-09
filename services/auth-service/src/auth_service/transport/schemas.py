# services/auth-service/src/auth_service/transport/schemas.py

"""Internal HTTP schemas Authentication Service."""

from datetime import datetime
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
)

from auth_service.application.dto import (
    AuthSessionResult,
    UserView,
)


class RegisterRequest(BaseModel):
    """Internal registration request."""

    email: EmailStr
    password: SecretStr = Field(
        min_length=12,
        max_length=128,
    )


class LoginRequest(BaseModel):
    """Internal password login request."""

    email: EmailStr
    password: SecretStr = Field(
        min_length=12,
        max_length=128,
    )


class SessionTokenRequest(BaseModel):
    """Internal request carrying opaque token only in body."""

    session_token: SecretStr


class UserResponse(BaseModel):
    """Internal safe user representation."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    email: EmailStr
    created_at: datetime

    @classmethod
    def from_dto(
        cls,
        user: UserView,
    ) -> "UserResponse":
        """Преобразует Application UserView в HTTP response."""
        return cls(
            id=user.id,
            email=user.email,
            created_at=user.created_at,
        )


class AuthSessionResponse(BaseModel):
    """Internal response с raw token только для trusted Gateway."""

    model_config = ConfigDict(frozen=True)

    user: UserResponse
    session_token: str
    expires_at: datetime

    @classmethod
    def from_dto(
        cls,
        result: AuthSessionResult,
    ) -> "AuthSessionResponse":
        """Преобразует application auth result в internal response."""
        return cls(
            user=UserResponse.from_dto(result.user),
            session_token=(result.session_token),
            expires_at=result.expires_at,
        )


class ErrorDetail(BaseModel):
    """Стабильная internal error information."""

    code: str
    message: str
    correlation_id: str | None


class ErrorResponse(BaseModel):
    """Единый internal error envelope."""

    error: ErrorDetail


class HealthResponse(BaseModel):
    """Operational health response Auth Service."""

    status: str
    service: str
    version: str
