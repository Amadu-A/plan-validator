# tests/unit/context_service/test_runtime_status.py

"""Unit tests operational status use-cases Context Service."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from context_service.application.use_cases.runtime_status import (
    CheckContextReadinessUseCase,
    GetContextIndexJobUseCase,
)
from context_service.domain.exceptions import ContextIndexJobNotFoundError
from context_service.domain.models import (
    ContextIndexJob,
    ContextIndexJobState,
    ContextSourceKind,
    NormalizedContextChunk,
)


class FakeHealthProbe:
    """Управляемый readiness probe для unit tests."""

    def __init__(self, ready: bool) -> None:
        """Сохраняет заданное состояние readiness."""
        self._ready = ready
        self.calls = 0

    async def ready(self) -> bool:
        """Возвращает test readiness и фиксирует вызов."""
        self.calls += 1
        return self._ready


class FakeJobRepository:
    """Минимальный repository double для job status use-case."""

    def __init__(
        self,
        job: ContextIndexJob | None,
    ) -> None:
        """Сохраняет единственный test job."""
        self._job = job
        self.requested_job_id: UUID | None = None

    async def get(
        self,
        job_id: UUID,
    ) -> ContextIndexJob | None:
        """Возвращает configured job."""
        self.requested_job_id = job_id

        if self._job is None:
            return None

        if self._job.id != job_id:
            return None

        return self._job


class FakeUnitOfWork:
    """Минимальный async UoW только для чтения job."""

    def __init__(
        self,
        jobs: FakeJobRepository,
    ) -> None:
        """Сохраняет repository double."""
        self.jobs = jobs

    async def __aenter__(self) -> "FakeUnitOfWork":
        """Открывает fake transaction scope."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> None:
        """Fake UoW не владеет внешними resources."""
        del exc_type, exc, traceback


class FakeUnitOfWorkFactory:
    """Создаёт FakeUnitOfWork поверх одного repository."""

    def __init__(
        self,
        jobs: FakeJobRepository,
    ) -> None:
        """Сохраняет repository."""
        self._jobs = jobs

    def __call__(self) -> FakeUnitOfWork:
        """Создаёт новый fake transaction scope."""
        return FakeUnitOfWork(self._jobs)


def build_job(
    *,
    user_id: UUID | None = None,
    context_id: UUID | None = None,
) -> ContextIndexJob:
    """Создаёт валидный durable indexing job для unit tests."""
    now = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)

    return ContextIndexJob(
        id=uuid4(),
        context_id=context_id or uuid4(),
        source_id=uuid4(),
        user_id=user_id or uuid4(),
        kind=ContextSourceKind.TECHNICAL_ASSIGNMENT,
        fingerprint="a" * 64,
        correlation_id="runtime-status-test",
        chunks=(
            NormalizedContextChunk(
                chunk_id="chunk-1",
                text="Проверочный фрагмент технического задания.",
                page_number=1,
                fragment_index=0,
            ),
        ),
        state=ContextIndexJobState.QUEUED,
        attempt=0,
        max_attempts=3,
        deadline_at=now + timedelta(minutes=12),
        next_attempt_at=None,
        dispatched_at=now,
        lease_owner=None,
        lease_expires_at=None,
        last_error=None,
        created_at=now,
        updated_at=now,
    )


def test_readiness_requires_all_dependencies() -> None:
    """Проверяет aggregate readiness трёх mandatory dependencies."""
    database = FakeHealthProbe(True)
    vector_store = FakeHealthProbe(True)
    broker = FakeHealthProbe(True)

    use_case = CheckContextReadinessUseCase(
        database=database,
        vector_store=vector_store,
        broker=broker,
    )

    result = asyncio.run(use_case.execute())

    assert result is True
    assert database.calls == 1
    assert vector_store.calls == 1
    assert broker.calls == 1


def test_readiness_is_false_when_one_dependency_is_unavailable() -> None:
    """Проверяет not-ready без short-circuit остальных probes."""
    database = FakeHealthProbe(True)
    vector_store = FakeHealthProbe(False)
    broker = FakeHealthProbe(True)

    use_case = CheckContextReadinessUseCase(
        database=database,
        vector_store=vector_store,
        broker=broker,
    )

    result = asyncio.run(use_case.execute())

    assert result is False
    assert database.calls == 1
    assert vector_store.calls == 1
    assert broker.calls == 1


def test_get_job_returns_job_inside_owner_and_context_scope() -> None:
    """Возвращает job только при совпадении user/context."""
    user_id = uuid4()
    context_id = uuid4()

    job = build_job(
        user_id=user_id,
        context_id=context_id,
    )

    repository = FakeJobRepository(job)

    use_case = GetContextIndexJobUseCase(FakeUnitOfWorkFactory(repository))

    result = asyncio.run(
        use_case.execute(
            user_id=user_id,
            context_id=context_id,
            job_id=job.id,
        )
    )

    assert result == job
    assert repository.requested_job_id == job.id


def test_get_job_hides_foreign_user_job() -> None:
    """Не раскрывает существование job другому пользователю."""
    job = build_job()
    repository = FakeJobRepository(job)

    use_case = GetContextIndexJobUseCase(FakeUnitOfWorkFactory(repository))

    with pytest.raises(
        ContextIndexJobNotFoundError,
        match="Context indexing job was not found",
    ):
        asyncio.run(
            use_case.execute(
                user_id=uuid4(),
                context_id=job.context_id,
                job_id=job.id,
            )
        )


def test_get_job_hides_job_from_another_context() -> None:
    """Не разрешает использовать job UUID между contexts одного пользователя."""
    user_id = uuid4()

    job = build_job(user_id=user_id)

    repository = FakeJobRepository(job)

    use_case = GetContextIndexJobUseCase(FakeUnitOfWorkFactory(repository))

    with pytest.raises(
        ContextIndexJobNotFoundError,
        match="Context indexing job was not found",
    ):
        asyncio.run(
            use_case.execute(
                user_id=user_id,
                context_id=uuid4(),
                job_id=job.id,
            )
        )


def test_get_job_returns_not_found_for_missing_job() -> None:
    """Возвращает безопасный not-found для отсутствующего job."""
    repository = FakeJobRepository(None)

    use_case = GetContextIndexJobUseCase(FakeUnitOfWorkFactory(repository))

    with pytest.raises(
        ContextIndexJobNotFoundError,
        match="Context indexing job was not found",
    ):
        asyncio.run(
            use_case.execute(
                user_id=uuid4(),
                context_id=uuid4(),
                job_id=uuid4(),
            )
        )
