# tests/architecture/test_gateway_context_contract.py

"""Architecture contract API Gateway facade временного Project Context."""

from pathlib import Path

from api_gateway.core.settings import GatewaySettings
from api_gateway.transport.context_schemas import (
    RegisterProjectContextSourceRequest,
)

_ROOT = Path(__file__).resolve().parents[2]

_GATEWAY = _ROOT / "services" / "api-gateway" / "src" / "api_gateway"


def _read(
    relative_path: str,
) -> str:
    """Читает UTF-8 project file."""
    return (_ROOT / relative_path).read_text(encoding="utf-8")


def test_gateway_context_application_port_is_framework_independent() -> None:
    """Application Context port не зависит от FastAPI/httpx."""
    content = _read(
        "services/api-gateway/src/api_gateway/application/context_service.py"
    ).casefold()

    assert "fastapi" not in content
    assert "httpx" not in content


def test_public_context_request_cannot_supply_user_id() -> None:
    """Ownership определяется Auth Service, а не JSON browser request."""
    assert "user_id" not in RegisterProjectContextSourceRequest.model_fields


def test_public_context_router_does_not_expose_index_or_search() -> None:
    """Normalized chunks/retrieval остаются internal Context API."""
    content = (_GATEWAY / "transport" / "routers" / "project_contexts.py").read_text(
        encoding="utf-8"
    )

    assert "/index" not in content
    assert "/search" not in content
    assert "enqueue_index" not in content
    assert "search_context" not in content


def test_gateway_context_http_timeout_remains_short() -> None:
    """Gateway lifecycle facade не может ждать десятки минут."""
    settings = GatewaySettings(_env_file=None)

    assert settings.internal_http.connect_timeout_seconds <= 3.0

    assert settings.internal_http.read_timeout_seconds <= 30.0

    assert settings.internal_http.read_timeout_seconds <= 60.0


def test_context_client_maps_transport_failure_to_temporary_dependency() -> None:
    """Фиксирует recovery classification DNS/connect/read failures."""
    content = _read("services/api-gateway/src/api_gateway/infrastructure/context_client.py")

    assert "httpx.TimeoutException" in content
    assert "httpx.TransportError" in content
    assert "TemporaryDependencyError" in content


def test_context_service_default_uses_docker_dns() -> None:
    """Фиксирует stable internal Context service name."""
    settings = GatewaySettings(_env_file=None)

    assert settings.context_service.base_url == "http://context-service:8000"
