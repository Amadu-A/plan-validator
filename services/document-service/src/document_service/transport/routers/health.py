# services/document-service/src/document_service/transport/routers/health.py

"""Liveness/readiness endpoints Document Service."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from document_service.core.container import DocumentContainer
from document_service.transport.dependencies import get_container

router = APIRouter(tags=["health"])
ContainerDependency = Annotated[DocumentContainer, Depends(get_container)]


@router.get("/health/live")
async def live() -> dict[str, str]:
    """Подтверждает жизнь HTTP process без heavy dependencies."""
    return {"status": "ok"}


@router.get("/health/ready")
async def ready(
    container: ContainerDependency,
    response: Response,
) -> dict[str, object]:
    """Проверяет PostgreSQL и bounded filesystem storage."""
    database = await container.database_health.is_ready()
    storage = await container.storage.is_ready()
    ready_state = database and storage
    if not ready_state:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ok" if ready_state else "not_ready",
        "database": database,
        "storage": storage,
    }
