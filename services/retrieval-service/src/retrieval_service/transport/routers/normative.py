# services/retrieval-service/src/retrieval_service/transport/routers/normative.py

"""Internal typed normative N retrieval endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from retrieval_service.core.container import RetrievalContainer
from retrieval_service.domain.search import SearchQuery
from retrieval_service.domain.source_index import SourceKind
from retrieval_service.transport.dependencies import get_container
from retrieval_service.transport.schemas import SearchHitResponse, SearchRequest, SearchResponse

router = APIRouter(
    prefix="/internal/v1/retrieval/normative",
    tags=["internal-normative-retrieval"],
)
ContainerDependency = Annotated[RetrievalContainer, Depends(get_container)]


@router.post("/search", response_model=SearchResponse)
async def search_normative_sources(
    body: SearchRequest,
    request: Request,
    container: ContainerDependency,
) -> SearchResponse:
    """Ищет только normative N evidence текущего explicit tenant user_id."""
    query = SearchQuery(
        user_id=body.user_id,
        kind=SourceKind.NORMATIVE,
        text=body.text,
        section_ids=tuple(body.section_ids),
        source_ids=tuple(body.source_ids),
        limit=body.limit or container.settings.retrieval_search.default_limit,
        score_threshold=(
            body.score_threshold
            if body.score_threshold is not None
            else container.settings.retrieval_search.default_score_threshold
        ),
    )
    hits = await container.search_sources.execute(
        query,
        correlation_id=str(request.scope["plan_validator.correlation_id"]),
    )
    return SearchResponse(hits=[SearchHitResponse.from_domain(hit) for hit in hits])
