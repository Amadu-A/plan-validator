# services/api-gateway/src/api_gateway/transport/middleware.py

"""Pure ASGI middleware request context и structured request timing."""

import logging
import re
import time

from plan_validator_common.observability import (
    new_correlation_id,
    scoped_log_context,
)
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import (
    ASGIApp,
    Message,
    Receive,
    Scope,
    Send,
)

_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")

_LOGGER = logging.getLogger(__name__)


class RequestContextMiddleware:
    """Создаёт correlation/request context и пишет один HTTP summary log."""

    def __init__(
        self,
        app: ASGIApp,
    ) -> None:
        """Сохраняет следующий ASGI application в middleware chain."""
        self._app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        """Обрабатывает HTTP context, не вмешиваясь в non-HTTP protocols."""
        if scope["type"] != "http":
            await self._app(
                scope,
                receive,
                send,
            )
            return

        headers = Headers(scope=scope)

        correlation_id = _normalize_request_identifier(headers.get("x-correlation-id"))
        request_id = _normalize_request_identifier(headers.get("x-request-id"))

        started_at = time.perf_counter()
        status_code = 500

        async def send_with_context(
            message: Message,
        ) -> None:
            """Добавляет response identifiers и запоминает HTTP status code."""
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
                duration_ms = round(
                    (time.perf_counter() - started_at) * 1000,
                    3,
                )

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
                        "duration_ms": (duration_ms),
                    },
                )


def _normalize_request_identifier(
    value: str | None,
) -> str:
    """Принимает безопасный identifier либо создаёт новый project identifier."""
    if value is not None and _IDENTIFIER_PATTERN.fullmatch(value):
        return value

    return new_correlation_id()
