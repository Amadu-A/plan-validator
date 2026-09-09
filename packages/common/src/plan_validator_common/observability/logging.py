# packages/common/src/plan_validator_common/observability/logging.py

"""Structured JSON logging и bounded file retention для Plan Validator."""

import json
import logging
import sys
import time
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from plan_validator_common.observability.correlation import get_log_context

_BASE_RECORD_KEYS = frozenset(logging.makeLogRecord({}).__dict__)

_RESERVED_OUTPUT_KEYS = frozenset(
    {
        "timestamp",
        "level",
        "logger",
        "service",
        "message",
        "exception",
    }
)

_MANAGED_HANDLER_PREFIX = "plan-validator:"

_SENSITIVE_KEY_PARTS = (
    "password",
    "secret",
    "token",
    "authorization",
    "cookie",
    "api_key",
    "apikey",
    "private_key",
    "access_key",
    "credential",
)


class CorrelationContextFilter(logging.Filter):
    """Добавляет correlation/request/job identifiers в каждый LogRecord."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Обогащает record текущим ContextVar context и пропускает запись."""
        context = get_log_context()

        context_values = {
            "correlation_id": context.correlation_id,
            "request_id": context.request_id,
            "job_id": context.job_id,
        }

        for key, value in context_values.items():
            if value is not None:
                record.__dict__.setdefault(key, value)

        return True


class JsonFormatter(logging.Formatter):
    """Форматирует LogRecord как одну UTF-8 JSON Lines запись."""

    def __init__(self, *, service_name: str) -> None:
        """Создаёт formatter с фиксированной process/service identity."""
        super().__init__()
        self._service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        """Преобразует standard и structured extra fields в JSON object."""
        payload: dict[str, object] = {
            "timestamp": (
                datetime.fromtimestamp(record.created, tz=UTC)
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z")
            ),
            "level": record.levelname,
            "logger": record.name,
            "service": self._service_name,
            "message": record.getMessage(),
        }

        for key, value in record.__dict__.items():
            if key in _BASE_RECORD_KEYS or key in _RESERVED_OUTPUT_KEYS:
                continue

            payload[key] = "[REDACTED]" if _is_sensitive_key(key) else value

        if record.exc_info is not None:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(
            payload,
            ensure_ascii=False,
            default=str,
            separators=(",", ":"),
        )


def _is_sensitive_key(key: str) -> bool:
    """Определяет structured field names, значения которых нужно скрывать."""
    normalized_key = key.casefold().replace("-", "_")

    return any(part in normalized_key for part in _SENSITIVE_KEY_PARTS)


def _validate_service_name(service_name: str) -> None:
    """Не позволяет service name превратить log path в произвольный filesystem path."""
    if not service_name or Path(service_name).name != service_name or service_name in {".", ".."}:
        raise ValueError("service_name must be a single non-empty path component")


def _resolve_log_level(level: str) -> int:
    """Преобразует textual logging level в numeric stdlib constant."""
    numeric_level = getattr(logging, level.upper(), None)

    if not isinstance(numeric_level, int):
        raise ValueError(f"Unsupported logging level: {level}")

    return numeric_level


def cleanup_expired_log_files(
    *,
    log_root_dir: Path,
    service_name: str,
    retention_days: int,
    now: float | None = None,
) -> int:
    """Удаляет только просроченные rotated log archives указанного service."""
    _validate_service_name(service_name)

    if retention_days < 1:
        raise ValueError("retention_days must be at least 1")

    service_log_dir = log_root_dir / service_name

    if not service_log_dir.exists():
        return 0

    reference_time = time.time() if now is None else now
    cutoff_timestamp = reference_time - retention_days * 24 * 60 * 60

    removed_count = 0

    for rotated_log in service_log_dir.glob(f"{service_name}.log.*"):
        try:
            if rotated_log.is_file() and rotated_log.stat().st_mtime < cutoff_timestamp:
                rotated_log.unlink()
                removed_count += 1
        except FileNotFoundError:
            continue

    return removed_count


def reset_logging() -> None:
    """Закрывает только handlers, которыми управляет common logging package."""
    root_logger = logging.getLogger()

    for handler in list(root_logger.handlers):
        if (handler.get_name() or "").startswith(_MANAGED_HANDLER_PREFIX):
            root_logger.removeHandler(handler)
            handler.close()


def configure_logging(
    *,
    service_name: str,
    level: str = "INFO",
    log_root_dir: Path = Path("var/log"),
    log_to_file: bool = True,
    file_max_bytes: int = 20 * 1024 * 1024,
    file_backup_count: int = 7,
    retention_days: int = 14,
) -> logging.Logger:
    """Настраивает JSON stdout и bounded per-service file logging процесса."""
    _validate_service_name(service_name)

    if file_max_bytes < 1:
        raise ValueError("file_max_bytes must be positive")

    if file_backup_count < 1:
        raise ValueError("file_backup_count must be at least 1")

    if retention_days < 1:
        raise ValueError("retention_days must be at least 1")

    numeric_level = _resolve_log_level(level)

    removed_count = cleanup_expired_log_files(
        log_root_dir=log_root_dir,
        service_name=service_name,
        retention_days=retention_days,
    )

    reset_logging()

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    formatter = JsonFormatter(service_name=service_name)
    context_filter = CorrelationContextFilter()

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.set_name(f"{_MANAGED_HANDLER_PREFIX}stdout")
    stream_handler.setLevel(numeric_level)
    stream_handler.setFormatter(formatter)
    stream_handler.addFilter(context_filter)

    root_logger.addHandler(stream_handler)

    if log_to_file:
        service_log_dir = log_root_dir / service_name
        service_log_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        log_file = service_log_dir / f"{service_name}.log"

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=file_max_bytes,
            backupCount=file_backup_count,
            encoding="utf-8",
        )

        file_handler.set_name(f"{_MANAGED_HANDLER_PREFIX}file:{service_name}")
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(context_filter)

        root_logger.addHandler(file_handler)

    if removed_count:
        logging.getLogger(__name__).info(
            "Expired rotated log files removed",
            extra={
                "event": "log_retention_cleanup",
                "removed_count": removed_count,
                "retention_days": retention_days,
            },
        )

    return root_logger
