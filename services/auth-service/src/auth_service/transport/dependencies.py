# services/auth-service/src/auth_service/transport/dependencies.py

"""FastAPI dependencies Authentication Service."""

from typing import cast

from fastapi import Request

from auth_service.core.container import (
    AuthContainer,
)


def get_container(
    request: Request,
) -> AuthContainer:
    """Возвращает Auth composition root из app state."""
    return cast(
        AuthContainer,
        request.app.state.container,
    )
