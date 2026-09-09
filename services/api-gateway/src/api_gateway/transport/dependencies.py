# services/api-gateway/src/api_gateway/transport/dependencies.py

"""FastAPI dependencies для получения objects из Gateway composition root."""

from typing import cast

from fastapi import Request

from api_gateway.core.container import GatewayContainer


def get_container(
    request: Request,
) -> GatewayContainer:
    """Возвращает process container, созданный composition root."""
    return cast(
        GatewayContainer,
        request.app.state.container,
    )
