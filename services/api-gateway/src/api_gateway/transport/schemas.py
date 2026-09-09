# services/api-gateway/src/api_gateway/transport/schemas.py

"""Transport schemas operational и system endpoints API Gateway."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from api_gateway.application.system_info import SystemInfo


class HealthResponse(BaseModel):
    """HTTP response operational health endpoint."""

    model_config = ConfigDict(frozen=True)

    status: Literal[
        "alive",
        "ready",
        "not_ready",
    ]
    service: str
    version: str


class SystemInfoResponse(BaseModel):
    """HTTP representation application SystemInfo DTO."""

    model_config = ConfigDict(frozen=True)

    service: str
    service_version: str
    api_version: str
    environment: str

    @classmethod
    def from_dto(
        cls,
        system_info: SystemInfo,
    ) -> "SystemInfoResponse":
        """Преобразует application DTO в public HTTP schema."""
        return cls(
            service=system_info.service,
            service_version=(system_info.service_version),
            api_version=system_info.api_version,
            environment=system_info.environment,
        )


class ErrorDetail(BaseModel):
    """Содержит стабильную публичную информацию об HTTP error."""

    model_config = ConfigDict(frozen=True)

    code: str
    message: str
    correlation_id: str | None


class ErrorResponse(BaseModel):
    """Envelope единого публичного error contract."""

    model_config = ConfigDict(frozen=True)

    error: ErrorDetail
