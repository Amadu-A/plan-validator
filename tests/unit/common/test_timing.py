# tests/unit/common/test_timing.py

"""Unit tests reusable operation timing decorator."""

import asyncio
import logging

import pytest
from plan_validator_common.observability.timing import (
    log_execution_time,
)


def test_sync_timing_logs_success(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Проверяет sync operation_timing success event."""
    caplog.set_level(logging.INFO)

    @log_execution_time("tests.sync_operation")
    def calculate(value: int) -> int:
        """Возвращает тестовое значение для проверки decorator."""
        return value + 1

    assert calculate(4) == 5

    timing_record = next(
        record
        for record in caplog.records
        if getattr(
            record,
            "event",
            None,
        )
        == "operation_timing"
    )

    assert timing_record.operation == "tests.sync_operation"
    assert timing_record.status == "success"
    assert timing_record.duration_ms >= 0


def test_async_timing_logs_success(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Проверяет поддержку coroutine function без отдельного async plugin."""
    caplog.set_level(logging.INFO)

    @log_execution_time("tests.async_operation")
    async def calculate(value: int) -> int:
        """Возвращает тестовое значение после одного event-loop переключения."""
        await asyncio.sleep(0)
        return value + 2

    assert asyncio.run(calculate(3)) == 5

    timing_record = next(
        record
        for record in caplog.records
        if getattr(
            record,
            "operation",
            None,
        )
        == "tests.async_operation"
    )

    assert timing_record.status == "success"


def test_timing_reraises_error_without_attaching_traceback(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Проверяет error timing event и сохранение исходного exception."""
    caplog.set_level(logging.ERROR)

    @log_execution_time("tests.failed_operation")
    def fail() -> None:
        """Создаёт контролируемое исключение для проверки error path."""
        raise RuntimeError("expected failure")

    with pytest.raises(
        RuntimeError,
        match="expected failure",
    ):
        fail()

    timing_record = next(
        record
        for record in caplog.records
        if getattr(
            record,
            "operation",
            None,
        )
        == "tests.failed_operation"
    )

    assert timing_record.status == "error"
    assert timing_record.error_type == "RuntimeError"
    assert timing_record.exc_info is None
