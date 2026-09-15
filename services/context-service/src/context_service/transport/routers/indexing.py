# services/context-service/src/context_service/transport/routers/indexing.py

"""Internal durable indexing/status endpoints Context Service."""

from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    Query,
    Request,
    status,
)

from context_service.core.container import ContextContainer
from context_service.transport.dependencies import (
    get_container,
)
from context_service.transport.schemas import (
    ContextIndexAcceptedResponse,
    ContextIndexJobResponse,
    EnqueueContextIndexRequest,
)

router = APIRouter(
    prefix="/internal/v1/context/contexts",
    tags=["internal-context-indexing"],
)

ContainerDependency = Annotated[
    ContextContainer,
    Depends(get_container),
]

UserIdQuery = Annotated[
    UUID,
    Query(),
]


@router.post(
    "/{context_id}/sources/{source_id}/index",
    response_model=ContextIndexAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def enqueue_context_index(
    context_id: UUID,
    source_id: UUID,
    body: EnqueueContextIndexRequest,
    request: Request,
    container: ContainerDependency,
) -> ContextIndexAcceptedResponse:
    """Принимает normalized chunks и создаёт durable indexing job."""
    correlation_id = str(request.scope["plan_validator.correlation_id"])

    result = await container.enqueue_index.execute(
        user_id=body.user_id,
        context_id=context_id,
        source_id=source_id,
        chunks=tuple(chunk.to_domain() for chunk in body.chunks),
        correlation_id=correlation_id,
    )

    return ContextIndexAcceptedResponse.from_application(result)


@router.get(
    "/{context_id}/jobs/{job_id}",
    response_model=ContextIndexJobResponse,
)
async def context_index_job_status(
    context_id: UUID,
    job_id: UUID,
    user_id: UserIdQuery,
    container: ContainerDependency,
) -> ContextIndexJobResponse:
    """Возвращает owner/context-scoped durable job status."""
    job = await container.get_index_job.execute(
        user_id=user_id,
        context_id=context_id,
        job_id=job_id,
    )

    return ContextIndexJobResponse.from_domain(job)
