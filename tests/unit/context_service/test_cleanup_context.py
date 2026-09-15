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
    ProjectContext,
    ProjectContextState,
)


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
        jobs_open: bool,
    ) -> None:
        """Сохраняет context и cleanup flags."""
        self.context = context
        self.jobs_open = jobs_open
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
    """Job repository с configurable non-terminal state."""

    def __init__(
        self,
        state: SharedState,
    ) -> None:
        """Сохраняет state."""
        self._state = state

    async def has_open_for_context(
        self,
        *,
        context_id: UUID,
    ) -> bool:
        """Возвращает open-jobs flag."""
        assert context_id == self._state.context.id

        return self._state.jobs_open

    async def delete_for_context(
        self,
        *,
        context_id: UUID,
    ) -> None:
        """Фиксирует purge durable job/chunk rows."""
        assert context_id == self._state.context.id

        self._state.jobs_deleted = True


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


def test_cleanup_hides_context_but_waits_for_open_job_before_qdrant() -> None:
    """Physical cleanup не гонится с RUNNING worker."""
    now = datetime(
        2026,
        9,
        11,
        12,
        0,
        tzinfo=UTC,
    )

    state = SharedState(
        build_context(now),
        jobs_open=True,
    )

    vector_store = FakeVectorStore()

    use_case = FinalizeProjectContextCleanupUseCase(
        uow_factory=(FakeUowFactory(state)),
        vector_store=vector_store,
        clock=FrozenClock(now),
    )

    result = asyncio.run(
        use_case.execute(
            user_id=(state.context.user_id),
            context_id=(state.context.id),
        )
    )

    assert result.state is ProjectContextState.CLEANUP_PENDING

    assert state.context.state is ProjectContextState.CLEANUP_PENDING

    assert vector_store.deletes == 0
    assert state.jobs_deleted is False
    assert state.sources_deleted is False


def test_cleanup_deletes_qdrant_and_temporary_db_payload() -> None:
    """После terminal jobs удаляет vectors, chunks и source metadata."""
    now = datetime(
        2026,
        9,
        11,
        12,
        0,
        tzinfo=UTC,
    )

    state = SharedState(
        build_context(now),
        jobs_open=False,
    )

    vector_store = FakeVectorStore()

    use_case = FinalizeProjectContextCleanupUseCase(
        uow_factory=(FakeUowFactory(state)),
        vector_store=vector_store,
        clock=FrozenClock(now),
    )

    result = asyncio.run(
        use_case.execute(
            user_id=(state.context.user_id),
            context_id=(state.context.id),
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
        11,
        12,
        0,
        tzinfo=UTC,
    )

    expired = replace(
        build_context(now),
        expires_at=(now - timedelta(seconds=1)),
    )

    state = SharedState(
        expired,
        jobs_open=False,
    )

    use_case = ListProjectContextCleanupCandidatesUseCase(
        uow_factory=(FakeUowFactory(state)),
        clock=FrozenClock(now),
        batch_size=50,
    )

    result = asyncio.run(use_case.execute())

    assert result == (expired,)
