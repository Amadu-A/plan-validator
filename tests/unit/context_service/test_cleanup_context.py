# tests/unit/context_service/test_cleanup_context.py

"""Unit tests logical-first Context cleanup coordination."""

import asyncio
from dataclasses import replace
from datetime import (
    UTC,
    datetime,
    timedelta,
)
from uuid import (
    UUID,
    uuid4,
)

from context_service.application.use_cases.cleanup_context import (
    FinalizeProjectContextCleanupUseCase,
    ListProjectContextCleanupCandidatesUseCase,
)
from context_service.domain.models import (
    TERMINAL_JOB_STATES,
    ContextIndexJob,
    ContextIndexJobState,
    ContextSourceKind,
    ProjectContext,
    ProjectContextState,
)

_CLEANUP_CANCEL_REASON = "project_context_cleanup_requested"


class FrozenClock:
    """Возвращает deterministic UTC timestamp."""

    def __init__(
        self,
        now: datetime,
    ) -> None:
        """Сохраняет timestamp."""
        self._now = now

    def now(
        self,
    ) -> datetime:
        """Возвращает timestamp."""
        return self._now


class SharedState:
    """Общее mutable состояние fake repositories между UoW scopes."""

    def __init__(
        self,
        context: ProjectContext,
        *,
        jobs: tuple[ContextIndexJob, ...] = (),
    ) -> None:
        """Сохраняет context, jobs и cleanup flags."""
        self.context = context
        self.jobs = list(jobs)
        self.jobs_deleted = False
        self.sources_deleted = False


class FakeContexts:
    """Project Context repository поверх SharedState."""

    def __init__(
        self,
        state: SharedState,
    ) -> None:
        """Сохраняет state."""
        self._state = state

    async def get_for_user_for_update(
        self,
        **_: object,
    ) -> ProjectContext:
        """Возвращает current context."""
        return self._state.context

    async def get_for_user(
        self,
        **_: object,
    ) -> ProjectContext:
        """Возвращает current context."""
        return self._state.context

    async def list_cleanup_candidates(
        self,
        *,
        now: datetime,
        limit: int,
    ) -> list[ProjectContext]:
        """Имитирует expiration/cleanup_pending query."""
        assert limit > 0

        context = self._state.context

        if context.state is ProjectContextState.CLEANUP_PENDING or (
            context.state is ProjectContextState.ACTIVE and context.expires_at <= now
        ):
            return [context]

        return []

    async def save(
        self,
        context: ProjectContext,
    ) -> None:
        """Сохраняет updated immutable context."""
        self._state.context = context


class FakeJobs:
    """Job repository с waiting/running cleanup semantics."""

    def __init__(
        self,
        state: SharedState,
    ) -> None:
        """Сохраняет state."""
        self._state = state

    async def list_waiting_for_context_for_update(
        self,
        *,
        context_id: UUID,
    ) -> list[ContextIndexJob]:
        """Возвращает только QUEUED/RETRY_WAIT jobs."""
        assert context_id == self._state.context.id

        waiting_states = {
            ContextIndexJobState.QUEUED,
            ContextIndexJobState.RETRY_WAIT,
        }

        return [
            job
            for job in self._state.jobs
            if job.context_id == context_id and job.state in waiting_states
        ]

    async def has_open_for_context(
        self,
        *,
        context_id: UUID,
    ) -> bool:
        """Проверяет, остался ли non-terminal job."""
        assert context_id == self._state.context.id

        return any(
            job.context_id == context_id and job.state not in TERMINAL_JOB_STATES
            for job in self._state.jobs
        )

    async def delete_for_context(
        self,
        *,
        context_id: UUID,
    ) -> None:
        """Фиксирует purge durable job/chunk rows."""
        assert context_id == self._state.context.id

        self._state.jobs_deleted = True

    async def save(
        self,
        job: ContextIndexJob,
    ) -> None:
        """Заменяет immutable job в shared state."""
        for index, current in enumerate(self._state.jobs):
            if current.id == job.id:
                self._state.jobs[index] = job
                return

        raise AssertionError("Fake job was not found")


class FakeSources:
    """Source repository cleanup double."""

    def __init__(
        self,
        state: SharedState,
    ) -> None:
        """Сохраняет state."""
        self._state = state

    async def delete_for_context(
        self,
        *,
        context_id: UUID,
    ) -> None:
        """Фиксирует purge temporary source metadata."""
        assert context_id == self._state.context.id

        self._state.sources_deleted = True


class FakeUow:
    """Минимальный cleanup UoW."""

    def __init__(
        self,
        state: SharedState,
    ) -> None:
        """Создаёт repositories."""
        self.contexts = FakeContexts(state)

        self.jobs = FakeJobs(state)

        self.sources = FakeSources(state)

    async def __aenter__(
        self,
    ) -> "FakeUow":
        """Возвращает себя."""
        return self

    async def __aexit__(
        self,
        *args: object,
    ) -> None:
        """Ничего не закрывает."""
        del args

    async def commit(
        self,
    ) -> None:
        """Fake commit."""


class FakeUowFactory:
    """Создаёт UoW поверх shared state."""

    def __init__(
        self,
        state: SharedState,
    ) -> None:
        """Сохраняет state."""
        self._state = state

    def __call__(
        self,
    ) -> FakeUow:
        """Создаёт fake transaction scope."""
        return FakeUow(self._state)


class FakeVectorStore:
    """Фиксирует physical Context collection deletion."""

    def __init__(
        self,
    ) -> None:
        """Инициализирует counter."""
        self.deletes = 0

    async def delete_context(
        self,
        **_: object,
    ) -> None:
        """Фиксирует delete."""
        self.deletes += 1


def build_context(
    now: datetime,
) -> ProjectContext:
    """Создаёт active temporary context."""
    return ProjectContext(
        id=uuid4(),
        user_id=uuid4(),
        state=(ProjectContextState.ACTIVE),
        cleanup_error=None,
        created_at=now,
        updated_at=now,
        expires_at=(now + timedelta(hours=24)),
    )


def build_job(
    context: ProjectContext,
    now: datetime,
    *,
    state: ContextIndexJobState,
) -> ContextIndexJob:
    """Создаёт persistent job нужного lifecycle state."""
    running = state is ContextIndexJobState.RUNNING
    retry_wait = state is ContextIndexJobState.RETRY_WAIT

    return ContextIndexJob(
        id=uuid4(),
        context_id=context.id,
        source_id=uuid4(),
        user_id=context.user_id,
        kind=ContextSourceKind.TECHNICAL_ASSIGNMENT,
        fingerprint="f" * 64,
        correlation_id=str(uuid4()),
        chunks=(),
        state=state,
        attempt=1 if running or retry_wait else 0,
        max_attempts=3,
        deadline_at=now + timedelta(minutes=12),
        next_attempt_at=(now + timedelta(seconds=5)) if retry_wait else None,
        dispatched_at=now if state is not ContextIndexJobState.RETRY_WAIT else None,
        lease_owner="worker-1" if running else None,
        lease_expires_at=(now + timedelta(seconds=60)) if running else None,
        last_error="temporary_failure" if retry_wait else None,
        created_at=now,
        updated_at=now,
    )


def test_cleanup_cancels_waiting_jobs_and_continues_physical_cleanup() -> None:
    """QUEUED/RETRY_WAIT не заставляют cleanup ждать свободного worker."""
    now = datetime(
        2026,
        9,
        16,
        12,
        0,
        tzinfo=UTC,
    )

    context = build_context(now)

    queued = build_job(
        context,
        now,
        state=ContextIndexJobState.QUEUED,
    )
    retry_wait = build_job(
        context,
        now,
        state=ContextIndexJobState.RETRY_WAIT,
    )

    state = SharedState(
        context,
        jobs=(queued, retry_wait),
    )

    vector_store = FakeVectorStore()

    use_case = FinalizeProjectContextCleanupUseCase(
        uow_factory=FakeUowFactory(state),
        vector_store=vector_store,
        clock=FrozenClock(now),
    )

    result = asyncio.run(
        use_case.execute(
            user_id=state.context.user_id,
            context_id=state.context.id,
        )
    )

    assert result.state is ProjectContextState.CLEANED
    assert state.context.state is ProjectContextState.CLEANED

    assert all(job.state is ContextIndexJobState.CANCELED for job in state.jobs)
    assert all(job.last_error == _CLEANUP_CANCEL_REASON for job in state.jobs)

    assert vector_store.deletes == 1
    assert state.jobs_deleted is True
    assert state.sources_deleted is True


def test_cleanup_waits_for_running_job_but_cancels_waiting_job() -> None:
    """RUNNING сохраняет lease, а соседний QUEUED proactively отменяется."""
    now = datetime(
        2026,
        9,
        16,
        12,
        0,
        tzinfo=UTC,
    )

    context = build_context(now)

    running = build_job(
        context,
        now,
        state=ContextIndexJobState.RUNNING,
    )
    queued = build_job(
        context,
        now,
        state=ContextIndexJobState.QUEUED,
    )

    state = SharedState(
        context,
        jobs=(running, queued),
    )

    vector_store = FakeVectorStore()

    use_case = FinalizeProjectContextCleanupUseCase(
        uow_factory=FakeUowFactory(state),
        vector_store=vector_store,
        clock=FrozenClock(now),
    )

    result = asyncio.run(
        use_case.execute(
            user_id=state.context.user_id,
            context_id=state.context.id,
        )
    )

    assert result.state is ProjectContextState.CLEANUP_PENDING
    assert state.context.state is ProjectContextState.CLEANUP_PENDING

    running_after = next(job for job in state.jobs if job.id == running.id)
    queued_after = next(job for job in state.jobs if job.id == queued.id)

    assert running_after.state is ContextIndexJobState.RUNNING
    assert running_after.lease_owner == "worker-1"
    assert running_after.lease_expires_at == now + timedelta(seconds=60)

    assert queued_after.state is ContextIndexJobState.CANCELED
    assert queued_after.last_error == _CLEANUP_CANCEL_REASON

    assert vector_store.deletes == 0
    assert state.jobs_deleted is False
    assert state.sources_deleted is False


def test_cleanup_deletes_qdrant_and_temporary_db_payload_without_jobs() -> None:
    """Context без open jobs очищается немедленно."""
    now = datetime(
        2026,
        9,
        16,
        12,
        0,
        tzinfo=UTC,
    )

    state = SharedState(build_context(now))

    vector_store = FakeVectorStore()

    use_case = FinalizeProjectContextCleanupUseCase(
        uow_factory=FakeUowFactory(state),
        vector_store=vector_store,
        clock=FrozenClock(now),
    )

    result = asyncio.run(
        use_case.execute(
            user_id=state.context.user_id,
            context_id=state.context.id,
        )
    )

    assert result.state is ProjectContextState.CLEANED

    assert vector_store.deletes == 1
    assert state.jobs_deleted is True
    assert state.sources_deleted is True


def test_expired_context_is_selected_for_automatic_cleanup() -> None:
    """Maintenance обнаруживает active context после TTL."""
    now = datetime(
        2026,
        9,
        16,
        12,
        0,
        tzinfo=UTC,
    )

    expired = replace(
        build_context(now),
        expires_at=(now - timedelta(seconds=1)),
    )

    state = SharedState(expired)

    use_case = ListProjectContextCleanupCandidatesUseCase(
        uow_factory=(FakeUowFactory(state)),
        clock=FrozenClock(now),
        batch_size=50,
    )

    result = asyncio.run(use_case.execute())

    assert result == (expired,)
