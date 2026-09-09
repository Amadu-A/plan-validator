# services/auth-service/src/auth_service/transport/app.py

"""FastAPI application factory Authentication Service."""

import logging
from collections.abc import (
    AsyncIterator,
)
from contextlib import (
    asynccontextmanager,
)
from typing import cast

from fastapi import FastAPI
from plan_validator_common.observability import (
    configure_logging,
    reset_logging,
)

from auth_service.core.container import (
    AuthContainer,
    build_container,
)
from auth_service.core.settings import (
    AuthSettings,
    load_auth_settings,
)
from auth_service.transport.errors import (
    register_error_handlers,
)
from auth_service.transport.middleware import (
    RequestContextMiddleware,
)
from auth_service.transport.routers.health import (
    router as health_router,
)
from auth_service.transport.routers.internal_v1 import (
    router as internal_v1_router,
)


@asynccontextmanager
async def application_lifespan(
    app: FastAPI,
) -> AsyncIterator[None]:
    """Управляет logging и database pool lifecycle."""
    container = cast(
        AuthContainer,
        app.state.container,
    )
    settings = container.settings

    configure_logging(
        service_name=settings.service_name,
        level=settings.log_level.value,
        log_root_dir=(settings.log_root_dir),
        log_to_file=(settings.log_to_file),
        file_max_bytes=(settings.log_file_max_bytes),
        file_backup_count=(settings.log_file_backup_count),
        retention_days=(settings.log_retention_days),
    )

    logger = logging.getLogger(__name__)

    logger.info(
        "Authentication Service started",
        extra={
            "event": "service_started",
            "version": (settings.service_version),
        },
    )

    try:
        yield
    finally:
        logger.info(
            "Authentication Service stopped",
            extra={
                "event": "service_stopped",
            },
        )

        await container.aclose()
        reset_logging()


def create_app(
    settings: AuthSettings | None = None,
) -> FastAPI:
    """Создаёт FastAPI app и Auth composition root."""
    resolved_settings = settings or load_auth_settings()

    container = build_container(resolved_settings)

    app = FastAPI(
        title="Plan Validator Auth Service",
        version=(resolved_settings.service_version),
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
