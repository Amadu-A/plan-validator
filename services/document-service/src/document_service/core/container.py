# services/document-service/src/document_service/core/container.py

"""Composition root Document Service."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine

from document_service.application.use_cases.documents import (
    DeleteProjectDocumentUseCase,
    GetProjectDocumentUseCase,
    ListProjectDocumentsUseCase,
    ProcessProjectDocumentPagesUseCase,
    SelectProjectDocumentPagesUseCase,
    UploadProjectDocumentUseCase,
)
from document_service.core.settings import DocumentSettings
from document_service.infrastructure.clock import SystemClock
from document_service.infrastructure.database.engine import (
    create_document_engine,
    create_document_session_factory,
)
from document_service.infrastructure.database.health import SqlAlchemyDatabaseHealthProbe
from document_service.infrastructure.database.uow import SqlAlchemyDocumentUnitOfWorkFactory
from document_service.infrastructure.ocr import TesseractOcrEngine
from document_service.infrastructure.pdf_processor import PyMuPdfProcessor
from document_service.infrastructure.processing_limiter import AsyncSemaphoreProcessingLimiter
from document_service.infrastructure.storage import LocalDocumentStorage


@dataclass(slots=True)
class DocumentContainer:
    """Хранит process-level dependencies и use-cases Document Service."""

    settings: DocumentSettings
    engine: AsyncEngine
    uow_factory: SqlAlchemyDocumentUnitOfWorkFactory
    storage: LocalDocumentStorage
    clock: SystemClock
    database_health: SqlAlchemyDatabaseHealthProbe
    upload_document: UploadProjectDocumentUseCase
    get_document: GetProjectDocumentUseCase
    list_documents: ListProjectDocumentsUseCase
    select_pages: SelectProjectDocumentPagesUseCase
    process_pages: ProcessProjectDocumentPagesUseCase
    delete_document: DeleteProjectDocumentUseCase

    async def aclose(self) -> None:
        """Освобождает PostgreSQL engine."""
        await self.engine.dispose()


def build_container(settings: DocumentSettings) -> DocumentContainer:
    """Собирает concrete adapters только в composition root."""
    engine = create_document_engine(settings)
    session_factory = create_document_session_factory(engine)
    uow_factory = SqlAlchemyDocumentUnitOfWorkFactory(session_factory)
    storage = LocalDocumentStorage(settings.document_storage.root_dir)
    clock = SystemClock()
    processing = settings.document_processing
    ocr = TesseractOcrEngine(
        languages=processing.ocr_languages,
        timeout_seconds=processing.ocr_timeout_seconds,
    )
    pdf_processor = PyMuPdfProcessor(
        render_dpi=processing.render_dpi,
        native_text_min_chars=processing.native_text_min_chars,
        visual_area_threshold=processing.visual_area_threshold,
        ocr_enabled=processing.ocr_enabled,
        ocr_engine=ocr,
    )
    limiter = AsyncSemaphoreProcessingLimiter(processing.max_concurrent_tasks)

    return DocumentContainer(
        settings=settings,
        engine=engine,
        uow_factory=uow_factory,
        storage=storage,
        clock=clock,
        database_health=SqlAlchemyDatabaseHealthProbe(session_factory),
        upload_document=UploadProjectDocumentUseCase(
            uow_factory=uow_factory,
            storage=storage,
            pdf_processor=pdf_processor,
            clock=clock,
            max_upload_bytes=settings.document_storage.max_upload_bytes,
            retention_days=settings.document_retention.source_days,
        ),
        get_document=GetProjectDocumentUseCase(uow_factory),
        list_documents=ListProjectDocumentsUseCase(uow_factory),
        select_pages=SelectProjectDocumentPagesUseCase(
            uow_factory=uow_factory,
            clock=clock,
        ),
        process_pages=ProcessProjectDocumentPagesUseCase(
            uow_factory=uow_factory,
            storage=storage,
            pdf_processor=pdf_processor,
            limiter=limiter,
            max_pages_per_request=processing.max_pages_per_request,
        ),
        delete_document=DeleteProjectDocumentUseCase(
            uow_factory=uow_factory,
            storage=storage,
            clock=clock,
        ),
    )
