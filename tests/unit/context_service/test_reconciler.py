# tests/unit/context_service/test_reconciler.py

"""Unit tests DB-driven Context indexing reconciliation semantics."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from context_service.application.use_cases.index_jobs import (
    ReconcileContextIndexJobsUseCase,
)
from context_service.domain.models import (
    ContextIndexJob,
    ContextIndexJobState,
    ContextSourceKind,
    NormalizedContextChunk,
)


class FrozenClock:
    """Возвращает deterministic UTC timestamp."""

    def __init__(self, now: datetime) -> None:
        """Сохраняет timestamp."""
        self._now = now

    def now(self) -> datetime:
        """Возвращает timestamp."""
        return self._now


class FakeJobs:
    """In-memory job repository одной reconciliation iteration."""

    def __init__(self, jobs: list[ContextIndexJob]) -> None:
        """Индексирует fixtures по id."""
        self.jobs = {job.id: job for job in jobs}
        self.candidates = list(jobs)

    async def list_recoverable(self, **_: object) -> list[ContextIndexJob]:
        """Возвращает заданные candidates."""
        return list(self.candidates)

    async def get_for_update(self, job_id: object) -> ContextIndexJob | None:
        """Возвращает job для state transition."""
        return self.jobs.get(job_id)

    async def save(self, job: ContextIndexJob) -> None:
        """Сохраняет immutable state."""
        self.jobs[job.id] = job


class FakeUow:
    """Минимальный UoW reconciliation use-case."""

    def __init__(self, jobs: FakeJobs) -> None:
        """Сохраняет repository."""
        self.jobs = jobs

    async def __aenter__(self) -> "FakeUow":
        """Возвращает себя."""
        return self

    async def __aexit__(self, *args: object) -> None:
        """Ничего не закрывает."""
        del args

    async def commit(self) -> None:
        """Fake commit."""


class FakeUowFactory:
    """Создаёт UoW поверх shared jobs repository."""

    def __init__(self, jobs: FakeJobs) -> None:
        """Сохраняет repository."""
        self._jobs = jobs

    def __call__(self) -> FakeUow:
        """Создаёт fake transaction scope."""
        return FakeUow(self._jobs)


class FakePublisher:
    """Запоминает published job ids."""

    def __init__(self) -> None:
        """Инициализирует publish log."""
        self.published: list[object] = []

    async def publish(self, *, job_id: object, **_: object) -> None:
        """Фиксирует publish."""
        self.published.append(job_id)


class FakeRetryFailure:
    """Переводит stale RUNNING в immediate RETRY_WAIT."""

    def __init__(self, jobs: FakeJobs, now: datetime) -> None:
        """Сохраняет shared repository и clock."""
        self._jobs = jobs
        self._now = now

    async def execute(self, *, job_id: object, **_: object) -> ContextIndexJob:
        """Сохраняет retry_wait с dispatched_at=None."""
        job = self._jobs.jobs[job_id]
        updated = job.schedule_retry(
            changed_at=self._now,
            next_attempt_at=self._now,
            error_message="stale_worker_lease_recovered",
        )
        self._jobs.jobs[job_id] = updated
        return updated


def build_job(
    *,
    now: datetime,
    state: ContextIndexJobState,
    dispatched_at: datetime | None,
    lease_expires_at: datetime | None = None,
) -> ContextIndexJob:
    """Создаёт deterministic job fixture."""
    return ContextIndexJob(
        id=uuid4(),
        context_id=uuid4(),
        source_id=uuid4(),
        user_id=uuid4(),
        kind=ContextSourceKind.TECHNICAL_ASSIGNMENT,
        fingerprint="a" * 64,
        correlation_id="corr-reconcile",
        chunks=(NormalizedContextChunk(chunk_id="c1", text="text"),),
        state=state,
        attempt=1 if state is ContextIndexJobState.RUNNING else 0,
        max_attempts=3,
        deadline_at=now + timedelta(minutes=12),
        next_attempt_at=None,
        dispatched_at=dispatched_at,
        lease_owner=("dead-worker" if state is ContextIndexJobState.RUNNING else None),
        lease_expires_at=lease_expires_at,
        last_error=None,
        created_at=now,
        updated_at=now,
    )


def test_reconciler_never_republishes_already_dispatched_queued_job() -> None:
    """Не создаёт duplicate message только из-за возраста dispatched_at."""
    now = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)
    job = build_job(
        now=now,
        state=ContextIndexJobState.QUEUED,
        dispatched_at=now - timedelta(minutes=5),
    )
    jobs = FakeJobs([job])
    publisher = FakePublisher()
    use_case = ReconcileContextIndexJobsUseCase(
        uow_factory=FakeUowFactory(jobs),
        publisher=publisher,
        clock=FrozenClock(now),
        retry_failure=FakeRetryFailure(jobs, now),
        batch_size=50,
    )

    result = asyncio.run(use_case.execute())

    assert result.dispatched == 0
    assert publisher.published == []


def test_reconciler_recovers_stale_running_job_and_publishes_once() -> None:
    """После crash/restart stale lease создаёт один controlled retry."""
    now = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)
    job = build_job(
        now=now,
        state=ContextIndexJobState.RUNNING,
        dispatched_at=now - timedelta(minutes=1),
        lease_expires_at=now - timedelta(seconds=1),
    )
    jobs = FakeJobs([job])
    publisher = FakePublisher()
    use_case = ReconcileContextIndexJobsUseCase(
        uow_factory=FakeUowFactory(jobs),
        publisher=publisher,
        clock=FrozenClock(now),
        retry_failure=FakeRetryFailure(jobs, now),
        batch_size=50,
    )

    result = asyncio.run(use_case.execute())

    assert result.dispatched == 1
    assert publisher.published == [job.id]
    assert jobs.jobs[job.id].dispatched_at == now
