# services/catalog-service/src/catalog_service/transport/routers/normative_documents.py

"""Internal router нормативных managed documents N."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, Response, status

from catalog_service.core.container import CatalogContainer
from catalog_service.domain.source import SourceKind
from catalog_service.transport.dependencies import get_container
from catalog_service.transport.source_routes import (
    delete_source_response,
    get_source_content_response,
    get_source_response,
    list_sources_response,
    upload_source_response,
)
from catalog_service.transport.source_schemas import (
    ManagedSourceListResponse,
    ManagedSourceResponse,
)

router = APIRouter(
    prefix="/catalog/users/{user_id}/normative-documents",
    tags=["internal-normative-documents"],
)

ContainerDependency = Annotated[
    CatalogContainer,
    Depends(get_container),
]

EncodedFilenameHeader = Annotated[
    str,
    Header(
        alias="X-Source-Filename",
        min_length=1,
        max_length=4096,
    ),
]


@router.get(
    "",
    response_model=ManagedSourceListResponse,
)
async def list_normative_documents(
    user_id: UUID,
    section_id: UUID,
    container: ContainerDependency,
) -> ManagedSourceListResponse:
    """Возвращает нормативные sources N выбранной section."""
    return await list_sources_response(
        user_id=user_id,
        section_id=section_id,
        kind=SourceKind.NORMATIVE,
        container=container,
    )


@router.post(
    "",
    response_model=ManagedSourceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_normative_document(
    user_id: UUID,
    section_id: UUID,
    request: Request,
    source_filename: EncodedFilenameHeader,
    container: ContainerDependency,
) -> ManagedSourceResponse:
    """Загружает нормативный source N через raw bounded request body."""
    return await upload_source_response(
        user_id=user_id,
        section_id=section_id,
        kind=SourceKind.NORMATIVE,
        encoded_name=source_filename,
        request=request,
        container=container,
    )


@router.get(
    "/{source_id}",
    response_model=ManagedSourceResponse,
)
async def get_normative_document(
    user_id: UUID,
    source_id: UUID,
    container: ContainerDependency,
) -> ManagedSourceResponse:
    """Возвращает metadata нормативного source N."""
    return await get_source_response(
        user_id=user_id,
        source_id=source_id,
        kind=SourceKind.NORMATIVE,
        container=container,
    )


@router.get(
    "/{source_id}/content",
    response_class=Response,
)
async def get_normative_document_content(
    user_id: UUID,
    source_id: UUID,
    container: ContainerDependency,
) -> Response:
    """Возвращает original bytes нормативного source N."""
    return await get_source_content_response(
        user_id=user_id,
        source_id=source_id,
        kind=SourceKind.NORMATIVE,
        container=container,
    )


@router.delete(
    "/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_normative_document(
    user_id: UUID,
    source_id: UUID,
    container: ContainerDependency,
) -> Response:
    """Удаляет нормативный source N через lifecycle cleanup."""
    return await delete_source_response(
        user_id=user_id,
        source_id=source_id,
        kind=SourceKind.NORMATIVE,
        container=container,
    )
