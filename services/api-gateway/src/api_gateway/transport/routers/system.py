# services/api-gateway/src/api_gateway/transport/routers/system.py

"""Versioned technical system endpoint API Gateway."""

from typing import Annotated

from fastapi import APIRouter, Depends

from api_gateway.core.container import (
    GatewayContainer,
)
from api_gateway.transport.dependencies import (
    get_container,
)
from api_gateway.transport.schemas import (
    SystemInfoResponse,
)

router = APIRouter(
    prefix="/system",
    tags=["system"],
)

ContainerDependency = Annotated[
    GatewayContainer,
    Depends(get_container),
]


@router.get(
    "/info",
    response_model=SystemInfoResponse,
)
async def get_system_info(
    container: ContainerDependency,
) -> SystemInfoResponse:
    """Возвращает version/environment metadata через application use-case."""
    result = container.system_info.execute()

    return SystemInfoResponse.from_dto(result)
