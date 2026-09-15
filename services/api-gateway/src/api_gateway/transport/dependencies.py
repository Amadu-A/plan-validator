# services/api-gateway/src/api_gateway/transport/dependencies.py

"""FastAPI dependencies для Gateway composition root и authentication."""

from typing import Annotated, cast

from fastapi import Depends, Request
from plan_validator_common.exceptions import AuthenticationError

from api_gateway.application.auth_service import AuthUser
from api_gateway.core.container import GatewayContainer
from api_gateway.transport.session_cookie import (
    read_session_cookie,
)


def get_container(
    request: Request,
) -> GatewayContainer:
    """Возвращает process container, созданный composition root."""
    return cast(
        GatewayContainer,
        request.app.state.container,
    )


async def get_authenticated_user(
    request: Request,
    container: Annotated[
        GatewayContainer,
        Depends(get_container),
    ],
) -> AuthUser:
    """Разрешает HttpOnly session через trusted Authentication Service."""
    session_token = read_session_cookie(
        request=request,
        settings=container.settings.session_cookie,
    )

    if session_token is None:
        raise AuthenticationError("Authentication required")

    return await container.auth_service.get_current_user(session_token=session_token)
