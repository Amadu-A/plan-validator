# tests/unit/api_gateway/test_settings.py

"""Unit tests service-specific settings API Gateway."""

import pytest
from api_gateway.core.settings import (
    GatewaySettings,
)


def test_gateway_settings_use_safe_defaults() -> None:
    """Проверяет Gateway defaults без dotenv files."""
    settings = GatewaySettings(_env_file=None)

    assert settings.service_name == "api-gateway"
    assert settings.service_version == "0.1.0"
    assert settings.api_version == "v1"

    assert settings.gateway.host == "0.0.0.0"
    assert settings.gateway.port == 8000
    assert settings.gateway.docs_enabled is True

    assert settings.internal_http.connect_timeout_seconds == 3.0
    assert settings.internal_http.read_timeout_seconds == 30.0


def test_nested_environment_overrides_gateway_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Проверяет inherited env_nested_delimiter для nested Gateway settings."""
    monkeypatch.setenv(
        "PLAN_VALIDATOR_GATEWAY__PORT",
        "9010",
    )
    monkeypatch.setenv(
        "PLAN_VALIDATOR_INTERNAL_HTTP__READ_TIMEOUT_SECONDS",
        "12.5",
    )

    settings = GatewaySettings(_env_file=None)

    assert settings.gateway.port == 9010
    assert settings.internal_http.read_timeout_seconds == 12.5
