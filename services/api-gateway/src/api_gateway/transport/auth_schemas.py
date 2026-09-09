# services/api-gateway/src/api_gateway/transport/auth_schemas.py

"""Public HTTP schemas authentication API Gateway."""

from datetime import datetime
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
)

from api_gateway.application.auth_service import (
    AuthUser,
)


class RegisterRequest(BaseModel):
    """Public registration request browser -> Gateway."""

    email: EmailStr
    password: SecretStr = Field(
        min_length=12,
        max_length=128,
    )


class LoginRequest(BaseModel):
    """Public login request browser -> Gateway."""

    email: EmailStr
    password: SecretStr = Field(
        min_length=12,
        max_length=128,
    )


class AuthUserResponse(BaseModel):
    """Public user response без password/session token."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    email: EmailStr
    created_at: datetime

    @classmethod
    def from_dto(
        cls,
        user: AuthUser,
    ) -> "AuthUserResponse":
        """Преобразует Gateway AuthUser в public schema."""
        return cls(
            id=user.id,
            email=user.email,
            created_at=user.created_at,
        )
