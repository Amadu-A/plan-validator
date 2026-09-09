# packages/common/src/plan_validator_common/observability/correlation.py

"""ContextVar-based correlation context для HTTP, jobs и фоновых операций."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from uuid import uuid4

_CORRELATION_ID: ContextVar[str | None] = ContextVar(
    "correlation_id",
    default=None,
)
_REQUEST_ID: ContextVar[str | None] = ContextVar(
    "request_id",
    default=None,
)
_JOB_ID: ContextVar[str | None] = ContextVar(
    "job_id",
    default=None,
)


@dataclass(frozen=True, slots=True)
class LogContext:
    """Представляет текущие identifiers, добавляемые в structured logs."""

    correlation_id: str | None
    request_id: str | None
    job_id: str | None


@dataclass(frozen=True, slots=True)
class LogContextTokens:
    """Хранит ContextVar tokens для безопасного восстановления прошлого context."""

    correlation_id: Token[str | None] | None = None
    request_id: Token[str | None] | None = None
    job_id: Token[str | None] | None = None


def new_correlation_id() -> str:
    """Создаёт новый correlation identifier без внешнего состояния."""
    return uuid4().hex


def get_log_context() -> LogContext:
    """Возвращает immutable snapshot текущего logging context."""
    return LogContext(
        correlation_id=_CORRELATION_ID.get(),
        request_id=_REQUEST_ID.get(),
        job_id=_JOB_ID.get(),
    )


def bind_log_context(
    *,
    correlation_id: str | None = None,
    request_id: str | None = None,
    job_id: str | None = None,
) -> LogContextTokens:
    """Устанавливает переданные identifiers и возвращает tokens для rollback."""
    return LogContextTokens(
        correlation_id=(
            _CORRELATION_ID.set(correlation_id) if correlation_id is not None else None
        ),
        request_id=(_REQUEST_ID.set(request_id) if request_id is not None else None),
        job_id=(_JOB_ID.set(job_id) if job_id is not None else None),
    )


def reset_log_context(tokens: LogContextTokens) -> None:
    """Восстанавливает только те ContextVar, которые менялись при bind."""
    if tokens.job_id is not None:
        _JOB_ID.reset(tokens.job_id)

    if tokens.request_id is not None:
        _REQUEST_ID.reset(tokens.request_id)

    if tokens.correlation_id is not None:
        _CORRELATION_ID.reset(tokens.correlation_id)


def clear_log_context() -> None:
    """Очищает identifiers текущего execution context."""
    _CORRELATION_ID.set(None)
    _REQUEST_ID.set(None)
    _JOB_ID.set(None)


@contextmanager
def scoped_log_context(
    *,
    correlation_id: str | None = None,
    request_id: str | None = None,
    job_id: str | None = None,
) -> Iterator[LogContext]:
    """Временно устанавливает identifiers и гарантированно восстанавливает context."""
    tokens = bind_log_context(
        correlation_id=correlation_id,
        request_id=request_id,
        job_id=job_id,
    )

    try:
        yield get_log_context()
    finally:
        reset_log_context(tokens)
