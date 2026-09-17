# services/document-service/src/document_service/application/use_cases/documents.py

"""Project Document lifecycle, page selection и bounded processing use-cases."""

import asyncio
import json
from contextlib import suppress
from dataclasses import asdict
from datetime import timedelta
from hashlib import sha256
from pathlib import PurePath
from uuid import UUID, uuid4

from plan_validator_common.observability import log_execution_time

from document_service.application.dto import ProcessedPage
from document_service.application.ports.clock import Clock
from document_service.application.ports.pdf_processor import PdfProcessor
from document_service.application.ports.processing_limiter import ProcessingLimiter
from document_service.application.ports.storage import DocumentStorage
from document_service.application.ports.unit_of_work import DocumentUnitOfWorkFactory
from document_service.domain.exceptions import (
    DocumentDependencyError,
    DocumentValidationError,
    ProjectDocumentConflictError,
    ProjectDocumentNotFoundError,
)
from document_service.domain.models import (
    ContentModality,
    DocumentLifecycle,
    NormalizedContentFragment,
    ProjectDocument,
)

PDF_EXTENSION = ".pdf"
PDF_MIME = "application/pdf"
PDF_SIGNATURE_WINDOW = 1024


def _normalize_name(original_name: str) -> str:
    """Нормализует filename и разрешает только main project PDF."""
    normalized = original_name.replace("\\", "/").rsplit("/", maxsplit=1)[-1].strip()
    if not normalized or "\x00" in normalized:
        raise DocumentValidationError("Project document filename is invalid")
    if len(normalized) > 255:
        raise DocumentValidationError("Project document filename is too long")
    if PurePath(normalized).suffix.casefold() != PDF_EXTENSION:
        raise DocumentValidationError("Main project document must be PDF")
    return normalized


def _validate_pdf(content: bytes, *, max_upload_bytes: int) -> None:
    """Проверяет bounded size и реальную PDF signature."""
    if not content:
        raise DocumentValidationError("Project document must not be empty")
    if len(content) > max_upload_bytes:
        raise DocumentValidationError("Project document exceeds configured upload limit")
    if b"%PDF-" not in content[:PDF_SIGNATURE_WINDOW]:
        raise DocumentValidationError("Uploaded project document is not a valid PDF")


def _object_prefix(document: ProjectDocument) -> str:
    """Возвращает server-generated document storage prefix."""
    return f".objects/{document.user_id}/{document.id}"


class UploadProjectDocumentUseCase:
    """Сохраняет original PDF и owner-scoped registry metadata."""

    def __init__(
        self,
        *,
        uow_factory: DocumentUnitOfWorkFactory,
        storage: DocumentStorage,
        pdf_processor: PdfProcessor,
        clock: Clock,
        max_upload_bytes: int,
        retention_days: int,
    ) -> None:
        """Сохраняет upload collaborators."""
        self._uow_factory = uow_factory
        self._storage = storage
        self._pdf_processor = pdf_processor
        self._clock = clock
        self._max_upload_bytes = max_upload_bytes
        self._retention_days = retention_days

    @log_execution_time("document.upload_project_document")
    async def execute(
        self,
        *,
        user_id: UUID,
        original_name: str,
        content: bytes,
    ) -> ProjectDocument:
        """Валидирует, инспектирует и сохраняет PDF без queue side effects."""
        normalized_name = _normalize_name(original_name)
        _validate_pdf(content, max_upload_bytes=self._max_upload_bytes)
        try:
            inspection = await asyncio.to_thread(self._pdf_processor.inspect, content)
        except Exception as exc:
            raise DocumentValidationError("PDF cannot be opened safely") from exc
        if inspection.page_count < 1:
            raise DocumentValidationError("PDF must contain at least one page")

        now = self._clock.now()
        document_id = uuid4()
        storage_key = f".objects/{user_id}/{document_id}/original.pdf"
        document = ProjectDocument(
            id=document_id,
            user_id=user_id,
            original_name=normalized_name,
            storage_key=storage_key,
            mime_type=PDF_MIME,
            size_bytes=len(content),
            sha256=sha256(content).hexdigest(),
            page_count=inspection.page_count,
            selected_pages=tuple(range(1, inspection.page_count + 1)),
            lifecycle=DocumentLifecycle.ACTIVE,
            cleanup_error=None,
            created_at=now,
            updated_at=now,
            expires_at=now + timedelta(days=self._retention_days),
        )

        try:
            await self._storage.save(storage_key=storage_key, content=content)
            async with self._uow_factory() as uow:
                await uow.documents.add(document)
                await uow.commit()
        except Exception as exc:
            with suppress(Exception):
                await self._storage.delete_tree(storage_prefix=_object_prefix(document))
            raise DocumentDependencyError("Project document storage is unavailable") from exc
        return document


class GetProjectDocumentUseCase:
    """Возвращает owner-scoped document metadata."""

    def __init__(self, uow_factory: DocumentUnitOfWorkFactory) -> None:
        """Сохраняет UoW factory."""
        self._uow_factory = uow_factory

    async def execute(self, *, user_id: UUID, document_id: UUID) -> ProjectDocument:
        """Возвращает visible document либо not-found error."""
        async with self._uow_factory() as uow:
            document = await uow.documents.get_for_user(user_id=user_id, document_id=document_id)
        if document is None or document.lifecycle is DocumentLifecycle.DELETED:
            raise ProjectDocumentNotFoundError("Project document was not found")
        return document


class ListProjectDocumentsUseCase:
    """Возвращает visible Project Documents пользователя."""

    def __init__(self, uow_factory: DocumentUnitOfWorkFactory) -> None:
        """Сохраняет UoW factory."""
        self._uow_factory = uow_factory

    async def execute(self, *, user_id: UUID) -> tuple[ProjectDocument, ...]:
        """Возвращает owner-scoped list."""
        async with self._uow_factory() as uow:
            documents = await uow.documents.list_for_user(user_id)
        return tuple(documents)


class SelectProjectDocumentPagesUseCase:
    """Сохраняет bounded page selection для дальнейшего анализа."""

    def __init__(self, *, uow_factory: DocumentUnitOfWorkFactory, clock: Clock) -> None:
        """Сохраняет collaborators."""
        self._uow_factory = uow_factory
        self._clock = clock

    async def execute(
        self,
        *,
        user_id: UUID,
        document_id: UUID,
        page_numbers: tuple[int, ...],
    ) -> ProjectDocument:
        """Атомарно обновляет selection."""
        async with self._uow_factory() as uow:
            document = await uow.documents.get_for_user_for_update(
                user_id=user_id,
                document_id=document_id,
            )
            if document is None:
                raise ProjectDocumentNotFoundError("Project document was not found")
            selected = document.select_pages(
                page_numbers=page_numbers,
                changed_at=self._clock.now(),
            )
            await uow.documents.save(selected)
            await uow.commit()
        return selected


class ProcessProjectDocumentPagesUseCase:
    """Выполняет bounded synchronous extraction/render под CPU admission limiter."""

    def __init__(
        self,
        *,
        uow_factory: DocumentUnitOfWorkFactory,
        storage: DocumentStorage,
        pdf_processor: PdfProcessor,
        limiter: ProcessingLimiter,
        max_pages_per_request: int,
    ) -> None:
        """Сохраняет processing collaborators."""
        self._uow_factory = uow_factory
        self._storage = storage
        self._pdf_processor = pdf_processor
        self._limiter = limiter
        self._max_pages = max_pages_per_request

    @log_execution_time("document.process_pages")
    async def execute(
        self,
        *,
        user_id: UUID,
        document_id: UUID,
        page_numbers: tuple[int, ...] | None,
    ) -> tuple[ProcessedPage, ...]:
        """Возвращает persisted parser-neutral fragments выбранных страниц."""
        async with self._uow_factory() as uow:
            document = await uow.documents.get_for_user(user_id=user_id, document_id=document_id)
        if document is None or document.lifecycle is DocumentLifecycle.DELETED:
            raise ProjectDocumentNotFoundError("Project document was not found")
        if document.lifecycle is not DocumentLifecycle.ACTIVE:
            raise ProjectDocumentConflictError("Project document is being deleted")

        pages = tuple(sorted(set(page_numbers or document.selected_pages)))
        if not pages:
            raise DocumentValidationError("At least one page must be processed")
        if len(pages) > self._max_pages:
            raise DocumentValidationError("Too many pages in one processing request")
        if pages[0] < 1 or pages[-1] > document.page_count:
            raise DocumentValidationError("Processing page is outside document bounds")

        try:
            content = await self._storage.read(storage_key=document.storage_key)
        except Exception as exc:
            raise DocumentDependencyError("Project document storage is unavailable") from exc

        async def operation() -> tuple[object, ...]:
            return await self._pdf_processor.process_pages(content=content, page_numbers=pages)

        try:
            drafts = await self._limiter.run(operation)
            prefix = _object_prefix(document)
            processed: list[ProcessedPage] = []
            for draft in drafts:
                render_id = f"{prefix}/renders/page-{draft.page_number:04d}.png"
                await self._storage.save(storage_key=render_id, content=draft.render_png)
                fragments = tuple(
                    NormalizedContentFragment(
                        fragment_id=fragment.fragment_id,
                        page_number=fragment.page_number,
                        modality=fragment.modality,
                        text_origin=fragment.text_origin,
                        text=fragment.text,
                        image_artifact_id=(
                            render_id
                            if fragment.modality in {ContentModality.IMAGE, ContentModality.MIXED}
                            else None
                        ),
                        bbox=fragment.bbox,
                        ocr_confidence=fragment.ocr_confidence,
                    )
                    for fragment in draft.fragments
                )
                processed.append(
                    ProcessedPage(
                        page_number=draft.page_number,
                        render_artifact_id=render_id,
                        fragments=fragments,
                        native_text_chars=draft.native_text_chars,
                        visual_area_ratio=draft.visual_area_ratio,
                        used_ocr=draft.used_ocr,
                    )
                )

            manifest = json.dumps(
                {
                    "document_id": str(document.id),
                    "pages": [_page_manifest(page) for page in processed],
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            await self._storage.save(
                storage_key=f"{prefix}/analysis/manifest.json",
                content=manifest,
            )
            return tuple(processed)
        except DocumentValidationError:
            raise
        except Exception as exc:
            raise DocumentDependencyError("Document page processing failed") from exc


class DeleteProjectDocumentUseCase:
    """Выполняет logical-first, retryable physical cleanup Project Document."""

    def __init__(
        self,
        *,
        uow_factory: DocumentUnitOfWorkFactory,
        storage: DocumentStorage,
        clock: Clock,
    ) -> None:
        """Сохраняет cleanup collaborators."""
        self._uow_factory = uow_factory
        self._storage = storage
        self._clock = clock

    async def execute(self, *, user_id: UUID, document_id: UUID) -> ProjectDocument:
        """Удаляет document tree и подтверждает terminal lifecycle."""
        async with self._uow_factory() as uow:
            document = await uow.documents.get_for_user_for_update(
                user_id=user_id,
                document_id=document_id,
            )
            if document is None:
                raise ProjectDocumentNotFoundError("Project document was not found")
            if document.lifecycle is DocumentLifecycle.DELETED:
                return document
            pending = document.request_delete(changed_at=self._clock.now())
            await uow.documents.save(pending)
            await uow.commit()

        try:
            await self._storage.delete_tree(storage_prefix=_object_prefix(pending))
        except Exception as exc:
            async with self._uow_factory() as uow:
                locked = await uow.documents.get_for_user_for_update(
                    user_id=user_id,
                    document_id=document_id,
                )
                if locked is not None:
                    failed = locked.mark_cleanup_failed(
                        changed_at=self._clock.now(),
                        error_message=f"{type(exc).__name__}: {exc}",
                    )
                    await uow.documents.save(failed)
                    await uow.commit()
            raise DocumentDependencyError("Project document cleanup failed") from exc

        async with self._uow_factory() as uow:
            locked = await uow.documents.get_for_user_for_update(
                user_id=user_id,
                document_id=document_id,
            )
            if locked is None:
                raise ProjectDocumentNotFoundError("Project document was not found")
            deleted = locked.mark_deleted(changed_at=self._clock.now())
            await uow.documents.save(deleted)
            await uow.commit()
        return deleted


def _page_manifest(page: ProcessedPage) -> dict[str, object]:
    """Преобразует page DTO в compact JSON-safe manifest."""
    fragments: list[dict[str, object]] = []
    for fragment in page.fragments:
        item = asdict(fragment)
        item["modality"] = fragment.modality.value
        item["text_origin"] = fragment.text_origin.value
        item["bbox"] = asdict(fragment.bbox)
        fragments.append(item)
    return {
        "page_number": page.page_number,
        "render_artifact_id": page.render_artifact_id,
        "native_text_chars": page.native_text_chars,
        "visual_area_ratio": page.visual_area_ratio,
        "used_ocr": page.used_ocr,
        "fragments": fragments,
    }
