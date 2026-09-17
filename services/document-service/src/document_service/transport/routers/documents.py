# services/document-service/src/document_service/transport/routers/documents.py

"""Trusted internal Project Document HTTP API."""

from typing import Annotated
from urllib.parse import unquote
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status

from document_service.core.container import DocumentContainer
from document_service.domain.exceptions import DocumentValidationError
from document_service.transport.dependencies import get_container
from document_service.transport.schemas import (
    DocumentResponse,
    ProcessPagesRequest,
    ProcessPagesResponse,
    SelectPagesRequest,
    page_to_payload,
)

router = APIRouter(prefix="/internal/v1/documents", tags=["documents"])
ContainerDependency = Annotated[DocumentContainer, Depends(get_container)]
FilenameHeader = Annotated[
    str,
    Header(alias="X-Document-Filename", min_length=1, max_length=4096),
]
UserQuery = Annotated[UUID, Query()]


async def _read_bounded(request: Request, max_bytes: int) -> bytes:
    """Читает upload stream без unbounded memory growth."""
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > max_bytes:
            raise DocumentValidationError("Project document exceeds configured upload limit")
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    request: Request,
    user_id: UserQuery,
    encoded_name: FilenameHeader,
    container: ContainerDependency,
) -> DocumentResponse:
    """Принимает owner-scoped bounded PDF upload."""
    content = await _read_bounded(
        request,
        container.settings.document_storage.max_upload_bytes,
    )
    try:
        file_name = unquote(encoded_name, encoding="utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise DocumentValidationError("X-Document-Filename is not valid UTF-8") from exc
    document = await container.upload_document.execute(
        user_id=user_id,
        original_name=file_name,
        content=content,
    )
    return DocumentResponse.from_domain(document)


@router.get("")
async def list_documents(
    user_id: UserQuery,
    container: ContainerDependency,
) -> dict[str, object]:
    """Возвращает documents одного owner."""
    documents = await container.list_documents.execute(user_id=user_id)
    return {
        "documents": [
            DocumentResponse.from_domain(item).model_dump(mode="json") for item in documents
        ]
    }


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: UUID,
    user_id: UserQuery,
    container: ContainerDependency,
) -> DocumentResponse:
    """Возвращает owner-scoped document."""
    document = await container.get_document.execute(
        user_id=user_id,
        document_id=document_id,
    )
    return DocumentResponse.from_domain(document)


@router.put("/{document_id}/selection", response_model=DocumentResponse)
async def select_pages(
    document_id: UUID,
    body: SelectPagesRequest,
    user_id: UserQuery,
    container: ContainerDependency,
) -> DocumentResponse:
    """Сохраняет selected page list."""
    document = await container.select_pages.execute(
        user_id=user_id,
        document_id=document_id,
        page_numbers=tuple(body.page_numbers),
    )
    return DocumentResponse.from_domain(document)


@router.post("/{document_id}/process", response_model=ProcessPagesResponse)
async def process_pages(
    document_id: UUID,
    body: ProcessPagesRequest,
    user_id: UserQuery,
    container: ContainerDependency,
) -> ProcessPagesResponse:
    """Выполняет bounded native/OCR/image/mixed normalization."""
    pages = await container.process_pages.execute(
        user_id=user_id,
        document_id=document_id,
        page_numbers=None if body.page_numbers is None else tuple(body.page_numbers),
    )
    return ProcessPagesResponse(pages=[page_to_payload(page) for page in pages])


@router.get("/{document_id}/renders/{page_number}")
async def get_render(
    document_id: UUID,
    page_number: int,
    user_id: UserQuery,
    container: ContainerDependency,
) -> Response:
    """Возвращает persisted render только после owner validation."""
    document = await container.get_document.execute(
        user_id=user_id,
        document_id=document_id,
    )
    if page_number < 1 or page_number > document.page_count:
        raise DocumentValidationError("Render page is outside document bounds")
    key = f".objects/{user_id}/{document_id}/renders/page-{page_number:04d}.png"
    try:
        content = await container.storage.read(storage_key=key)
    except OSError as exc:
        raise DocumentValidationError("Requested page render is not available") from exc
    return Response(content=content, media_type="image/png")


@router.delete(
    "/{document_id}",
    response_model=DocumentResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def delete_document(
    document_id: UUID,
    user_id: UserQuery,
    container: ContainerDependency,
) -> DocumentResponse:
    """Запускает retryable physical cleanup document tree."""
    document = await container.delete_document.execute(
        user_id=user_id,
        document_id=document_id,
    )
    return DocumentResponse.from_domain(document)
