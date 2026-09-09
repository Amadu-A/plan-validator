# services/auth-service/src/auth_service/transport/middleware.py

"""Pure ASGI correlation middleware Authentication Service."""

import logging
import re
import time

from plan_validator_common.observability import (
    new_correlation_id,
    scoped_log_context,
)
from starlette.datastructures import (
    Headers,
    MutableHeaders,
)
from starlette.types import (
    ASGIApp,
    Message,
    Receive,
    Scope,
    Send,
)

_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")

_CORRELATION_SCOPE_KEY = "plan_validator.correlation_id"
_REQUEST_SCOPE_KEY = "plan_validator.request_id"

_LOGGER = logging.getLogger(__name__)


class RequestContextMiddleware:
    """Изолирует correlation/request context internal HTTP request."""

    def __init__(
        self,
        app: ASGIApp,
    ) -> None:
        """Сохраняет следующий ASGI application."""
        self._app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        """Создаёт context только для HTTP protocol."""
        if scope["type"] != "http":
            await self._app(
                scope,
                receive,
                send,
            )
            return

        headers = Headers(scope=scope)

        correlation_id = _safe_identifier(headers.get("x-correlation-id"))
        request_id = _safe_identifier(headers.get("x-request-id"))

        _store_request_identifiers(
            scope=scope,
            correlation_id=correlation_id,
            request_id=request_id,
        )

        status_code = 500
        started_at = time.perf_counter()

        async def send_with_context(
            message: Message,
        ) -> None:
            """Добавляет identifiers в HTTP response headers."""
            nonlocal status_code

            if message["type"] == "http.response.start":
                status_code = int(message["status"])

                response_headers = MutableHeaders(scope=message)
                response_headers["X-Correlation-ID"] = correlation_id
                response_headers["X-Request-ID"] = request_id

            await send(message)

        with scoped_log_context(
            correlation_id=correlation_id,
            request_id=request_id,
        ):
            try:
                await self._app(
                    scope,
                    receive,
                    send_with_context,
                )
            finally:
                _LOGGER.info(
                    "HTTP request completed",
                    extra={
                        "event": "http_request",
                        "method": scope.get(
                            "method",
                            "UNKNOWN",
                        ),
                        "path": scope.get(
                            "path",
                            "",
                        ),
                        "status_code": (status_code),
                        "duration_ms": round(
                            (time.perf_counter() - started_at) * 1000,
                            3,
                        ),
                    },
                )


def _store_request_identifiers(
    *,
    scope: Scope,
    correlation_id: str,
    request_id: str,
) -> None:
    """Сохраняет IDs на весь ASGI request независимо от ContextVar lifetime."""
    scope[_CORRELATION_SCOPE_KEY] = correlation_id
    scope[_REQUEST_SCOPE_KEY] = request_id


def _safe_identifier(
    value: str | None,
) -> str:
    """Принимает bounded identifier либо генерирует новый."""
    if value is not None and _IDENTIFIER_PATTERN.fullmatch(value):
        return value

    return new_correlation_id()
