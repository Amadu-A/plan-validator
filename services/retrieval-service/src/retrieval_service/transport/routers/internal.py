# services/retrieval-service/src/retrieval_service/transport/routers/internal.py

"""Internal normalized source indexing/status endpoints Retrieval Service."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

from retrieval_service.core.container import RetrievalContainer
from retrieval_service.domain.source_index import NormalizedChunk
from retrieval_service.transport.dependencies import get_container
from retrieval_service.transport.schemas import (
    SourceIndexAcceptedResponse,
    SourceIndexRequest,
    SourceIndexStatusResponse,
)

router = APIRouter(prefix="/internal/v1/retrieval", tags=["internal-retrieval"])
ContainerDependency = Annotated[RetrievalContainer, Depends(get_container)]


@router.post(
    "/sources/{source_id}/index",
    response_model=SourceIndexAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def enqueue_source_index(
    source_id: UUID,
    body: SourceIndexRequest,
    request: Request,
    container: ContainerDependency,
) -> SourceIndexAcceptedResponse:
    """Принимает parser-neutral chunks и enqueue'ит expensive reindex job."""
    correlation_id = str(request.scope["plan_validator.correlation_id"])
    chunks = tuple(
        NormalizedChunk(
            chunk_id=chunk.chunk_id,
            text=chunk.text,
            page_number=chunk.page_number,
            fragment_index=chunk.fragment_index,
            heading=chunk.heading,
            char_start=chunk.char_start,
            char_end=chunk.char_end,
        )
        for chunk in body.chunks
    )
    job_id = await container.enqueue_source_index.execute(
        source_id=source_id,
        source_sha256=body.source_sha256,
        chunks=chunks,
        correlation_id=correlation_id,
    )

    return SourceIndexAcceptedResponse(job_id=job_id, source_id=source_id)


@router.get(
    "/sources/{source_id}/status",
    response_model=SourceIndexStatusResponse,
)
async def source_status(
    source_id: UUID,
    container: ContainerDependency,
) -> SourceIndexStatusResponse:
    """Возвращает current Registry state для Document/Result orchestration."""
    source = await container.get_source_status.execute(source_id)
    return SourceIndexStatusResponse.from_domain(source)
