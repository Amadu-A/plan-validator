# packages/common/src/plan_validator_common/observability/timing.py

"""Reusable timing decorator для значимых sync/async operations."""

import inspect
import logging
import time
from collections.abc import Callable
from functools import wraps
from typing import cast


def log_execution_time[**P, R](
    operation: str,
    *,
    logger_name: str | None = None,
) -> Callable[
    [Callable[P, R]],
    Callable[P, R],
]:
    """Логирует duration/status operation и сохраняет исходное исключение."""
    if not operation.strip():
        raise ValueError("operation must be a non-empty stable name")

    def decorator(
        func: Callable[P, R],
    ) -> Callable[P, R]:
        """Создаёт sync или async wrapper в зависимости от decorated function."""
        logger = logging.getLogger(logger_name or func.__module__)

        if inspect.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(
                *args: P.args,
                **kwargs: P.kwargs,
            ) -> R:
                """Измеряет async operation через monotonic performance counter."""
                started_at = time.perf_counter()

                try:
                    result = await func(
                        *args,
                        **kwargs,
                    )
                except Exception as exc:
                    _log_timing_error(
                        logger=logger,
                        operation=operation,
                        started_at=started_at,
                        error=exc,
                    )
                    raise

                _log_timing_success(
                    logger=logger,
                    operation=operation,
                    started_at=started_at,
                )

                return result

            return cast(
                Callable[P, R],
                async_wrapper,
            )

        @wraps(func)
        def sync_wrapper(
            *args: P.args,
            **kwargs: P.kwargs,
        ) -> R:
            """Измеряет sync operation через monotonic performance counter."""
            started_at = time.perf_counter()

            try:
                result = func(
                    *args,
                    **kwargs,
                )
            except Exception as exc:
                _log_timing_error(
                    logger=logger,
                    operation=operation,
                    started_at=started_at,
                    error=exc,
                )
                raise

            _log_timing_success(
                logger=logger,
                operation=operation,
                started_at=started_at,
            )

            return result

        return sync_wrapper

    return decorator


def _duration_ms(started_at: float) -> float:
    """Возвращает duration в milliseconds с устойчивой точностью для logs."""
    return round(
        (time.perf_counter() - started_at) * 1000,
        3,
    )


def _log_timing_success(
    *,
    logger: logging.Logger,
    operation: str,
    started_at: float,
) -> None:
    """Пишет успешное operation_timing событие без лишнего detail logging."""
    logger.info(
        "Operation completed",
        extra={
            "event": "operation_timing",
            "operation": operation,
            "duration_ms": _duration_ms(started_at),
            "status": "success",
        },
    )


def _log_timing_error(
    *,
    logger: logging.Logger,
    operation: str,
    started_at: float,
    error: Exception,
) -> None:
    """Пишет timing ошибки без traceback и оставляет traceback error boundary."""
    logger.error(
        "Operation failed",
        extra={
            "event": "operation_timing",
            "operation": operation,
            "duration_ms": _duration_ms(started_at),
            "status": "error",
            "error_type": type(error).__name__,
        },
    )
