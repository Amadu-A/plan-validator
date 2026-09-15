# services/api-gateway/src/api_gateway/core/settings.py

"""Service-specific настройки API Gateway поверх CommonSettings."""

from typing import Literal

from plan_validator_common.settings import CommonSettings
from pydantic import BaseModel, Field


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


class GatewayUploadSettings(BaseModel):
    """Bounded browser upload limits API Gateway."""

    max_managed_source_bytes: int = Field(
        default=64 * 1024 * 1024,
        gt=0,
    )


class InternalHttpSettings(BaseModel):
    """Настройки outbound HTTP clients internal service calls."""

    connect_timeout_seconds: float = Field(
        default=3.0,
        gt=0,
    )
    read_timeout_seconds: float = Field(
        default=30.0,
        gt=0,
        le=60.0,
    )


class AuthServiceSettings(BaseModel):
    """Docker-DNS endpoint trusted Authentication Service."""

    base_url: str = Field(
        default="http://auth-service:8000",
        min_length=1,
    )


class CatalogServiceSettings(BaseModel):
    """Docker-DNS endpoint trusted Catalog Service."""

    base_url: str = Field(
        default="http://catalog-service:8000",
        min_length=1,
    )


class ContextServiceSettings(BaseModel):
    """Docker-DNS endpoint trusted Context Service."""

    base_url: str = Field(
        default="http://context-service:8000",
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
    """Объединяет common и service-specific Gateway settings."""

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
    gateway_upload: GatewayUploadSettings = Field(
        default_factory=GatewayUploadSettings,
    )
    internal_http: InternalHttpSettings = Field(
        default_factory=InternalHttpSettings,
    )
    auth_service: AuthServiceSettings = Field(
        default_factory=AuthServiceSettings,
    )
    catalog_service: CatalogServiceSettings = Field(
        default_factory=CatalogServiceSettings,
    )
    context_service: ContextServiceSettings = Field(
        default_factory=ContextServiceSettings,
    )
    session_cookie: SessionCookieSettings = Field(
        default_factory=SessionCookieSettings,
    )


def load_gateway_settings() -> GatewaySettings:
    """Загружает Gateway settings через общий layered environment contract."""
    return GatewaySettings()
