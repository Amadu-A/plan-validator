# services/embedding-service/src/embedding_service/transport/dependencies.py

"""FastAPI dependencies Embedding Service."""

from typing import cast

from fastapi import Request

from embedding_service.core.container import EmbeddingContainer


def get_container(request: Request) -> EmbeddingContainer:
    """Возвращает process container из FastAPI application state."""
    return cast(EmbeddingContainer, request.app.state.container)
