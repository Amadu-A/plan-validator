# tests/unit/auth_service/test_settings.py

"""Unit tests Pydantic Authentication settings."""

import pytest
from auth_service.core.settings import (
    AuthSettings,
)
from pydantic import (
    SecretStr,
    ValidationError,
)


def test_auth_settings_build_database_url_without_placeholder() -> None:
    """Проверяет service defaults и SQLAlchemy Psycopg URL."""
    settings = AuthSettings(
        postgres_password=SecretStr("unit-test-secret"),
        _env_file=None,
    )

    assert settings.service_name == "auth-service"
    assert settings.auth_database.host == "postgres"
    assert settings.auth_database.schema_name == "auth"
    assert settings.auth_session.ttl_seconds == 604800

    assert settings.database_url.startswith("postgresql+psycopg://")
    assert "unit-test-secret" in (settings.database_url)


def test_auth_settings_reject_placeholder_password() -> None:
    """Не позволяет случайно запустить service с `.env.example` placeholder."""
    with pytest.raises(ValidationError):
        AuthSettings(
            postgres_password=SecretStr("CHANGE_ME_GENERATED_AUTOMATICALLY"),
            _env_file=None,
        )
