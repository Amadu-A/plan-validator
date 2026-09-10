# services/catalog-service/src/catalog_service/transport/routers/catalog.py

"""Internal CRUD router пользовательского Catalog."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from catalog_service.core.container import CatalogContainer
from catalog_service.transport.dependencies import get_container
from catalog_service.transport.schemas import (
    CreateSectionRequest,
    SaveSystemPromptRequest,
    SectionListResponse,
    SectionResponse,
    SystemPromptResponse,
    UpdateSectionRequest,
)

router = APIRouter(
    prefix="/catalog/users/{user_id}",
    tags=["internal-catalog"],
)

ContainerDependency = Annotated[
    CatalogContainer,
    Depends(get_container),
]


@router.get(
    "/sections",
    response_model=SectionListResponse,
)
async def list_sections(
    user_id: UUID,
    container: ContainerDependency,
) -> SectionListResponse:
    """Возвращает sections trusted user identity."""
    sections = await container.list_sections.execute(user_id=user_id)

    return SectionListResponse(
        sections=[
            SectionResponse.from_domain(section)
            for section in sections
        ]
    )


@router.post(
    "/sections",
    response_model=SectionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_section(
    user_id: UUID,
    request: CreateSectionRequest,
    container: ContainerDependency,
) -> SectionResponse:
    """Создаёт новый user-owned section."""
    section = await container.create_section.execute(
        user_id=user_id,
        title=request.title,
        parent_id=request.parent_id,
        sort_order=request.sort_order,
    )

    return SectionResponse.from_domain(section)


@router.patch(
    "/sections/{section_id}",
    response_model=SectionResponse,
)
async def update_section(
    user_id: UUID,
    section_id: UUID,
    request: UpdateSectionRequest,
    container: ContainerDependency,
) -> SectionResponse:
    """Изменяет section с явной семантикой omitted/null parent_id."""
    section = await container.update_section.execute(
        user_id=user_id,
        section_id=section_id,
        title=request.title,
        parent_id=request.parent_id,
        parent_id_supplied="parent_id" in request.model_fields_set,
        sort_order=request.sort_order,
    )

    return SectionResponse.from_domain(section)


@router.delete(
    "/sections/{section_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_section(
    user_id: UUID,
    section_id: UUID,
    container: ContainerDependency,
) -> Response:
    """Удаляет section metadata."""
    await container.delete_section.execute(
        user_id=user_id,
        section_id=section_id,
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/system-prompt",
    response_model=SystemPromptResponse,
)
async def get_system_prompt(
    user_id: UUID,
    container: ContainerDependency,
) -> SystemPromptResponse:
    """Возвращает текущий system prompt либо empty default."""
    value = await container.get_system_prompt.execute(user_id=user_id)

    return SystemPromptResponse.from_dto(value)


@router.put(
    "/system-prompt",
    response_model=SystemPromptResponse,
)
async def save_system_prompt(
    user_id: UUID,
    request: SaveSystemPromptRequest,
    container: ContainerDependency,
) -> SystemPromptResponse:
    """Создаёт либо обновляет singleton system prompt."""
    value = await container.save_system_prompt.execute(
        user_id=user_id,
        prompt=request.prompt,
    )

    return SystemPromptResponse.from_dto(value)
