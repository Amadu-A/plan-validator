# services/context-service/src/context_service/transport/dependencies.py

"""FastAPI dependencies Context Service."""

from typing import cast

from fastapi import Request

from context_service.core.container import ContextContainer


def get_container(
    request: Request,
) -> ContextContainer:
    """Возвращает process container из FastAPI state."""
    return cast(
        ContextContainer,
        request.app.state.container,
    )
