# services/context-service/src/context_service/transport/errors.py

"""Transport mapping Context application/domain exceptions."""

from fastapi import Request
from fastapi.responses import JSONResponse

from context_service.domain.exceptions import (
    ContextDependencyError,
    ContextServiceError,
    ContextValidationError,
)


def _error_response(
    *,
    status_code: int,
    code: str,
    message: str,
) -> JSONResponse:
    """Создаёт единый безопасный error envelope Context API."""
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
            }
        },
    )


async def validation_error_handler(
    request: Request,
    error: ContextValidationError,
) -> JSONResponse:
    """Преобразует domain validation failure в HTTP 422."""
    del request

    return _error_response(
        status_code=422,
        code="context_validation_error",
        message=str(error),
    )


async def not_found_error_handler(
    request: Request,
    error: ContextServiceError,
) -> JSONResponse:
    """Преобразует owner-safe missing Context resource в HTTP 404."""
    del request

    return _error_response(
        status_code=404,
        code="context_resource_not_found",
        message=str(error),
    )


async def conflict_error_handler(
    request: Request,
    error: ContextServiceError,
) -> JSONResponse:
    """Преобразует invalid lifecycle transition в HTTP 409."""
    del request

    return _error_response(
        status_code=409,
        code="context_conflict",
        message=str(error),
    )


async def dependency_error_handler(
    request: Request,
    error: ContextDependencyError,
) -> JSONResponse:
    """Скрывает infrastructure details и сообщает временную HTTP 503."""
    del request
    del error

    return _error_response(
        status_code=503,
        code="context_dependency_unavailable",
        message=("Context dependency is temporarily unavailable"),
    )
