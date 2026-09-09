# services/api-gateway/src/api_gateway/transport/errors.py

"""Единый HTTP error boundary API Gateway."""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from plan_validator_common.exceptions import (
    ApplicationError,
    ConfigurationError,
    ExternalDependencyError,
    PlanValidatorError,
    ResourceConflictError,
    ResourceNotFoundError,
    TemporaryDependencyError,
)
from plan_validator_common.observability import (
    get_log_context,
)
from starlette.types import ASGIApp, Receive, Scope, Send

from api_gateway.transport.schemas import (
    ErrorDetail,
    ErrorResponse,
)

_LOGGER = logging.getLogger(__name__)


class UnhandledExceptionMiddleware:
    """Обрабатывает unexpected HTTP exceptions внутри request correlation context."""

    def __init__(self, app: ASGIApp) -> None:
        """Сохраняет следующий ASGI application в error-boundary chain."""
        self._app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        """Возвращает generic 500 и пишет единственный traceback на HTTP boundary."""
        try:
            await self._app(
                scope,
                receive,
                send,
            )
        except Exception as exc:
            if scope["type"] != "http":
                raise

            _LOGGER.exception(
                "Unhandled API Gateway exception",
                extra={
                    "event": "unhandled_exception",
                    "path": scope.get(
                        "path",
                        "",
                    ),
                    "error_type": type(exc).__name__,
                },
            )

            response = _build_error_response(
                status_code=500,
                code="internal_error",
                message="Internal server error",
            )

            await response(
                scope,
                receive,
                send,
            )


def register_error_handlers(
    app: FastAPI,
) -> None:
    """Регистрирует mapping ожидаемых project exceptions в HTTP."""
    app.add_exception_handler(
        PlanValidatorError,
        handle_project_error,
    )


async def handle_project_error(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Преобразует ожидаемую project error без traceback duplication."""
    if not isinstance(
        exc,
        PlanValidatorError,
    ):
        raise TypeError("handle_project_error received unsupported exception")

    status_code, code, message = _classify_project_error(exc)

    _LOGGER.warning(
        "Project request failed",
        extra={
            "event": "request_error",
            "path": request.url.path,
            "status_code": status_code,
            "error_code": code,
            "error_type": type(exc).__name__,
        },
    )

    return _build_error_response(
        status_code=status_code,
        code=code,
        message=message,
    )


def _classify_project_error(
    exc: PlanValidatorError,
) -> tuple[int, str, str]:
    """Возвращает public HTTP mapping без зависимости application от FastAPI."""
    if isinstance(
        exc,
        ResourceNotFoundError,
    ):
        return (
            404,
            "resource_not_found",
            str(exc) or "Resource not found",
        )

    if isinstance(
        exc,
        ResourceConflictError,
    ):
        return (
            409,
            "resource_conflict",
            str(exc) or "Resource conflict",
        )

    if isinstance(
        exc,
        TemporaryDependencyError,
    ):
        return (
            503,
            "temporary_dependency_error",
            "Temporary dependency failure",
        )

    if isinstance(
        exc,
        ExternalDependencyError,
    ):
        return (
            502,
            "external_dependency_error",
            "External dependency failure",
        )

    if isinstance(
        exc,
        ConfigurationError,
    ):
        return (
            500,
            "configuration_error",
            "Service configuration error",
        )

    if isinstance(
        exc,
        ApplicationError,
    ):
        return (
            400,
            "application_error",
            str(exc) or "Application error",
        )

    return (
        400,
        "plan_validator_error",
        "Request could not be completed",
    )


def _build_error_response(
    *,
    status_code: int,
    code: str,
    message: str,
) -> JSONResponse:
    """Создаёт единый JSON error envelope с correlation identifier."""
    context = get_log_context()

    body = ErrorResponse(
        error=ErrorDetail(
            code=code,
            message=message,
            correlation_id=(context.correlation_id),
        )
    )

    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(mode="json"),
    )
