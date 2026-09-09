# services/api-gateway/src/api_gateway/transport/errors.py

"""Единый HTTP error boundary API Gateway."""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from plan_validator_common.exceptions import (
    ApplicationError,
    AuthenticationError,
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

from api_gateway.transport.schemas import (
    ErrorDetail,
    ErrorResponse,
)

_CORRELATION_SCOPE_KEY = "plan_validator.correlation_id"
_REQUEST_SCOPE_KEY = "plan_validator.request_id"

_LOGGER = logging.getLogger(__name__)


def register_error_handlers(
    app: FastAPI,
) -> None:
    """Регистрирует единый mapping project/unexpected exceptions в HTTP."""
    app.add_exception_handler(
        PlanValidatorError,
        handle_project_error,
    )
    app.add_exception_handler(
        Exception,
        handle_unexpected_error,
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

    correlation_id, request_id = _get_request_identifiers(request)

    _LOGGER.warning(
        "Project request failed",
        extra={
            "event": "request_error",
            "path": request.url.path,
            "status_code": status_code,
            "error_code": code,
            "error_type": (type(exc).__name__),
            "correlation_id": (correlation_id),
            "request_id": request_id,
        },
    )

    return _build_error_response(
        correlation_id=correlation_id,
        request_id=request_id,
        status_code=status_code,
        code=code,
        message=message,
    )


async def handle_unexpected_error(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Логирует один traceback и сохраняет IDs после ContextVar reset."""
    correlation_id, request_id = _get_request_identifiers(request)

    _LOGGER.exception(
        "Unhandled API Gateway exception",
        extra={
            "event": "unhandled_exception",
            "path": request.url.path,
            "error_type": (type(exc).__name__),
            "correlation_id": (correlation_id),
            "request_id": request_id,
        },
    )

    return _build_error_response(
        correlation_id=correlation_id,
        request_id=request_id,
        status_code=500,
        code="internal_error",
        message="Internal server error",
    )


def _get_request_identifiers(
    request: Request,
) -> tuple[
    str | None,
    str | None,
]:
    """Читает IDs из ASGI scope с ContextVar fallback."""
    context = get_log_context()

    scope_correlation_id = request.scope.get(_CORRELATION_SCOPE_KEY)
    scope_request_id = request.scope.get(_REQUEST_SCOPE_KEY)

    correlation_id = (
        scope_correlation_id
        if isinstance(
            scope_correlation_id,
            str,
        )
        else context.correlation_id
    )

    request_id = (
        scope_request_id
        if isinstance(
            scope_request_id,
            str,
        )
        else context.request_id
    )

    return (
        correlation_id,
        request_id,
    )


def _classify_project_error(
    exc: PlanValidatorError,
) -> tuple[int, str, str]:
    """Возвращает public HTTP mapping без зависимости application от FastAPI."""
    if isinstance(
        exc,
        AuthenticationError,
    ):
        return (
            401,
            "authentication_required",
            str(exc) or "Authentication required",
        )

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
    correlation_id: str | None,
    request_id: str | None,
    status_code: int,
    code: str,
    message: str,
) -> JSONResponse:
    """Создаёт error envelope и явно сохраняет request identifiers в headers."""
    body = ErrorResponse(
        error=ErrorDetail(
            code=code,
            message=message,
            correlation_id=(correlation_id),
        )
    )

    headers = _build_error_headers(
        correlation_id=correlation_id,
        request_id=request_id,
    )

    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(mode="json"),
        headers=headers,
    )


def _build_error_headers(
    *,
    correlation_id: str | None,
    request_id: str | None,
) -> dict[str, str]:
    """Формирует request identity headers для любого error response."""
    headers: dict[str, str] = {}

    if correlation_id is not None:
        headers["X-Correlation-ID"] = correlation_id

    if request_id is not None:
        headers["X-Request-ID"] = request_id

    return headers
