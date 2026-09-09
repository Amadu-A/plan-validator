# tests/transport/api_gateway/test_gateway.py

"""Transport tests public HTTP contract API Gateway."""

from pathlib import Path

from api_gateway.core.settings import (
    GatewaySettings,
)
from api_gateway.transport.app import (
    create_app,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from plan_validator_common.exceptions import (
    ResourceNotFoundError,
)
from plan_validator_common.settings import (
    Environment,
)


def build_test_app(
    tmp_path: Path,
) -> FastAPI:
    """Создаёт Gateway app без physical file logging для transport tests."""
    settings = GatewaySettings(
        service_name="api-gateway",
        environment=Environment.TEST,
        log_to_file=False,
        log_root_dir=tmp_path,
        gateway={
            "host": "127.0.0.1",
            "port": 8000,
            "docs_enabled": False,
        },
        _env_file=None,
    )

    return create_app(settings)


def test_health_and_versioned_system_endpoints(
    tmp_path: Path,
) -> None:
    """Проверяет unversioned health и versioned public API route."""
    app = build_test_app(tmp_path)

    with TestClient(app) as client:
        live_response = client.get("/health/live")
        ready_response = client.get("/health/ready")
        system_response = client.get("/api/v1/system/info")

    assert live_response.status_code == 200
    assert live_response.json()["status"] == "alive"

    assert ready_response.status_code == 200
    assert ready_response.json()["status"] == "ready"

    assert system_response.status_code == 200

    assert system_response.json() == {
        "service": "api-gateway",
        "service_version": "0.1.0",
        "api_version": "v1",
        "environment": "test",
    }


def test_readiness_returns_503_after_container_marked_not_ready(
    tmp_path: Path,
) -> None:
    """Проверяет operational 503 без подмены readiness liveness-ответом."""
    app = build_test_app(tmp_path)

    with TestClient(app) as client:
        app.state.container.mark_not_ready()

        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"


def test_request_context_echoes_safe_identifiers(
    tmp_path: Path,
) -> None:
    """Проверяет propagation correlation/request identifiers через boundary."""
    app = build_test_app(tmp_path)

    with TestClient(app) as client:
        response = client.get(
            "/health/live",
            headers={
                "X-Correlation-ID": "corr-123",
                "X-Request-ID": "req-456",
            },
        )

    assert response.headers["X-Correlation-ID"] == "corr-123"
    assert response.headers["X-Request-ID"] == "req-456"


def test_invalid_external_identifier_is_replaced(
    tmp_path: Path,
) -> None:
    """Проверяет bounded validation недоверенного correlation header."""
    app = build_test_app(tmp_path)

    invalid_identifier = "x" * 500

    with TestClient(app) as client:
        response = client.get(
            "/health/live",
            headers={
                "X-Correlation-ID": (invalid_identifier),
            },
        )

    returned_identifier = response.headers["X-Correlation-ID"]

    assert returned_identifier != invalid_identifier
    assert len(returned_identifier) == 32


def test_project_exception_uses_public_error_contract(
    tmp_path: Path,
) -> None:
    """Проверяет mapping common application exception в единый error envelope."""
    app = build_test_app(tmp_path)

    @app.get("/test/not-found")
    async def not_found() -> None:
        """Создаёт контролируемую expected application error."""
        raise ResourceNotFoundError("Requested test resource was not found")

    with TestClient(
        app,
        raise_server_exceptions=False,
    ) as client:
        response = client.get(
            "/test/not-found",
            headers={
                "X-Correlation-ID": "corr-error",
            },
        )

    assert response.status_code == 404

    assert response.json() == {
        "error": {
            "code": "resource_not_found",
            "message": ("Requested test resource was not found"),
            "correlation_id": "corr-error",
        }
    }


def test_unexpected_exception_preserves_correlation_context(
    tmp_path: Path,
) -> None:
    """Проверяет generic 500 без утечки details и потери request identifiers."""
    app = build_test_app(tmp_path)

    @app.get("/test/crash")
    async def crash() -> None:
        """Создаёт unexpected exception для проверки HTTP error boundary."""
        raise RuntimeError("private implementation detail")

    with TestClient(
        app,
        raise_server_exceptions=False,
    ) as client:
        response = client.get(
            "/test/crash",
            headers={
                "X-Correlation-ID": "corr-crash",
                "X-Request-ID": "req-crash",
            },
        )

    assert response.status_code == 500

    assert response.json() == {
        "error": {
            "code": "internal_error",
            "message": "Internal server error",
            "correlation_id": "corr-crash",
        }
    }

    assert response.headers["X-Correlation-ID"] == "corr-crash"
    assert response.headers["X-Request-ID"] == "req-crash"

    assert "private implementation detail" not in response.text
