# services/embedding-service/src/embedding_service/transport/routers/internal_v1.py

"""Internal versioned operational API Embedding Service."""

from typing import Annotated

from fastapi import APIRouter, Depends

from embedding_service.core.container import EmbeddingContainer
from embedding_service.transport.dependencies import get_container
from embedding_service.transport.schemas import RuntimeStatusResponse

router = APIRouter(prefix="/internal/v1/embedding", tags=["internal-embedding"])
ContainerDependency = Annotated[EmbeddingContainer, Depends(get_container)]


@router.get("/runtime", response_model=RuntimeStatusResponse)
async def runtime_status(container: ContainerDependency) -> RuntimeStatusResponse:
    """Возвращает safe model/queue/cache contract без GPU allocation."""
    status = await container.get_runtime_status.execute()

    return RuntimeStatusResponse(
        model=status.model,
        dimension=status.dimension,
        queue=status.queue,
        cache_ready=status.cache_ready,
        gpu_required=status.gpu_required,
        offline_only=status.offline_only,
    )
