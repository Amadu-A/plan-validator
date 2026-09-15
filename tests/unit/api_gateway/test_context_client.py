# tests/unit/api_gateway/test_context_client.py

"""Unit tests Gateway HTTP adapter Context Service."""

import asyncio
import json
from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest
from api_gateway.application.context_service import (
    ContextSourceKind,
    ContextSourceState,
    ProjectContextState,
)
from api_gateway.infrastructure.context_client import (
    HttpContextServiceClient,
)
from plan_validator_common.exceptions import (
    ExternalDependencyError,
    TemporaryDependencyError,
)

USER_ID = UUID("11111111-1111-1111-1111-111111111111")

CONTEXT_ID = UUID("22222222-2222-2222-2222-222222222222")

SOURCE_ID = UUID("33333333-3333-3333-3333-333333333333")

NOW = datetime(
    2026,
    9,
    15,
    12,
    0,
    tzinfo=UTC,
)

SHA = "a" * 64


def context_payload(
    *,
    user_id: UUID = USER_ID,
) -> dict[str, object]:
    """Создаёт internal Context response payload."""
    return {
        "id": str(CONTEXT_ID),
        "user_id": str(user_id),
        "state": "active",
        "created_at": NOW.isoformat(),
        "updated_at": NOW.isoformat(),
        "expires_at": NOW.isoformat(),
    }


def source_payload() -> dict[str, object]:
    """Создаёт internal source response payload."""
    return {
        "id": str(SOURCE_ID),
        "context_id": str(CONTEXT_ID),
        "user_id": str(USER_ID),
        "kind": "T",
        "original_name": "tz.pdf",
        "source_sha256": SHA,
        "state": "awaiting_chunks",
        "active_fingerprint": None,
        "chunk_count": 0,
        "created_at": NOW.isoformat(),
        "updated_at": NOW.isoformat(),
    }


def test_create_context_sends_server_selected_user_id() -> None:
    """Проверяет exact owner propagation Gateway -> Context."""

    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        """Проверяет outbound create request."""
        assert request.url.path == "/internal/v1/context/contexts"

        payload = json.loads(request.content.decode("utf-8"))

        assert payload == {"user_id": str(USER_ID)}

        return httpx.Response(
            status_code=201,
            json=context_payload(),
        )

    client = HttpContextServiceClient(
        base_url="http://context.test",
        connect_timeout_seconds=1.0,
        read_timeout_seconds=5.0,
        transport=httpx.MockTransport(handler),
    )

    result = asyncio.run(client.create_context(user_id=USER_ID))

    asyncio.run(client.aclose())

    assert result.id == CONTEXT_ID
    assert result.user_id == USER_ID
    assert result.state is ProjectContextState.ACTIVE


def test_register_context_source_preserves_t_semantics() -> None:
    """Проверяет typed T metadata forwarding без normalized chunks."""

    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        """Проверяет source metadata request."""
        assert request.url.path == (f"/internal/v1/context/contexts/{CONTEXT_ID}/sources")

        payload = json.loads(request.content.decode("utf-8"))

        assert payload == {
            "user_id": str(USER_ID),
            "kind": "T",
            "original_name": "tz.pdf",
            "source_sha256": SHA,
        }

        assert "chunks" not in payload
        assert "text" not in payload

        return httpx.Response(
            status_code=201,
            json=source_payload(),
        )

    client = HttpContextServiceClient(
        base_url="http://context.test",
        connect_timeout_seconds=1.0,
        read_timeout_seconds=5.0,
        transport=httpx.MockTransport(handler),
    )

    result = asyncio.run(
        client.register_source(
            user_id=USER_ID,
            context_id=CONTEXT_ID,
            kind=(ContextSourceKind.TECHNICAL_ASSIGNMENT),
            original_name="tz.pdf",
            source_sha256=SHA,
        )
    )

    asyncio.run(client.aclose())

    assert result.id == SOURCE_ID
    assert result.kind is ContextSourceKind.TECHNICAL_ASSIGNMENT
    assert result.state is ContextSourceState.AWAITING_CHUNKS


def test_context_client_rejects_owner_mismatch() -> None:
    """Не доверяет downstream response с другим user_id."""

    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        """Возвращает spoofed downstream owner."""
        del request

        return httpx.Response(
            status_code=201,
            json=context_payload(user_id=UUID("99999999-9999-9999-9999-999999999999")),
        )

    client = HttpContextServiceClient(
        base_url="http://context.test",
        connect_timeout_seconds=1.0,
        read_timeout_seconds=5.0,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(
        ExternalDependencyError,
        match="owner identity mismatch",
    ):
        asyncio.run(client.create_context(user_id=USER_ID))

    asyncio.run(client.aclose())


def test_context_transport_failure_is_recoverable_dependency_error() -> None:
    """DNS/connect/reset/timeout class не превращается в application failure."""

    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        """Имитирует transient connection failure."""
        raise httpx.ConnectError(
            "temporary dns failure",
            request=request,
        )

    client = HttpContextServiceClient(
        base_url="http://context.test",
        connect_timeout_seconds=1.0,
        read_timeout_seconds=5.0,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(
        TemporaryDependencyError,
        match="temporarily unavailable",
    ):
        asyncio.run(
            client.get_context(
                user_id=USER_ID,
                context_id=CONTEXT_ID,
            )
        )

    asyncio.run(client.aclose())
