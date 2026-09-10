# services/catalog-service/src/catalog_service/transport/app.py

"""FastAPI application factory Catalog Service."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI
from plan_validator_common.observability import configure_logging, reset_logging

from catalog_service.core.container import CatalogContainer, build_container
from catalog_service.core.settings import CatalogSettings, load_catalog_settings
from catalog_service.transport.errors import register_error_handlers
from catalog_service.transport.middleware import RequestContextMiddleware
from catalog_service.transport.routers.health import router as health_router
from catalog_service.transport.routers.internal_v1 import router as internal_v1_router


@asynccontextmanager
async def application_lifespan(
    app: FastAPI,
) -> AsyncIterator[None]:
    """Управляет logging и database pool lifecycle."""
    container = cast(
        CatalogContainer,
        app.state.container,
    )
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
        "Catalog Service started",
        extra={
            "event": "service_started",
            "version": settings.service_version,
        },
    )

    try:
        yield
    finally:
        logger.info(
            "Catalog Service stopped",
            extra={"event": "service_stopped"},
        )

        await container.aclose()
        reset_logging()


def create_app(
    settings: CatalogSettings | None = None,
) -> FastAPI:
    """Создаёт internal FastAPI application Catalog Service."""
    resolved_settings = settings or load_catalog_settings()
    container = build_container(resolved_settings)

    app = FastAPI(
        title="Plan Validator Catalog Service",
        version=resolved_settings.service_version,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=application_lifespan,
    )

    app.state.container = container

    app.add_middleware(RequestContextMiddleware)

    register_error_handlers(app)

    app.include_router(health_router)
    app.include_router(internal_v1_router)

    return app
