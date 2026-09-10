# services/api-gateway/src/api_gateway/transport/routers/catalog.py

"""Public authenticated Catalog facade API Gateway."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from plan_validator_common.exceptions import AuthenticationError

from api_gateway.application.auth_service import AuthUser
from api_gateway.core.container import GatewayContainer
from api_gateway.transport.catalog_schemas import (
    CreateSectionRequest,
    SaveSystemPromptRequest,
    SectionListResponse,
    SectionResponse,
    SystemPromptResponse,
    UpdateSectionRequest,
)
from api_gateway.transport.dependencies import get_container
from api_gateway.transport.session_cookie import read_session_cookie

router = APIRouter(
    prefix="/catalog",
    tags=["catalog"],
)

ContainerDependency = Annotated[
    GatewayContainer,
    Depends(get_container),
]


async def _resolve_authenticated_user(
    *,
    request: Request,
    container: GatewayContainer,
) -> AuthUser:
    """Разрешает HttpOnly session через trusted Authentication Service."""
    session_token = read_session_cookie(
        request=request,
        settings=container.settings.session_cookie,
    )

    if session_token is None:
        raise AuthenticationError("Authentication required")

    return await container.auth_service.get_current_user(session_token=session_token)


@router.get(
    "/sections",
    response_model=SectionListResponse,
)
async def list_sections(
    request: Request,
    container: ContainerDependency,
) -> SectionListResponse:
    """Возвращает sections текущего authenticated user."""
    user = await _resolve_authenticated_user(
        request=request,
        container=container,
    )

    sections = await container.catalog_service.list_sections(user_id=user.id)

    return SectionListResponse(sections=[SectionResponse.from_dto(section) for section in sections])


@router.post(
    "/sections",
    response_model=SectionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_section(
    request: Request,
    body: CreateSectionRequest,
    container: ContainerDependency,
) -> SectionResponse:
    """Создаёт section текущего authenticated user."""
    user = await _resolve_authenticated_user(
        request=request,
        container=container,
    )

    section = await container.catalog_service.create_section(
        user_id=user.id,
        title=body.title,
        parent_id=body.parent_id,
        sort_order=body.sort_order,
    )

    return SectionResponse.from_dto(section)


@router.patch(
    "/sections/{section_id}",
    response_model=SectionResponse,
)
async def update_section(
    section_id: UUID,
    request: Request,
    body: UpdateSectionRequest,
    container: ContainerDependency,
) -> SectionResponse:
    """Изменяет user-owned section."""
    user = await _resolve_authenticated_user(
        request=request,
        container=container,
    )

    section = await container.catalog_service.update_section(
        user_id=user.id,
        section_id=section_id,
        title=body.title,
        parent_id=body.parent_id,
        parent_id_supplied="parent_id" in body.model_fields_set,
        sort_order=body.sort_order,
    )

    return SectionResponse.from_dto(section)


@router.delete(
    "/sections/{section_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_section(
    section_id: UUID,
    request: Request,
    container: ContainerDependency,
) -> Response:
    """Удаляет user-owned Catalog section."""
    user = await _resolve_authenticated_user(
        request=request,
        container=container,
    )

    await container.catalog_service.delete_section(
        user_id=user.id,
        section_id=section_id,
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/system-prompt",
    response_model=SystemPromptResponse,
)
async def get_system_prompt(
    request: Request,
    container: ContainerDependency,
) -> SystemPromptResponse:
    """Возвращает system prompt текущего пользователя."""
    user = await _resolve_authenticated_user(
        request=request,
        container=container,
    )

    prompt = await container.catalog_service.get_system_prompt(user_id=user.id)

    return SystemPromptResponse.from_dto(prompt)


@router.put(
    "/system-prompt",
    response_model=SystemPromptResponse,
)
async def save_system_prompt(
    request: Request,
    body: SaveSystemPromptRequest,
    container: ContainerDependency,
) -> SystemPromptResponse:
    """Сохраняет system prompt текущего пользователя."""
    user = await _resolve_authenticated_user(
        request=request,
        container=container,
    )

    prompt = await container.catalog_service.save_system_prompt(
        user_id=user.id,
        prompt=body.prompt,
    )

    return SystemPromptResponse.from_dto(prompt)
