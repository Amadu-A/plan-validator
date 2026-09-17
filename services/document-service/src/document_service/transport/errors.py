# services/document-service/src/document_service/transport/errors.py

"""HTTP exception mapping Document Service."""

from fastapi import Request
from fastapi.responses import JSONResponse


def _response(status_code: int, code: str, message: str) -> JSONResponse:
    """Создаёт stable internal error envelope."""
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


async def validation_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """Map validation -> 400."""
    return _response(400, "document_validation_error", str(exc))


async def not_found_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """Map missing owner-scoped resource -> 404."""
    return _response(404, "document_not_found", str(exc))


async def conflict_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """Map lifecycle conflict -> 409."""
    return _response(409, "document_conflict", str(exc))


async def dependency_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """Map temporary dependency failure -> 503."""
    return _response(503, "document_dependency_error", str(exc))
