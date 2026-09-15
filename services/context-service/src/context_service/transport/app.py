# services/context-service/src/context_service/transport/app.py

"""FastAPI application factory Context Service."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI
from plan_validator_common.observability import (
    configure_logging,
    reset_logging,
)

from context_service.core.container import (
    ContextContainer,
    build_container,
)
from context_service.core.settings import (
    ContextSettings,
    load_context_settings,
)
from context_service.domain.exceptions import (
    ContextDependencyError,
    ContextIndexJobConflictError,
    ContextIndexJobNotFoundError,
    ContextSourceConflictError,
    ContextSourceNotFoundError,
    ContextValidationError,
    ProjectContextConflictError,
    ProjectContextNotFoundError,
)
from context_service.transport.errors import (
    conflict_error_handler,
    dependency_error_handler,
    not_found_error_handler,
    validation_error_handler,
)
from context_service.transport.middleware import (
    RequestContextMiddleware,
)
from context_service.transport.routers.health import (
    router as health_router,
)
from context_service.transport.routers.indexing import (
    router as indexing_router,
)
from context_service.transport.routers.lifecycle import (
    router as lifecycle_router,
)
from context_service.transport.routers.search import (
    router as search_router,
)


@asynccontextmanager
async def application_lifespan(
    app: FastAPI,
) -> AsyncIterator[None]:
    """Управляет structured logging и process-level dependencies."""
    container = cast(
        ContextContainer,
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
        "Context Service started",
        extra={
            "event": "service_started",
            "version": settings.service_version,
            "index_queue": (settings.context_queue.index_queue_name),
        },
    )

    try:
        yield

    finally:
        logger.info(
            "Context Service stopped",
            extra={"event": "service_stopped"},
        )

        await container.aclose()
        reset_logging()


def create_app(
    settings: ContextSettings | None = None,
) -> FastAPI:
    """Создаёт internal Context API; public facade появится в Gateway."""
    resolved_settings = settings or load_context_settings()

    app = FastAPI(
        title="Plan Validator Context Service",
        version=resolved_settings.service_version,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=application_lifespan,
    )

    app.state.container = build_container(resolved_settings)

    app.add_middleware(RequestContextMiddleware)

    app.add_exception_handler(
        ContextValidationError,
        validation_error_handler,
    )

    for exception_type in (
        ProjectContextNotFoundError,
        ContextSourceNotFoundError,
        ContextIndexJobNotFoundError,
    ):
        app.add_exception_handler(
            exception_type,
            not_found_error_handler,
        )

    for exception_type in (
        ProjectContextConflictError,
        ContextSourceConflictError,
        ContextIndexJobConflictError,
    ):
        app.add_exception_handler(
            exception_type,
            conflict_error_handler,
        )

    app.add_exception_handler(
        ContextDependencyError,
        dependency_error_handler,
    )

    app.include_router(health_router)

    app.include_router(lifecycle_router)

    app.include_router(indexing_router)

    app.include_router(search_router)

    return app
