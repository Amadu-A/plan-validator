# services/retrieval-service/src/retrieval_service/transport/app.py

"""FastAPI application factory Retrieval Service."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI
from plan_validator_common.observability import configure_logging, reset_logging

from retrieval_service.core.container import RetrievalContainer, build_container
from retrieval_service.core.settings import RetrievalSettings, load_retrieval_settings
from retrieval_service.domain.exceptions import (
    RetrievalDependencyError,
    RetrievalSourceConflictError,
    RetrievalSourceNotFoundError,
    RetrievalValidationError,
)
from retrieval_service.transport.errors import (
    dependency_error_handler,
    source_conflict_handler,
    source_not_found_handler,
    validation_error_handler,
)
from retrieval_service.transport.middleware import RequestContextMiddleware
from retrieval_service.transport.routers.health import router as health_router
from retrieval_service.transport.routers.internal import router as internal_router
from retrieval_service.transport.routers.normative import router as normative_router
from retrieval_service.transport.routers.user import router as user_router


@asynccontextmanager
async def application_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Управляет structured logging и process-level dependencies."""
    container = cast(RetrievalContainer, app.state.container)
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
    logger.info(
        "Retrieval Service started",
        extra={
            "event": "service_started",
            "version": settings.service_version,
            "qdrant_alias": settings.retrieval_qdrant.alias_name,
        },
    )

    try:
        yield
    finally:
        logger.info("Retrieval Service stopped", extra={"event": "service_stopped"})
        await container.aclose()
        reset_logging()


def create_app(settings: RetrievalSettings | None = None) -> FastAPI:
    """Создаёт internal Retrieval API; public search через Gateway пока не публикуется."""
    resolved_settings = settings or load_retrieval_settings()
    app = FastAPI(
        title="Plan Validator Retrieval Service",
        version=resolved_settings.service_version,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=application_lifespan,
    )
    app.state.container = build_container(resolved_settings)
    app.add_middleware(RequestContextMiddleware)
    app.add_exception_handler(RetrievalValidationError, validation_error_handler)
    app.add_exception_handler(RetrievalSourceNotFoundError, source_not_found_handler)
    app.add_exception_handler(RetrievalSourceConflictError, source_conflict_handler)
    app.add_exception_handler(RetrievalDependencyError, dependency_error_handler)
    app.include_router(health_router)
    app.include_router(internal_router)
    app.include_router(normative_router)
    app.include_router(user_router)
    return app
