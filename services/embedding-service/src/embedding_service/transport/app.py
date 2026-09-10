# services/embedding-service/src/embedding_service/transport/app.py

"""FastAPI application factory Embedding Service."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI
from plan_validator_common.observability import configure_logging, reset_logging

from embedding_service.core.container import EmbeddingContainer, build_container
from embedding_service.core.settings import EmbeddingSettings, load_embedding_settings
from embedding_service.transport.middleware import RequestContextMiddleware
from embedding_service.transport.routers.health import router as health_router
from embedding_service.transport.routers.internal_v1 import router as internal_v1_router


@asynccontextmanager
async def application_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Управляет structured logging lifecycle HTTP process."""
    container = cast(EmbeddingContainer, app.state.container)
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
        "Embedding Service started",
        extra={
            "event": "service_started",
            "version": settings.service_version,
            "model": settings.embedding_model.name,
        },
    )

    try:
        yield
    finally:
        logger.info("Embedding Service stopped", extra={"event": "service_stopped"})
        reset_logging()


def create_app(settings: EmbeddingSettings | None = None) -> FastAPI:
    """Создаёт internal FastAPI application без public embedding endpoint."""
    resolved_settings = settings or load_embedding_settings()
    app = FastAPI(
        title="Plan Validator Embedding Service",
        version=resolved_settings.service_version,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=application_lifespan,
    )
    app.state.container = build_container(resolved_settings)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(health_router)
    app.include_router(internal_v1_router)
    return app
