# tests/unit/api_gateway/test_http_client.py

"""Unit tests HTTPX implementation internal service application port."""

import asyncio
from collections.abc import Coroutine
from typing import Any

import httpx
import pytest
from api_gateway.infrastructure.http_client import (
    HttpInternalServiceClient,
)
from plan_validator_common.exceptions import (
    ExternalDependencyError,
    TemporaryDependencyError,
)
from plan_validator_common.observability import (
    scoped_log_context,
)


def run_async[T](
    coroutine: Coroutine[Any, Any, T],
) -> T:
    """Выполняет небольшую coroutine без дополнительного pytest async plugin."""
    return asyncio.run(coroutine)


def test_internal_client_propagates_correlation_headers() -> None:
    """Проверяет propagation request context во внутренний HTTP request."""
    captured_headers: dict[str, str] = {}

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        """Имитирует успешный internal service и сохраняет request headers."""
        captured_headers.update(request.headers)

        return httpx.Response(
            status_code=200,
            json={
                "status": "ok",
            },
        )

    async def scenario() -> dict[str, Any]:
        """Создаёт client, выполняет request и гарантированно закрывает pool."""
        client = HttpInternalServiceClient(
            base_url="http://internal-service:8000",
            connect_timeout_seconds=1,
            read_timeout_seconds=2,
            transport=httpx.MockTransport(handler),
        )

        try:
            with scoped_log_context(
                correlation_id="corr-123",
                request_id="req-456",
                job_id="job-789",
            ):
                return await client.get_json("/internal/v1/status")
        finally:
            await client.aclose()

    result = run_async(scenario())

    assert result == {
        "status": "ok",
    }

    assert captured_headers["x-correlation-id"] == "corr-123"
    assert captured_headers["x-request-id"] == "req-456"
    assert captured_headers["x-job-id"] == "job-789"


def test_internal_client_maps_server_error_to_temporary_failure() -> None:
    """Проверяет retryable classification HTTP 5xx."""

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        """Возвращает контролируемый upstream 503."""
        del request

        return httpx.Response(
            status_code=503,
            json={
                "error": "temporary",
            },
        )

    async def scenario() -> None:
        """Выполняет request и закрывает client после ошибки."""
        client = HttpInternalServiceClient(
            base_url="http://internal-service:8000",
            connect_timeout_seconds=1,
            read_timeout_seconds=2,
            transport=httpx.MockTransport(handler),
        )

        try:
            await client.get_json("/internal/v1/status")
        finally:
            await client.aclose()

    with pytest.raises(TemporaryDependencyError):
        run_async(scenario())


def test_internal_client_maps_client_error_to_external_failure() -> None:
    """Проверяет non-retryable classification HTTP 4xx."""

    def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        """Возвращает контролируемый upstream 404."""
        del request

        return httpx.Response(
            status_code=404,
            json={
                "error": "not-found",
            },
        )

    async def scenario() -> None:
        """Выполняет request и закрывает client после ошибки."""
        client = HttpInternalServiceClient(
            base_url="http://internal-service:8000",
            connect_timeout_seconds=1,
            read_timeout_seconds=2,
            transport=httpx.MockTransport(handler),
        )

        try:
            await client.get_json("/internal/v1/status")
        finally:
            await client.aclose()

    with pytest.raises(ExternalDependencyError):
        run_async(scenario())
