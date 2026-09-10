# services/retrieval-service/src/retrieval_service/transport/errors.py

"""Transport mapping Retrieval application/domain exceptions."""

from fastapi import Request
from fastapi.responses import JSONResponse

from retrieval_service.domain.exceptions import (
    RetrievalDependencyError,
    RetrievalSourceConflictError,
    RetrievalSourceNotFoundError,
    RetrievalValidationError,
)


def _error_response(*, status_code: int, code: str, message: str) -> JSONResponse:
    """Создаёт единый безопасный error envelope internal Retrieval API."""
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
    error: RetrievalValidationError,
) -> JSONResponse:
    """Преобразует retrieval validation failure в HTTP 422."""
    del request
    return _error_response(status_code=422, code="retrieval_validation_error", message=str(error))


async def source_not_found_handler(
    request: Request,
    error: RetrievalSourceNotFoundError,
) -> JSONResponse:
    """Преобразует отсутствующий source registry row в HTTP 404."""
    del request
    return _error_response(status_code=404, code="retrieval_source_not_found", message=str(error))


async def source_conflict_handler(
    request: Request,
    error: RetrievalSourceConflictError,
) -> JSONResponse:
    """Преобразует stale/deleted source operation в HTTP 409."""
    del request
    return _error_response(status_code=409, code="retrieval_source_conflict", message=str(error))


async def dependency_error_handler(
    request: Request,
    error: RetrievalDependencyError,
) -> JSONResponse:
    """Скрывает infrastructure details и сообщает временную HTTP 503 ошибку."""
    del request
    del error
    return _error_response(
        status_code=503,
        code="retrieval_dependency_unavailable",
        message="Retrieval dependency is temporarily unavailable",
    )
