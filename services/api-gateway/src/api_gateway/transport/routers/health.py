# services/api-gateway/src/api_gateway/transport/routers/health.py

"""Operational liveness/readiness endpoints API Gateway."""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from api_gateway.core.container import (
    GatewayContainer,
)
from api_gateway.transport.dependencies import (
    get_container,
)
from api_gateway.transport.schemas import (
    HealthResponse,
)

router = APIRouter(
    prefix="/health",
    tags=["health"],
)

ContainerDependency = Annotated[
    GatewayContainer,
    Depends(get_container),
]


@router.get(
    "/live",
    response_model=HealthResponse,
)
async def liveness(
    container: ContainerDependency,
) -> HealthResponse:
    """Подтверждает, что Gateway HTTP process жив."""
    return HealthResponse(
        status="alive",
        service=(container.settings.service_name),
        version=(container.settings.service_version),
    )


@router.get(
    "/ready",
    response_model=HealthResponse,
    responses={
        503: {
            "model": HealthResponse,
        }
    },
)
async def readiness(
    container: ContainerDependency,
) -> HealthResponse | JSONResponse:
    """Возвращает 200 после startup либо 503, если Gateway ещё не ready."""
    response = HealthResponse(
        status=("ready" if container.is_ready else "not_ready"),
        service=(container.settings.service_name),
        version=(container.settings.service_version),
    )

    if container.is_ready:
        return response

    return JSONResponse(
        status_code=503,
        content=response.model_dump(mode="json"),
    )
