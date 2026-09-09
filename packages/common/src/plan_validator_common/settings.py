# packages/common/src/plan_validator_common/settings.py

"""Общие настройки Plan Validator на базе Pydantic Settings."""

from enum import StrEnum
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    """Поддерживаемые типы runtime-окружения приложения."""

    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class LogLevel(StrEnum):
    """Поддерживаемые уровни application logging."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class CommonSettings(BaseSettings):
    """Хранит общие process-level настройки всех сервисов Plan Validator."""

    model_config = SettingsConfigDict(
        env_prefix="PLAN_VALIDATOR_",
        env_nested_delimiter="__",
        env_file=(".env.example", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    service_name: str = Field(default="plan-validator", min_length=1)
    environment: Environment = Environment.DEVELOPMENT

    log_level: LogLevel = LogLevel.INFO
    log_root_dir: Path = Path("var/log")
    log_to_file: bool = True
    log_file_max_bytes: int = Field(default=20 * 1024 * 1024, gt=0)
    log_file_backup_count: int = Field(default=7, ge=1)
    log_retention_days: int = Field(default=14, ge=1)


def load_common_settings(*, service_name: str | None = None) -> CommonSettings:
    """Загружает layered settings и при необходимости задаёт имя процесса."""
    if service_name is None:
        return CommonSettings()

    return CommonSettings(service_name=service_name)
