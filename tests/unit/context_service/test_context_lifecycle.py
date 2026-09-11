# tests/unit/context_service/test_context_lifecycle.py

"""Unit tests temporary Project Context domain lifecycle."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from context_service.domain.exceptions import ProjectContextConflictError
from context_service.domain.models import (
    ProjectContext,
    ProjectContextState,
)


def test_active_context_touch_extends_expiration() -> None:
    """Проверяет sliding 24-hour temporary context TTL."""
    created_at = datetime(
        2026,
        9,
        11,
        9,
        0,
        tzinfo=UTC,
    )
    changed_at = created_at + timedelta(hours=2)

    context = ProjectContext(
        id=uuid4(),
        user_id=uuid4(),
        state=ProjectContextState.ACTIVE,
        cleanup_error=None,
        created_at=created_at,
        updated_at=created_at,
        expires_at=created_at + timedelta(hours=24),
    )

    updated = context.touch(
        changed_at=changed_at,
        ttl=timedelta(hours=24),
    )

    assert updated.state is ProjectContextState.ACTIVE
    assert updated.updated_at == changed_at
    assert updated.expires_at == changed_at + timedelta(hours=24)


def test_cleanup_pending_context_cannot_be_touched() -> None:
    """Не позволяет resurrect context после начала cleanup."""
    now = datetime(
        2026,
        9,
        11,
        9,
        0,
        tzinfo=UTC,
    )

    context = ProjectContext(
        id=uuid4(),
        user_id=uuid4(),
        state=ProjectContextState.CLEANUP_PENDING,
        cleanup_error=None,
        created_at=now,
        updated_at=now,
        expires_at=now,
    )

    with pytest.raises(ProjectContextConflictError):
        context.touch(
            changed_at=now,
            ttl=timedelta(hours=24),
        )


def test_cleanup_failure_remains_retryable() -> None:
    """Проверяет cleanup_pending вместо ложного cleaned при infrastructure failure."""
    now = datetime(
        2026,
        9,
        11,
        9,
        0,
        tzinfo=UTC,
    )

    context = ProjectContext(
        id=uuid4(),
        user_id=uuid4(),
        state=ProjectContextState.ACTIVE,
        cleanup_error=None,
        created_at=now,
        updated_at=now,
        expires_at=now,
    )

    pending = context.request_cleanup(
        changed_at=now,
    )
    failed = pending.mark_cleanup_failed(
        changed_at=now,
        error_message="qdrant_temporarily_unavailable",
    )

    assert failed.state is ProjectContextState.CLEANUP_PENDING
    assert failed.cleanup_error == "qdrant_temporarily_unavailable"

    cleaned = failed.mark_cleaned(
        changed_at=now,
    )

    assert cleaned.state is ProjectContextState.CLEANED
    assert cleaned.cleanup_error is None
