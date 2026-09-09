# services/api-gateway/src/api_gateway/transport/app.py

"""FastAPI application factory и lifecycle API Gateway."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI
from plan_validator_common.observability import (
    configure_logging,
    reset_logging,
)

from api_gateway.core.container import (
    GatewayContainer,
    build_container,
)
from api_gateway.core.settings import (
    GatewaySettings,
    load_gateway_settings,
)
from api_gateway.transport.errors import (
    UnhandledExceptionMiddleware,
    register_error_handlers,
)
from api_gateway.transport.middleware import (
    RequestContextMiddleware,
)
from api_gateway.transport.routers.api_v1 import (
    router as api_v1_router,
)
from api_gateway.transport.routers.health import (
    router as health_router,
)


@asynccontextmanager
async def application_lifespan(
    app: FastAPI,
) -> AsyncIterator[None]:
    """Настраивает observability и readiness вокруг lifespan процесса."""
    container = cast(
        GatewayContainer,
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

    container.mark_ready()

    logger.info(
        "API Gateway started",
        extra={
            "event": "service_started",
            "version": (settings.service_version),
            "api_version": (settings.api_version),
            "environment": (settings.environment.value),
        },
    )

    try:
        yield
    finally:
        container.mark_not_ready()

        logger.info(
            "API Gateway stopped",
            extra={
                "event": "service_stopped",
            },
        )

        reset_logging()


def create_app(
    settings: GatewaySettings | None = None,
) -> FastAPI:
    """Создаёт FastAPI app и связывает transport с composition root."""
    resolved_settings = settings or load_gateway_settings()

    container = build_container(resolved_settings)

    docs_enabled = resolved_settings.gateway.docs_enabled

    app = FastAPI(
        title="Plan Validator API Gateway",
        version=(resolved_settings.service_version),
        docs_url=("/docs" if docs_enabled else None),
        redoc_url=None,
        openapi_url=("/openapi.json" if docs_enabled else None),
        lifespan=application_lifespan,
    )

    app.state.container = container

    # Starlette оборачивает user middleware в обратном порядке добавления.
    # Поэтому error boundary добавляется первым, а request context вторым:
    #
    # RequestContextMiddleware
    #     -> UnhandledExceptionMiddleware
    #         -> FastAPI
    #
    # Так unexpected exception остаётся внутри активного correlation context.
    app.add_middleware(UnhandledExceptionMiddleware)
    app.add_middleware(RequestContextMiddleware)

    register_error_handlers(app)

    app.include_router(health_router)
    app.include_router(api_v1_router)

    return app
