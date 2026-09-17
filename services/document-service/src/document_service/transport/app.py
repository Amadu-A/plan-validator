# services/document-service/src/document_service/transport/app.py

"""FastAPI application factory Document Service."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI
from plan_validator_common.observability import configure_logging, reset_logging

from document_service.core.container import DocumentContainer, build_container
from document_service.core.settings import DocumentSettings, load_document_settings
from document_service.domain.exceptions import (
    DocumentDependencyError,
    DocumentValidationError,
    ProjectDocumentConflictError,
    ProjectDocumentNotFoundError,
)
from document_service.transport.errors import (
    conflict_error_handler,
    dependency_error_handler,
    not_found_error_handler,
    validation_error_handler,
)
from document_service.transport.routers.documents import router as documents_router
from document_service.transport.routers.health import router as health_router


@asynccontextmanager
async def application_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Управляет structured logging и process resources."""
    container = cast(DocumentContainer, app.state.container)
    settings = container.settings
    configure_logging(
        service_name=settings.service_name,
        level=settings.log_level.value,
        log_root_dir=settings.log_root_dir,
        log_to_file=settings.log_to_file,
        file_max_bytes=settings.log_file_max_bytes,
        file_backup_count=settings.log_file_backup_count,
        retention_days=settings.log_retention_days,
    )
    logger = logging.getLogger(__name__)
    logger.info("Document Service started", extra={"event": "service_started"})
    try:
        yield
    finally:
        logger.info("Document Service stopped", extra={"event": "service_stopped"})
        await container.aclose()
        reset_logging()


def create_app(settings: DocumentSettings | None = None) -> FastAPI:
    """Создаёт internal Document API."""
    resolved = settings or load_document_settings()
    app = FastAPI(
        title="Plan Validator Document Service",
        version=resolved.service_version,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=application_lifespan,
    )
    app.state.container = build_container(resolved)
    app.add_exception_handler(DocumentValidationError, validation_error_handler)
    app.add_exception_handler(ProjectDocumentNotFoundError, not_found_error_handler)
    app.add_exception_handler(ProjectDocumentConflictError, conflict_error_handler)
    app.add_exception_handler(DocumentDependencyError, dependency_error_handler)
    app.include_router(health_router)
    app.include_router(documents_router)
    return app
