# services/context-service/src/context_service/transport/routers/lifecycle.py

"""Internal lifecycle endpoints temporary Project Context."""

from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    Query,
    status,
)

from context_service.core.container import ContextContainer
from context_service.transport.dependencies import (
    get_container,
)
from context_service.transport.schemas import (
    ContextSourceResponse,
    CreateProjectContextRequest,
    ProjectContextResponse,
    RegisterContextSourceRequest,
)

router = APIRouter(
    prefix="/internal/v1/context/contexts",
    tags=["internal-context"],
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
    "",
    response_model=ProjectContextResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_project_context(
    body: CreateProjectContextRequest,
    container: ContainerDependency,
) -> ProjectContextResponse:
    """Создаёт owner-scoped temporary Project Context."""
    context = await container.create_context.execute(
        user_id=body.user_id,
    )

    return ProjectContextResponse.from_domain(context)


@router.get(
    "/{context_id}",
    response_model=ProjectContextResponse,
)
async def get_project_context(
    context_id: UUID,
    user_id: UserIdQuery,
    container: ContainerDependency,
) -> ProjectContextResponse:
    """Возвращает Project Context только его owner."""
    context = await container.get_context.execute(
        user_id=user_id,
        context_id=context_id,
    )

    return ProjectContextResponse.from_domain(context)


@router.delete(
    "/{context_id}",
    response_model=ProjectContextResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_project_context_cleanup(
    context_id: UUID,
    user_id: UserIdQuery,
    container: ContainerDependency,
) -> ProjectContextResponse:
    """Сначала логически скрывает context; physical cleanup асинхронный."""
    context = await container.request_cleanup.execute(
        user_id=user_id,
        context_id=context_id,
    )

    return ProjectContextResponse.from_domain(context)


@router.post(
    "/{context_id}/sources",
    response_model=ContextSourceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_context_source(
    context_id: UUID,
    body: RegisterContextSourceRequest,
    container: ContainerDependency,
) -> ContextSourceResponse:
    """Регистрирует metadata единственного T либо PZ source."""
    source = await container.register_source.execute(
        user_id=body.user_id,
        context_id=context_id,
        kind=body.kind,
        original_name=body.original_name,
        source_sha256=body.source_sha256,
    )

    return ContextSourceResponse.from_domain(source)
