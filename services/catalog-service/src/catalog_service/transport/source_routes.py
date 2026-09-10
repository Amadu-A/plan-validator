# services/catalog-service/src/catalog_service/transport/source_routes.py

"""Transport helpers отдельных N/U routers Catalog Service."""

from urllib.parse import quote, unquote
from uuid import UUID

from fastapi import Request, Response, status

from catalog_service.core.container import CatalogContainer
from catalog_service.domain.exceptions import InvalidManagedSourceUploadError
from catalog_service.domain.source import SourceKind
from catalog_service.transport.source_schemas import (
    ManagedSourceListResponse,
    ManagedSourceResponse,
)


def decode_source_filename(encoded_name: str) -> str:
    """Декодирует percent-encoded UTF-8 filename из ASCII-safe header."""
    try:
        return unquote(encoded_name, encoding="utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise InvalidManagedSourceUploadError("X-Source-Filename is not valid UTF-8") from exc


async def read_bounded_request_body(
    *,
    request: Request,
    max_bytes: int,
) -> bytes:
    """Читает streaming HTTP body с жёстким memory size limit."""
    content_length = request.headers.get("content-length")

    if content_length is not None:
        try:
            declared_size = int(content_length)
        except ValueError as exc:
            raise InvalidManagedSourceUploadError("Content-Length header is invalid") from exc

        if declared_size < 0 or declared_size > max_bytes:
            raise InvalidManagedSourceUploadError(
                "Managed source exceeds the configured upload limit"
            )

    chunks: list[bytes] = []
    total = 0

    async for chunk in request.stream():
        total += len(chunk)

        if total > max_bytes:
            raise InvalidManagedSourceUploadError(
                "Managed source exceeds the configured upload limit"
            )

        chunks.append(chunk)

    return b"".join(chunks)


async def list_sources_response(
    *,
    user_id: UUID,
    section_id: UUID,
    kind: SourceKind,
    container: CatalogContainer,
) -> ManagedSourceListResponse:
    """Вызывает list use-case и строит typed transport response."""
    sources = await container.list_managed_sources.execute(
        user_id=user_id,
        section_id=section_id,
        kind=kind,
    )

    return ManagedSourceListResponse(
        sources=[ManagedSourceResponse.from_domain(source) for source in sources]
    )


async def upload_source_response(
    *,
    user_id: UUID,
    section_id: UUID,
    kind: SourceKind,
    encoded_name: str,
    request: Request,
    container: CatalogContainer,
) -> ManagedSourceResponse:
    """Читает bounded upload и вызывает managed source upload use-case."""
    original_name = decode_source_filename(encoded_name)
    content = await read_bounded_request_body(
        request=request,
        max_bytes=container.settings.catalog_source_storage.max_upload_bytes,
    )

    source = await container.upload_managed_source.execute(
        user_id=user_id,
        section_id=section_id,
        kind=kind,
        original_name=original_name,
        content=content,
    )

    return ManagedSourceResponse.from_domain(source)


async def get_source_response(
    *,
    user_id: UUID,
    source_id: UUID,
    kind: SourceKind,
    container: CatalogContainer,
) -> ManagedSourceResponse:
    """Возвращает metadata одного managed source."""
    source = await container.get_managed_source.execute(
        user_id=user_id,
        source_id=source_id,
        kind=kind,
    )

    return ManagedSourceResponse.from_domain(source)


async def get_source_content_response(
    *,
    user_id: UUID,
    source_id: UUID,
    kind: SourceKind,
    container: CatalogContainer,
) -> Response:
    """Возвращает source bytes и ASCII-safe filename headers."""
    value = await container.get_managed_source_content.execute(
        user_id=user_id,
        source_id=source_id,
        kind=kind,
    )

    encoded_name = quote(
        value.source.original_name,
        safe="",
    )

    return Response(
        content=value.content,
        media_type=value.source.mime_type,
        headers={
            "Content-Disposition": (f"inline; filename*=UTF-8''{encoded_name}"),
            "X-Source-Filename": encoded_name,
        },
    )


async def delete_source_response(
    *,
    user_id: UUID,
    source_id: UUID,
    kind: SourceKind,
    container: CatalogContainer,
) -> Response:
    """Запускает crash-safe delete lifecycle и возвращает 204."""
    await container.delete_managed_source.execute(
        user_id=user_id,
        source_id=source_id,
        kind=kind,
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
