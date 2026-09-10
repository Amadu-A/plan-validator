# services/api-gateway/src/api_gateway/transport/routers/catalog_sources.py

"""Public authenticated N/U managed source facade API Gateway."""

from typing import Annotated
from urllib.parse import quote, unquote
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, Response, status
from plan_validator_common.exceptions import ApplicationError, AuthenticationError

from api_gateway.application.auth_service import AuthUser
from api_gateway.application.catalog_sources import CatalogSourceKind
from api_gateway.core.container import GatewayContainer
from api_gateway.transport.catalog_source_schemas import (
    ManagedSourceListResponse,
    ManagedSourceResponse,
)
from api_gateway.transport.dependencies import get_container
from api_gateway.transport.session_cookie import read_session_cookie

router = APIRouter(
    prefix="/catalog",
    tags=["catalog-sources"],
)

ContainerDependency = Annotated[
    GatewayContainer,
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


def _decode_source_filename(encoded_name: str) -> str:
    """Декодирует ASCII-safe percent-encoded UTF-8 filename."""
    try:
        return unquote(
            encoded_name,
            encoding="utf-8",
            errors="strict",
        )
    except UnicodeDecodeError as exc:
        raise ApplicationError("X-Source-Filename is not valid UTF-8") from exc


async def _read_bounded_upload(
    *,
    request: Request,
    max_bytes: int,
) -> bytes:
    """Читает browser upload stream с жёстким memory limit."""
    content_length = request.headers.get("content-length")

    if content_length is not None:
        try:
            declared_size = int(content_length)
        except ValueError as exc:
            raise ApplicationError("Content-Length header is invalid") from exc

        if declared_size < 0 or declared_size > max_bytes:
            raise ApplicationError("Managed source exceeds the configured upload limit")

    chunks: list[bytes] = []
    total = 0

    async for chunk in request.stream():
        total += len(chunk)

        if total > max_bytes:
            raise ApplicationError("Managed source exceeds the configured upload limit")

        chunks.append(chunk)

    return b"".join(chunks)


def _content_response(
    *,
    file_name: str,
    mime_type: str,
    content: bytes,
) -> Response:
    """Создаёт browser-safe raw content response."""
    encoded_name = quote(
        file_name,
        safe="",
    )

    return Response(
        content=content,
        media_type=mime_type,
        headers={"Content-Disposition": (f"inline; filename*=UTF-8''{encoded_name}")},
    )


async def _list_sources(
    *,
    request: Request,
    section_id: UUID,
    kind: CatalogSourceKind,
    container: GatewayContainer,
) -> ManagedSourceListResponse:
    """Общий authenticated list flow N/U router."""
    user = await _resolve_authenticated_user(
        request=request,
        container=container,
    )

    sources = await container.catalog_sources.list_sources(
        user_id=user.id,
        section_id=section_id,
        kind=kind,
    )

    return ManagedSourceListResponse(
        sources=[ManagedSourceResponse.from_dto(source) for source in sources]
    )


async def _upload_source(
    *,
    request: Request,
    section_id: UUID,
    kind: CatalogSourceKind,
    encoded_name: str,
    container: GatewayContainer,
) -> ManagedSourceResponse:
    """Общий authenticated bounded upload flow N/U router."""
    user = await _resolve_authenticated_user(
        request=request,
        container=container,
    )

    content = await _read_bounded_upload(
        request=request,
        max_bytes=container.settings.gateway_upload.max_managed_source_bytes,
    )
    file_name = _decode_source_filename(encoded_name)

    source = await container.catalog_sources.upload_source(
        user_id=user.id,
        section_id=section_id,
        kind=kind,
        file_name=file_name,
        content=content,
    )

    return ManagedSourceResponse.from_dto(source)


async def _get_source(
    *,
    request: Request,
    source_id: UUID,
    kind: CatalogSourceKind,
    container: GatewayContainer,
) -> ManagedSourceResponse:
    """Общий authenticated metadata flow N/U router."""
    user = await _resolve_authenticated_user(
        request=request,
        container=container,
    )

    source = await container.catalog_sources.get_source(
        user_id=user.id,
        source_id=source_id,
        kind=kind,
    )

    return ManagedSourceResponse.from_dto(source)


async def _get_source_content(
    *,
    request: Request,
    source_id: UUID,
    kind: CatalogSourceKind,
    container: GatewayContainer,
) -> Response:
    """Общий authenticated content flow N/U router."""
    user = await _resolve_authenticated_user(
        request=request,
        container=container,
    )

    value = await container.catalog_sources.get_source_content(
        user_id=user.id,
        source_id=source_id,
        kind=kind,
    )

    return _content_response(
        file_name=value.file_name,
        mime_type=value.mime_type,
        content=value.content,
    )


async def _delete_source(
    *,
    request: Request,
    source_id: UUID,
    kind: CatalogSourceKind,
    container: GatewayContainer,
) -> Response:
    """Общий authenticated delete flow N/U router."""
    user = await _resolve_authenticated_user(
        request=request,
        container=container,
    )

    await container.catalog_sources.delete_source(
        user_id=user.id,
        source_id=source_id,
        kind=kind,
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/normative-documents",
    response_model=ManagedSourceListResponse,
)
async def list_normative_documents(
    request: Request,
    section_id: UUID,
    container: ContainerDependency,
) -> ManagedSourceListResponse:
    """Возвращает normative documents N текущего пользователя."""
    return await _list_sources(
        request=request,
        section_id=section_id,
        kind=CatalogSourceKind.NORMATIVE,
        container=container,
    )


@router.post(
    "/normative-documents",
    response_model=ManagedSourceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_normative_document(
    request: Request,
    section_id: UUID,
    source_filename: EncodedFilenameHeader,
    container: ContainerDependency,
) -> ManagedSourceResponse:
    """Загружает normative document N текущего пользователя."""
    return await _upload_source(
        request=request,
        section_id=section_id,
        kind=CatalogSourceKind.NORMATIVE,
        encoded_name=source_filename,
        container=container,
    )


@router.get(
    "/normative-documents/{source_id}",
    response_model=ManagedSourceResponse,
)
async def get_normative_document(
    source_id: UUID,
    request: Request,
    container: ContainerDependency,
) -> ManagedSourceResponse:
    """Возвращает metadata normative document N."""
    return await _get_source(
        request=request,
        source_id=source_id,
        kind=CatalogSourceKind.NORMATIVE,
        container=container,
    )


@router.get(
    "/normative-documents/{source_id}/content",
    response_class=Response,
)
async def get_normative_document_content(
    source_id: UUID,
    request: Request,
    container: ContainerDependency,
) -> Response:
    """Возвращает content normative document N."""
    return await _get_source_content(
        request=request,
        source_id=source_id,
        kind=CatalogSourceKind.NORMATIVE,
        container=container,
    )


@router.delete(
    "/normative-documents/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_normative_document(
    source_id: UUID,
    request: Request,
    container: ContainerDependency,
) -> Response:
    """Удаляет normative document N."""
    return await _delete_source(
        request=request,
        source_id=source_id,
        kind=CatalogSourceKind.NORMATIVE,
        container=container,
    )


@router.get(
    "/user-documents",
    response_model=ManagedSourceListResponse,
)
async def list_user_documents(
    request: Request,
    section_id: UUID,
    container: ContainerDependency,
) -> ManagedSourceListResponse:
    """Возвращает user package documents U текущего пользователя."""
    return await _list_sources(
        request=request,
        section_id=section_id,
        kind=CatalogSourceKind.USER,
        container=container,
    )


@router.post(
    "/user-documents",
    response_model=ManagedSourceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_user_document(
    request: Request,
    section_id: UUID,
    source_filename: EncodedFilenameHeader,
    container: ContainerDependency,
) -> ManagedSourceResponse:
    """Загружает user package document U текущего пользователя."""
    return await _upload_source(
        request=request,
        section_id=section_id,
        kind=CatalogSourceKind.USER,
        encoded_name=source_filename,
        container=container,
    )


@router.get(
    "/user-documents/{source_id}",
    response_model=ManagedSourceResponse,
)
async def get_user_document(
    source_id: UUID,
    request: Request,
    container: ContainerDependency,
) -> ManagedSourceResponse:
    """Возвращает metadata user package document U."""
    return await _get_source(
        request=request,
        source_id=source_id,
        kind=CatalogSourceKind.USER,
        container=container,
    )


@router.get(
    "/user-documents/{source_id}/content",
    response_class=Response,
)
async def get_user_document_content(
    source_id: UUID,
    request: Request,
    container: ContainerDependency,
) -> Response:
    """Возвращает content user package document U."""
    return await _get_source_content(
        request=request,
        source_id=source_id,
        kind=CatalogSourceKind.USER,
        container=container,
    )


@router.delete(
    "/user-documents/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_user_document(
    source_id: UUID,
    request: Request,
    container: ContainerDependency,
) -> Response:
    """Удаляет user package document U."""
    return await _delete_source(
        request=request,
        source_id=source_id,
        kind=CatalogSourceKind.USER,
        container=container,
    )
