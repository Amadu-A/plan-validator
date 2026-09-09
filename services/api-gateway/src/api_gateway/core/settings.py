# services/api-gateway/src/api_gateway/core/settings.py

"""Service-specific настройки API Gateway поверх CommonSettings."""

from plan_validator_common.settings import CommonSettings
from pydantic import BaseModel, Field


class GatewayHttpSettings(BaseModel):
    """Настройки HTTP server API Gateway."""

    host: str = Field(default="0.0.0.0", min_length=1)
    port: int = Field(default=8000, ge=1, le=65535)
    docs_enabled: bool = True


class InternalHttpSettings(BaseModel):
    """Настройки outbound HTTP clients для internal service calls."""

    connect_timeout_seconds: float = Field(default=3.0, gt=0)
    read_timeout_seconds: float = Field(default=30.0, gt=0)


class GatewaySettings(CommonSettings):
    """Объединяет общие и service-specific настройки API Gateway."""

    service_name: str = Field(default="api-gateway", min_length=1)
    service_version: str = Field(default="0.1.0", min_length=1)
    api_version: str = Field(default="v1", min_length=1)

    gateway: GatewayHttpSettings = Field(
        default_factory=GatewayHttpSettings,
    )
    internal_http: InternalHttpSettings = Field(
        default_factory=InternalHttpSettings,
    )


def load_gateway_settings() -> GatewaySettings:
    """Загружает Gateway settings через общий layered environment contract."""
    return GatewaySettings()
