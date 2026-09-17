# services/document-service/src/document_service/transport/dependencies.py

"""FastAPI dependencies Document Service."""

from fastapi import Request

from document_service.core.container import DocumentContainer


def get_container(request: Request) -> DocumentContainer:
    """Возвращает application container из app state."""
    return request.app.state.container
