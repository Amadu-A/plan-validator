# tests/unit/common/test_correlation.py

"""Unit tests correlation context на базе ContextVar."""

from uuid import UUID

from plan_validator_common.observability.correlation import (
    bind_log_context,
    clear_log_context,
    get_log_context,
    new_correlation_id,
    reset_log_context,
    scoped_log_context,
)


def test_bind_and_reset_restore_previous_context() -> None:
    """Проверяет восстановление предыдущих identifiers после nested bind."""
    clear_log_context()

    outer_tokens = bind_log_context(
        correlation_id="outer",
        request_id="request-1",
    )

    inner_tokens = bind_log_context(
        correlation_id="inner",
        job_id="job-1",
    )

    assert get_log_context().correlation_id == "inner"
    assert get_log_context().request_id == "request-1"
    assert get_log_context().job_id == "job-1"

    reset_log_context(inner_tokens)

    restored = get_log_context()

    assert restored.correlation_id == "outer"
    assert restored.request_id == "request-1"
    assert restored.job_id is None

    reset_log_context(outer_tokens)
    clear_log_context()


def test_scoped_context_is_restored_after_exit() -> None:
    """Проверяет гарантированный rollback context manager после выхода из scope."""
    clear_log_context()

    with scoped_log_context(
        correlation_id="corr",
        request_id="req",
    ) as context:
        assert context.correlation_id == "corr"
        assert get_log_context().request_id == "req"

    assert get_log_context().correlation_id is None
    assert get_log_context().request_id is None


def test_new_correlation_id_is_valid_unique_uuid_hex() -> None:
    """Проверяет UUID-compatible формат и уникальность generated identifiers."""
    first = new_correlation_id()
    second = new_correlation_id()

    assert first != second
    assert UUID(hex=first).hex == first
    assert UUID(hex=second).hex == second
