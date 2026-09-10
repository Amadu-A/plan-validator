# services/catalog-service/src/catalog_service/transport/errors.py

"""HTTP error boundary Catalog Service."""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from plan_validator_common.observability import get_log_context

from catalog_service.domain.exceptions import (
    CatalogDomainError,
    InvalidCatalogValueError,
    InvalidSectionHierarchyError,
    SectionNotFoundError,
)
from catalog_service.transport.schemas import ErrorDetail, ErrorResponse

_CORRELATION_SCOPE_KEY = "plan_validator.correlation_id"
_REQUEST_SCOPE_KEY = "plan_validator.request_id"

_LOGGER = logging.getLogger(__name__)


def register_error_handlers(app: FastAPI) -> None:
    """Регистрирует domain и unexpected exception mapping."""
    app.add_exception_handler(
        CatalogDomainError,
        handle_catalog_domain_error,
    )
    app.add_exception_handler(
        Exception,
        handle_unexpected_error,
    )


async def handle_catalog_domain_error(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Преобразует ожидаемую Catalog domain error без traceback."""
    if not isinstance(exc, CatalogDomainError):
        raise TypeError("Unsupported Catalog domain error")

    status_code, code, message = _classify_domain_error(exc)
    correlation_id, request_id = _get_request_identifiers(request)

    _LOGGER.warning(
        "Catalog request rejected",
        extra={
            "event": "catalog_request_error",
            "path": request.url.path,
            "status_code": status_code,
            "error_code": code,
            "error_type": type(exc).__name__,
            "correlation_id": correlation_id,
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
    """Пишет один HTTP-boundary traceback и скрывает internal details."""
    correlation_id, request_id = _get_request_identifiers(request)

    _LOGGER.exception(
        "Unhandled Catalog Service exception",
        extra={
            "event": "unhandled_exception",
            "path": request.url.path,
            "error_type": type(exc).__name__,
            "correlation_id": correlation_id,
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


def _classify_domain_error(
    exc: CatalogDomainError,
) -> tuple[int, str, str]:
    """Возвращает stable internal HTTP mapping."""
    if isinstance(exc, SectionNotFoundError):
        return 404, "section_not_found", str(exc)

    if isinstance(exc, InvalidSectionHierarchyError):
        return 400, "invalid_section_hierarchy", str(exc)

    if isinstance(exc, InvalidCatalogValueError):
        return 400, "invalid_catalog_value", str(exc)

    return 400, "catalog_error", "Catalog request failed"


def _get_request_identifiers(
    request: Request,
) -> tuple[str | None, str | None]:
    """Читает IDs из ASGI scope с ContextVar fallback."""
    context = get_log_context()

    correlation_id = request.scope.get(_CORRELATION_SCOPE_KEY)
    request_id = request.scope.get(_REQUEST_SCOPE_KEY)

    return (
        correlation_id if isinstance(correlation_id, str) else context.correlation_id,
        request_id if isinstance(request_id, str) else context.request_id,
    )


def _error_response(
    *,
    correlation_id: str | None,
    request_id: str | None,
    status_code: int,
    code: str,
    message: str,
) -> JSONResponse:
    """Создаёт error envelope и сохраняет identity headers."""
    body = ErrorResponse(
        error=ErrorDetail(
            code=code,
            message=message,
            correlation_id=correlation_id,
        )
    )

    headers: dict[str, str] = {}

    if correlation_id is not None:
        headers["X-Correlation-ID"] = correlation_id

    if request_id is not None:
        headers["X-Request-ID"] = request_id

    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(mode="json"),
        headers=headers,
    )
