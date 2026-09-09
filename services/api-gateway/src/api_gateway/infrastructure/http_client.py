# services/api-gateway/src/api_gateway/infrastructure/http_client.py

"""HTTPX adapter для безопасных internal service calls API Gateway."""

from collections.abc import Mapping
from typing import Any, cast

import httpx
from plan_validator_common.exceptions import (
    ExternalDependencyError,
    TemporaryDependencyError,
)
from plan_validator_common.observability import (
    get_log_context,
    log_execution_time,
)

from api_gateway.application.internal_service import JsonObject


class HttpInternalServiceClient:
    """Реализует InternalServiceClient через HTTPX AsyncClient."""

    def __init__(
        self,
        *,
        base_url: str,
        connect_timeout_seconds: float,
        read_timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Создаёт bounded HTTP client с явными timeout и redirect policy."""
        if not base_url.startswith(
            (
                "http://",
                "https://",
            )
        ):
            raise ValueError("base_url must use http:// or https://")

        timeout = httpx.Timeout(
            timeout=read_timeout_seconds,
            connect=connect_timeout_seconds,
        )

        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            follow_redirects=False,
            transport=transport,
        )

    async def get_json(
        self,
        path: str,
    ) -> JsonObject:
        """Получает JSON object по internal endpoint."""
        return await self._request_json(
            method="GET",
            path=path,
            payload=None,
        )

    async def post_json(
        self,
        path: str,
        payload: Mapping[str, object],
    ) -> JsonObject:
        """Отправляет JSON object и возвращает JSON object response."""
        return await self._request_json(
            method="POST",
            path=path,
            payload=dict(payload),
        )

    async def aclose(self) -> None:
        """Закрывает underlying HTTPX connection pool."""
        await self._client.aclose()

    @log_execution_time("api_gateway.internal_http.request")
    async def _request_json(
        self,
        *,
        method: str,
        path: str,
        payload: dict[str, object] | None,
    ) -> JsonObject:
        """Выполняет значимый internal HTTP request и нормализует failures."""
        headers = self._build_context_headers()

        try:
            response = await self._client.request(
                method=method,
                url=path,
                json=payload,
                headers=headers,
            )
        except httpx.TimeoutException as exc:
            raise TemporaryDependencyError("Internal service request timed out") from exc
        except httpx.TransportError as exc:
            raise TemporaryDependencyError("Internal service transport failure") from exc

        if response.status_code >= 500:
            raise TemporaryDependencyError("Internal service returned server error")

        if response.status_code >= 300:
            raise ExternalDependencyError("Internal service returned unexpected HTTP status")

        try:
            response_payload = response.json()
        except ValueError as exc:
            raise ExternalDependencyError("Internal service returned invalid JSON") from exc

        if not isinstance(
            response_payload,
            dict,
        ):
            raise ExternalDependencyError("Internal service must return a JSON object")

        return cast(
            dict[str, Any],
            response_payload,
        )

    @staticmethod
    def _build_context_headers() -> dict[str, str]:
        """Прокидывает только безопасные correlation identifiers."""
        context = get_log_context()
        headers: dict[str, str] = {}

        if context.correlation_id is not None:
            headers["X-Correlation-ID"] = context.correlation_id

        if context.request_id is not None:
            headers["X-Request-ID"] = context.request_id

        if context.job_id is not None:
            headers["X-Job-ID"] = context.job_id

        return headers
