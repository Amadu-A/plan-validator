# services/context-service/src/context_service/transport/routers/search.py

"""Internal typed T/PZ retrieval endpoints Context Service."""

from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    Request,
)

from context_service.core.container import ContextContainer
from context_service.domain.models import ContextSourceKind
from context_service.domain.search import ContextSearchQuery
from context_service.transport.dependencies import (
    get_container,
)
from context_service.transport.schemas import (
    ContextSearchHitResponse,
    ContextSearchRequest,
    ContextSearchResponse,
)

router = APIRouter(
    prefix="/internal/v1/context/contexts",
    tags=["internal-context-search"],
)

ContainerDependency = Annotated[
    ContextContainer,
    Depends(get_container),
]


@router.post(
    "/{context_id}/search/{kind}",
    response_model=ContextSearchResponse,
)
async def search_project_context(
    context_id: UUID,
    kind: ContextSourceKind,
    body: ContextSearchRequest,
    request: Request,
    container: ContainerDependency,
) -> ContextSearchResponse:
    """Выполняет owner-scoped typed T/PZ search без normative semantics."""
    correlation_id = str(request.scope["plan_validator.correlation_id"])

    hits = await container.search_context.execute(
        ContextSearchQuery(
            user_id=body.user_id,
            context_id=context_id,
            kind=kind,
            text=body.text,
            limit=body.limit,
            score_threshold=body.score_threshold,
        ),
        correlation_id=correlation_id,
    )

    return ContextSearchResponse(hits=[ContextSearchHitResponse.from_domain(hit) for hit in hits])
