# tests/unit/context_service/test_index_jobs.py

"""Unit tests persistent Context indexing job recovery semantics."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from context_service.domain.exceptions import ContextIndexJobConflictError
from context_service.domain.models import (
    ContextIndexJob,
    ContextIndexJobState,
    ContextSourceKind,
    NormalizedContextChunk,
)


def build_job(
    *,
    now: datetime,
    state: ContextIndexJobState = ContextIndexJobState.QUEUED,
    attempt: int = 0,
    lease_owner: str | None = None,
    lease_expires_at: datetime | None = None,
    next_attempt_at: datetime | None = None,
) -> ContextIndexJob:
    """Создаёт deterministic recoverable job для unit tests."""
    return ContextIndexJob(
        id=uuid4(),
        context_id=uuid4(),
        source_id=uuid4(),
        user_id=uuid4(),
        kind=ContextSourceKind.TECHNICAL_ASSIGNMENT,
        fingerprint="a" * 64,
        correlation_id="context-unit",
        chunks=(
            NormalizedContextChunk(
                chunk_id="p1-0",
                text="Требование технического задания.",
                page_number=1,
            ),
        ),
        state=state,
        attempt=attempt,
        max_attempts=3,
        deadline_at=now + timedelta(minutes=12),
        next_attempt_at=next_attempt_at,
        dispatched_at=None,
        lease_owner=lease_owner,
        lease_expires_at=lease_expires_at,
        last_error=None,
        created_at=now,
        updated_at=now,
    )


def test_job_claim_creates_process_owned_lease() -> None:
    """Проверяет attempt increment и bounded process lease."""
    now = datetime(
        2026,
        9,
        11,
        9,
        0,
        tzinfo=UTC,
    )
    job = build_job(now=now)

    claimed, did_claim = job.claim(
        worker_id="context-worker-1",
        changed_at=now,
        lease_seconds=60,
    )

    assert did_claim is True
    assert claimed.state is ContextIndexJobState.RUNNING
    assert claimed.attempt == 1
    assert claimed.lease_owner == "context-worker-1"
    assert claimed.lease_expires_at == now + timedelta(seconds=60)


def test_duplicate_delivery_does_not_steal_live_lease() -> None:
    """Проверяет idempotent duplicate Rabbit delivery."""
    now = datetime(
        2026,
        9,
        11,
        9,
        0,
        tzinfo=UTC,
    )

    running = build_job(
        now=now,
        state=ContextIndexJobState.RUNNING,
        attempt=1,
        lease_owner="context-worker-1",
        lease_expires_at=now + timedelta(seconds=45),
    )

    unchanged, did_claim = running.claim(
        worker_id="context-worker-2",
        changed_at=now,
        lease_seconds=60,
    )

    assert did_claim is False
    assert unchanged == running


def test_stale_running_job_can_be_reclaimed() -> None:
    """Проверяет automatic recovery после crash/restart worker."""
    now = datetime(
        2026,
        9,
        11,
        9,
        0,
        tzinfo=UTC,
    )

    stale = build_job(
        now=now,
        state=ContextIndexJobState.RUNNING,
        attempt=1,
        lease_owner="dead-worker",
        lease_expires_at=now - timedelta(seconds=1),
    )

    reclaimed, did_claim = stale.claim(
        worker_id="replacement-worker",
        changed_at=now,
        lease_seconds=60,
    )

    assert did_claim is True
    assert reclaimed.state is ContextIndexJobState.RUNNING
    assert reclaimed.attempt == 2
    assert reclaimed.lease_owner == "replacement-worker"


def test_job_cannot_run_past_absolute_deadline() -> None:
    """Проверяет hard deadline независимо от Rabbit redelivery."""
    now = datetime(
        2026,
        9,
        11,
        9,
        0,
        tzinfo=UTC,
    )
    original = build_job(now=now)

    expired = ContextIndexJob(
        id=original.id,
        context_id=original.context_id,
        source_id=original.source_id,
        user_id=original.user_id,
        kind=original.kind,
        fingerprint=original.fingerprint,
        correlation_id=original.correlation_id,
        chunks=original.chunks,
        state=original.state,
        attempt=original.attempt,
        max_attempts=original.max_attempts,
        deadline_at=now - timedelta(seconds=1),
        next_attempt_at=None,
        dispatched_at=None,
        lease_owner=None,
        lease_expires_at=None,
        last_error=None,
        created_at=original.created_at,
        updated_at=original.updated_at,
    )

    failed, did_claim = expired.claim(
        worker_id="context-worker",
        changed_at=now,
        lease_seconds=60,
    )

    assert did_claim is False
    assert failed.state is ContextIndexJobState.FAILED
    assert failed.last_error == "job_deadline_exceeded"


def test_heartbeat_requires_lease_owner() -> None:
    """Не позволяет другому worker продлевать чужой lease."""
    now = datetime(
        2026,
        9,
        11,
        9,
        0,
        tzinfo=UTC,
    )

    running = build_job(
        now=now,
        state=ContextIndexJobState.RUNNING,
        attempt=1,
        lease_owner="worker-a",
        lease_expires_at=now + timedelta(seconds=60),
    )

    with pytest.raises(ContextIndexJobConflictError):
        running.heartbeat(
            worker_id="worker-b",
            changed_at=now,
            lease_seconds=60,
        )
