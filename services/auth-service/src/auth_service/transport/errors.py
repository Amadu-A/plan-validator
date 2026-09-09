# services/auth-service/src/auth_service/transport/errors.py

"""HTTP error boundary Authentication Service."""

import logging

from fastapi import (
    FastAPI,
    Request,
)
from fastapi.responses import (
    JSONResponse,
)
from plan_validator_common.observability import (
    get_log_context,
)

from auth_service.domain.exceptions import (
    AuthDomainError,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidSessionError,
    UserInactiveError,
)
from auth_service.transport.schemas import (
    ErrorDetail,
    ErrorResponse,
)

_CORRELATION_SCOPE_KEY = "plan_validator.correlation_id"
_REQUEST_SCOPE_KEY = "plan_validator.request_id"

_LOGGER = logging.getLogger(__name__)


def register_error_handlers(
    app: FastAPI,
) -> None:
    """Регистрирует domain/unexpected exception mapping."""
    app.add_exception_handler(
        AuthDomainError,
        handle_auth_domain_error,
    )
    app.add_exception_handler(
        Exception,
        handle_unexpected_error,
    )


async def handle_auth_domain_error(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Преобразует ожидаемую Auth domain error без traceback."""
    if not isinstance(
        exc,
        AuthDomainError,
    ):
        raise TypeError("Unsupported Auth domain error")

    status_code, code, message = _classify_domain_error(exc)

    correlation_id, request_id = _get_request_identifiers(request)

    _LOGGER.warning(
        "Authentication request rejected",
        extra={
            "event": "auth_request_error",
            "path": request.url.path,
            "status_code": status_code,
            "error_code": code,
            "error_type": (type(exc).__name__),
            "correlation_id": (correlation_id),
            "request_id": request_id,
        },
    )

    return _error_response(
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
    """Пишет один traceback и сохраняет IDs после выхода из middleware context."""
    correlation_id, request_id = _get_request_identifiers(request)

    _LOGGER.exception(
        "Unhandled Authentication Service exception",
        extra={
            "event": "unhandled_exception",
            "path": request.url.path,
            "error_type": (type(exc).__name__),
            "correlation_id": (correlation_id),
            "request_id": request_id,
        },
    )

    return _error_response(
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
    """Читает request IDs из ASGI scope с ContextVar fallback."""
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


def _classify_domain_error(
    exc: AuthDomainError,
) -> tuple[int, str, str]:
    """Возвращает stable internal HTTP mapping."""
    if isinstance(
        exc,
        EmailAlreadyRegisteredError,
    ):
        return (
            409,
            "email_already_registered",
            "Email is already registered",
        )

    if isinstance(
        exc,
        InvalidCredentialsError,
    ):
        return (
            401,
            "invalid_credentials",
            "Invalid email or password",
        )

    if isinstance(
        exc,
        InvalidSessionError,
    ):
        return (
            401,
            "invalid_session",
            "Session is invalid or expired",
        )

    if isinstance(
        exc,
        UserInactiveError,
    ):
        return (
            401,
            "user_inactive",
            "User is inactive",
        )

    return (
        400,
        "auth_error",
        "Authentication request failed",
    )


def _error_response(
    *,
    correlation_id: str | None,
    request_id: str | None,
    status_code: int,
    code: str,
    message: str,
) -> JSONResponse:
    """Создаёт internal error response и явно сохраняет identity headers."""
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
    """Формирует correlation/request headers любого Auth error response."""
    headers: dict[str, str] = {}

    if correlation_id is not None:
        headers["X-Correlation-ID"] = correlation_id

    if request_id is not None:
        headers["X-Request-ID"] = request_id

    return headers
