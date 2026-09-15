# tests/unit/api_gateway/test_settings.py

"""Unit tests service-specific settings API Gateway."""

import pytest
from api_gateway.core.settings import GatewaySettings


def test_gateway_settings_use_safe_defaults() -> None:
    """Проверяет Gateway defaults без dotenv files."""
    settings = GatewaySettings(_env_file=None)

    assert settings.service_name == "api-gateway"
    assert settings.service_version == "0.1.0"
    assert settings.api_version == "v1"

    assert settings.gateway.host == "0.0.0.0"
    assert settings.gateway.port == 8000
    assert settings.gateway.docs_enabled is True

    assert settings.gateway_upload.max_managed_source_bytes == 64 * 1024 * 1024

    assert settings.internal_http.connect_timeout_seconds == 3.0
    assert settings.internal_http.read_timeout_seconds == 30.0

    assert settings.auth_service.base_url == "http://auth-service:8000"
    assert settings.catalog_service.base_url == "http://catalog-service:8000"
    assert settings.context_service.base_url == "http://context-service:8000"


def test_nested_environment_overrides_gateway_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Проверяет inherited env_nested_delimiter для nested Gateway settings."""
    monkeypatch.setenv(
        "PLAN_VALIDATOR_GATEWAY__PORT",
        "9010",
    )

    monkeypatch.setenv(
        "PLAN_VALIDATOR_GATEWAY_UPLOAD__MAX_MANAGED_SOURCE_BYTES",
        "4096",
    )

    monkeypatch.setenv(
        "PLAN_VALIDATOR_INTERNAL_HTTP__READ_TIMEOUT_SECONDS",
        "12.5",
    )

    monkeypatch.setenv(
        "PLAN_VALIDATOR_CONTEXT_SERVICE__BASE_URL",
        "http://context-test:9000",
    )

    settings = GatewaySettings(_env_file=None)

    assert settings.gateway.port == 9010

    assert settings.gateway_upload.max_managed_source_bytes == 4096

    assert settings.internal_http.read_timeout_seconds == 12.5

    assert settings.context_service.base_url == "http://context-test:9000"


def test_gateway_rejects_unbounded_internal_http_timeout() -> None:
    """Не позволяет вернуть Gateway к многоминутному HTTP ожиданию."""
    with pytest.raises(ValueError):
        GatewaySettings(
            internal_http={
                "read_timeout_seconds": 1800.0,
            },
            _env_file=None,
        )
