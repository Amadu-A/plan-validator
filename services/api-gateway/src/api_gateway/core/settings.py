# services/api-gateway/src/api_gateway/core/settings.py

"""Service-specific настройки API Gateway поверх CommonSettings."""

from typing import Literal

from plan_validator_common.settings import (
    CommonSettings,
)
from pydantic import (
    BaseModel,
    Field,
)


class GatewayHttpSettings(BaseModel):
    """Настройки HTTP server API Gateway."""

    host: str = Field(
        default="0.0.0.0",
        min_length=1,
    )
    port: int = Field(
        default=8000,
        ge=1,
        le=65535,
    )
    docs_enabled: bool = True


class InternalHttpSettings(BaseModel):
    """Настройки outbound HTTP clients для internal service calls."""

    connect_timeout_seconds: float = Field(
        default=3.0,
        gt=0,
    )
    read_timeout_seconds: float = Field(
        default=30.0,
        gt=0,
    )


class AuthServiceSettings(BaseModel):
    """Docker-DNS endpoint trusted Authentication Service."""

    base_url: str = Field(
        default="http://auth-service:8000",
        min_length=1,
    )


class SessionCookieSettings(BaseModel):
    """Browser cookie policy opaque authentication session."""

    name: str = Field(
        default="plan_validator_session",
        min_length=1,
    )
    max_age_seconds: int = Field(
        default=7 * 24 * 60 * 60,
        ge=60,
    )
    secure: bool = False
    same_site: Literal[
        "lax",
        "strict",
        "none",
    ] = "lax"
    path: str = "/"


class GatewaySettings(CommonSettings):
    """Объединяет общие и service-specific настройки API Gateway."""

    service_name: str = Field(
        default="api-gateway",
        min_length=1,
    )
    service_version: str = Field(
        default="0.1.0",
        min_length=1,
    )
    api_version: str = Field(
        default="v1",
        min_length=1,
    )

    gateway: GatewayHttpSettings = Field(
        default_factory=GatewayHttpSettings,
    )
    internal_http: InternalHttpSettings = Field(
        default_factory=InternalHttpSettings,
    )
    auth_service: AuthServiceSettings = Field(
        default_factory=AuthServiceSettings,
    )
    session_cookie: SessionCookieSettings = Field(
        default_factory=SessionCookieSettings,
    )


def load_gateway_settings() -> GatewaySettings:
    """Загружает Gateway settings через общий layered environment contract."""
    return GatewaySettings()
