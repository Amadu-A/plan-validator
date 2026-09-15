# services/context-service/src/context_service/transport/routers/health.py

"""Operational health endpoints Context Service."""

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
)
from fastapi.responses import JSONResponse

from context_service.core.container import ContextContainer
from context_service.transport.dependencies import (
    get_container,
)
from context_service.transport.schemas import (
    HealthResponse,
)

router = APIRouter(
    prefix="/health",
    tags=["health"],
)

ContainerDependency = Annotated[
    ContextContainer,
    Depends(get_container),
]


@router.get(
    "/live",
    response_model=HealthResponse,
)
async def liveness(
    container: ContainerDependency,
) -> HealthResponse:
    """Подтверждает жизнь HTTP process без external dependency calls."""
    return HealthResponse(
        status="alive",
        service=container.settings.service_name,
        version=container.settings.service_version,
    )


@router.get(
    "/ready",
    response_model=HealthResponse,
)
async def readiness(
    container: ContainerDependency,
) -> HealthResponse | JSONResponse:
    """Проверяет PostgreSQL, Qdrant и mandatory Rabbit queues."""
    ready = await container.check_readiness.execute()

    body = HealthResponse(
        status=("ready" if ready else "not_ready"),
        service=container.settings.service_name,
        version=container.settings.service_version,
    )

    if ready:
        return body

    return JSONResponse(
        status_code=503,
        content=body.model_dump(mode="json"),
    )
