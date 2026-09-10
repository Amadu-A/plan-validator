# services/retrieval-service/src/retrieval_service/transport/dependencies.py

"""FastAPI dependencies Retrieval Service."""

from typing import cast

from fastapi import Request

from retrieval_service.core.container import RetrievalContainer


def get_container(request: Request) -> RetrievalContainer:
    """Возвращает process container из FastAPI application state."""
    return cast(RetrievalContainer, request.app.state.container)
