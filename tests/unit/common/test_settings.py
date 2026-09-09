# tests/unit/common/test_settings.py

"""Unit tests layered configuration общего package."""

from pathlib import Path

import pytest
from plan_validator_common.settings import (
    CommonSettings,
    Environment,
    LogLevel,
)
from pydantic import ValidationError


def test_settings_use_safe_defaults_without_dotenv() -> None:
    """Проверяет безопасные defaults при отключённом dotenv loading."""
    settings = CommonSettings(_env_file=None)

    assert settings.service_name == "plan-validator"
    assert settings.environment is Environment.DEVELOPMENT
    assert settings.log_level is LogLevel.INFO
    assert settings.log_file_max_bytes == 20 * 1024 * 1024
    assert settings.log_file_backup_count == 7
    assert settings.log_retention_days == 14


def test_settings_apply_baseline_override_and_process_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Проверяет приоритет `.env.example` -> `.env` -> process environment."""
    baseline = tmp_path / ".env.example"
    override = tmp_path / ".env"

    baseline.write_text(
        "PLAN_VALIDATOR_LOG_LEVEL=INFO\nPLAN_VALIDATOR_LOG_RETENTION_DAYS=14\n",
        encoding="utf-8",
    )

    override.write_text(
        "PLAN_VALIDATOR_LOG_LEVEL=WARNING\nPLAN_VALIDATOR_LOG_RETENTION_DAYS=21\n",
        encoding="utf-8",
    )

    monkeypatch.setenv(
        "PLAN_VALIDATOR_LOG_LEVEL",
        "ERROR",
    )

    settings = CommonSettings(
        _env_file=(
            baseline,
            override,
        )
    )

    assert settings.log_level is LogLevel.ERROR
    assert settings.log_retention_days == 21


def test_settings_explicit_argument_overrides_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Проверяет максимальный приоритет explicit init argument."""
    monkeypatch.setenv(
        "PLAN_VALIDATOR_SERVICE_NAME",
        "from-environment",
    )

    settings = CommonSettings(
        service_name="explicit-service",
        _env_file=None,
    )

    assert settings.service_name == "explicit-service"


def test_settings_reject_invalid_retention_values() -> None:
    """Проверяет валидацию положительных logging retention limits."""
    with pytest.raises(ValidationError):
        CommonSettings(
            log_retention_days=0,
            _env_file=None,
        )
