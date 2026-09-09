# tests/unit/common/test_logging.py

"""Unit tests JSON logging, redaction, rotation и age cleanup."""

import json
import logging
import os
from pathlib import Path

from plan_validator_common.observability.correlation import (
    scoped_log_context,
)
from plan_validator_common.observability.logging import (
    cleanup_expired_log_files,
    configure_logging,
    reset_logging,
)


def test_json_logging_contains_context_and_redacts_sensitive_fields(
    tmp_path: Path,
) -> None:
    """Проверяет JSON Lines schema, correlation context и structured redaction."""
    configure_logging(
        service_name="test-service",
        log_root_dir=tmp_path,
        log_to_file=True,
    )

    with scoped_log_context(
        correlation_id="corr-1",
        request_id="req-1",
        job_id="job-1",
    ):
        logging.getLogger("tests.logging").info(
            "Structured event",
            extra={
                "event": "unit_test_event",
                "document_id": "doc-1",
                "password": "must-not-leak",
                "api_token": "must-not-leak",
            },
        )

    reset_logging()

    log_file = tmp_path / "test-service" / "test-service.log"

    payload = json.loads(log_file.read_text(encoding="utf-8").splitlines()[-1])

    assert payload["service"] == "test-service"
    assert payload["event"] == "unit_test_event"
    assert payload["correlation_id"] == "corr-1"
    assert payload["request_id"] == "req-1"
    assert payload["job_id"] == "job-1"
    assert payload["document_id"] == "doc-1"
    assert payload["password"] == "[REDACTED]"
    assert payload["api_token"] == "[REDACTED]"


def test_cleanup_removes_only_expired_rotated_logs(
    tmp_path: Path,
) -> None:
    """Проверяет age cleanup без удаления active или свежего rotated log."""
    service_name = "cleanup-service"

    service_dir = tmp_path / service_name
    service_dir.mkdir()

    active_log = service_dir / f"{service_name}.log"
    expired_rotated = service_dir / f"{service_name}.log.7"
    fresh_rotated = service_dir / f"{service_name}.log.1"

    active_log.write_text(
        "active",
        encoding="utf-8",
    )
    expired_rotated.write_text(
        "expired",
        encoding="utf-8",
    )
    fresh_rotated.write_text(
        "fresh",
        encoding="utf-8",
    )

    now = 2_000_000_000.0

    expired_mtime = now - 15 * 24 * 60 * 60
    fresh_mtime = now - 2 * 24 * 60 * 60

    os.utime(
        active_log,
        (
            expired_mtime,
            expired_mtime,
        ),
    )
    os.utime(
        expired_rotated,
        (
            expired_mtime,
            expired_mtime,
        ),
    )
    os.utime(
        fresh_rotated,
        (
            fresh_mtime,
            fresh_mtime,
        ),
    )

    removed_count = cleanup_expired_log_files(
        log_root_dir=tmp_path,
        service_name=service_name,
        retention_days=14,
        now=now,
    )

    assert removed_count == 1
    assert active_log.exists()
    assert not expired_rotated.exists()
    assert fresh_rotated.exists()


def test_size_rotation_keeps_bounded_archive_count(
    tmp_path: Path,
) -> None:
    """Проверяет ограничение количества size-rotated log archives."""
    service_name = "rotation-service"

    configure_logging(
        service_name=service_name,
        log_root_dir=tmp_path,
        file_max_bytes=120,
        file_backup_count=2,
        retention_days=14,
    )

    logger = logging.getLogger("tests.rotation")

    for index in range(20):
        logger.info(
            "Rotation payload with enough bytes to force rollover",
            extra={
                "event": "rotation_test",
                "index": index,
            },
        )

    reset_logging()

    service_dir = tmp_path / service_name

    rotated_logs = list(service_dir.glob(f"{service_name}.log.*"))

    assert len(rotated_logs) <= 2
    assert (service_dir / f"{service_name}.log").exists()
