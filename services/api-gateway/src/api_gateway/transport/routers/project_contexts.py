# services/api-gateway/src/api_gateway/transport/routers/project_contexts.py

"""Public authenticated Project Context facade API Gateway."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from api_gateway.application.auth_service import AuthUser
from api_gateway.core.container import GatewayContainer
from api_gateway.transport.context_schemas import (
    ProjectContextResponse,
    ProjectContextSourceResponse,
    RegisterProjectContextSourceRequest,
)
from api_gateway.transport.dependencies import (
    get_authenticated_user,
    get_container,
)

router = APIRouter(
    prefix="/project-contexts",
    tags=["project-contexts"],
)

ContainerDependency = Annotated[
    GatewayContainer,
    Depends(get_container),
]

AuthenticatedUserDependency = Annotated[
    AuthUser,
    Depends(get_authenticated_user),
]


@router.post(
    "",
    response_model=ProjectContextResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_project_context(
    container: ContainerDependency,
    user: AuthenticatedUserDependency,
) -> ProjectContextResponse:
    """Создаёт temporary Project Context authenticated user."""
    context = await container.context_service.create_context(user_id=user.id)

    return ProjectContextResponse.from_dto(context)


@router.get(
    "/{context_id}",
    response_model=ProjectContextResponse,
)
async def get_project_context(
    context_id: UUID,
    container: ContainerDependency,
    user: AuthenticatedUserDependency,
) -> ProjectContextResponse:
    """Возвращает только owner-scoped Project Context."""
    context = await container.context_service.get_context(
        user_id=user.id,
        context_id=context_id,
    )

    return ProjectContextResponse.from_dto(context)


@router.delete(
    "/{context_id}",
    response_model=ProjectContextResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def delete_project_context(
    context_id: UUID,
    container: ContainerDependency,
    user: AuthenticatedUserDependency,
) -> ProjectContextResponse:
    """Запускает logical-first cleanup и не ждёт physical Qdrant deletion."""
    context = await container.context_service.request_cleanup(
        user_id=user.id,
        context_id=context_id,
    )

    return ProjectContextResponse.from_dto(context)


@router.post(
    "/{context_id}/sources",
    response_model=ProjectContextSourceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_project_context_source(
    context_id: UUID,
    body: RegisterProjectContextSourceRequest,
    container: ContainerDependency,
    user: AuthenticatedUserDependency,
) -> ProjectContextSourceResponse:
    """Регистрирует T/PZ metadata без client-controlled ownership."""
    source = await container.context_service.register_source(
        user_id=user.id,
        context_id=context_id,
        kind=body.kind,
        original_name=body.original_name,
        source_sha256=body.source_sha256,
    )

    return ProjectContextSourceResponse.from_dto(source)
