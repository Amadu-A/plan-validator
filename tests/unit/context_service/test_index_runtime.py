# tests/unit/context_service/test_index_runtime.py

"""Unit tests Context runtime indexing candidate/activation sequence."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from context_service.application.ports.embedding_gateway import EmbeddedContextTexts
from context_service.application.use_cases.index_runtime import IndexContextSourceUseCase
from context_service.domain.exceptions import ContextEmbeddingError
from context_service.domain.models import (
    ContextIndexJob,
    ContextIndexJobState,
    ContextSource,
    ContextSourceKind,
    ContextSourceState,
    NormalizedContextChunk,
    ProjectContext,
    ProjectContextState,
)


class FakeContexts:
    """Минимальный Project Context repository для runtime unit tests."""

    def __init__(self, context: ProjectContext) -> None:
        """Сохраняет context fixture."""
        self._context = context

    async def get_for_user(self, **_: object) -> ProjectContext:
        """Возвращает fixture context."""
        return self._context


class FakeSources:
    """Минимальный Context source repository для runtime unit tests."""

    def __init__(self, source: ContextSource) -> None:
        """Сохраняет source fixture."""
        self._source = source

    async def get_for_user(self, **_: object) -> ContextSource:
        """Возвращает fixture source."""
        return self._source


class FakeReadUow:
    """Async context manager только для runtime reads."""

    def __init__(self, context: ProjectContext, source: ContextSource) -> None:
        """Создаёт fake repositories."""
        self.contexts = FakeContexts(context)
        self.sources = FakeSources(source)

    async def __aenter__(self) -> "FakeReadUow":
        """Возвращает себя."""
        return self

    async def __aexit__(self, *args: object) -> None:
        """Ничего не закрывает."""
        del args


class FakeUowFactory:
    """Создаёт одинаковый fake UoW."""

    def __init__(self, context: ProjectContext, source: ContextSource) -> None:
        """Сохраняет fixtures."""
        self._context = context
        self._source = source

    def __call__(self) -> FakeReadUow:
        """Создаёт новый fake scope."""
        return FakeReadUow(self._context, self._source)


class FakeEmbeddingGateway:
    """Возвращает deterministic embedding batch."""

    def __init__(self, *, model: str, dimension: int) -> None:
        """Сохраняет embedding identity."""
        self.model = model
        self.dimension = dimension
        self.calls = 0

    async def embed_texts(self, **_: object) -> EmbeddedContextTexts:
        """Возвращает один vector на каждый test chunk."""
        self.calls += 1
        return EmbeddedContextTexts(
            model=self.model,
            dimension=self.dimension,
            vectors=((0.1,) * self.dimension,),
        )


class FakeVectorStore:
    """Запоминает candidate и stale cleanup operations."""

    def __init__(self) -> None:
        """Инициализирует counters."""
        self.upserts = 0
        self.obsolete_cleanups = 0
        self.deleted_versions = 0

    async def upsert_version(self, **_: object) -> None:
        """Фиксирует candidate upsert."""
        self.upserts += 1

    async def delete_obsolete_versions(self, **_: object) -> None:
        """Фиксирует stale cleanup."""
        self.obsolete_cleanups += 1

    async def delete_version(self, **_: object) -> None:
        """Фиксирует candidate rollback."""
        self.deleted_versions += 1


class FakeCompleteJob:
    """Имитирует атомарную DB activation Stage 10.1."""

    def __init__(self, job: ContextIndexJob, now: datetime) -> None:
        """Сохраняет job fixture."""
        self._job = job
        self._now = now
        self.calls = 0

    async def execute(self, **_: object) -> ContextIndexJob:
        """Возвращает terminal success."""
        self.calls += 1
        return self._job.succeed(changed_at=self._now)


def build_fixtures() -> tuple[datetime, ProjectContext, ContextSource, ContextIndexJob]:
    """Создаёт согласованные active Context/source/running job fixtures."""
    now = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)
    user_id = uuid4()
    context_id = uuid4()
    source_id = uuid4()
    context = ProjectContext(
        id=context_id,
        user_id=user_id,
        state=ProjectContextState.ACTIVE,
        cleanup_error=None,
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(hours=24),
    )
    source = ContextSource(
        id=source_id,
        context_id=context_id,
        user_id=user_id,
        kind=ContextSourceKind.TECHNICAL_ASSIGNMENT,
        original_name="technical-assignment.pdf",
        source_sha256="a" * 64,
        state=ContextSourceState.AWAITING_CHUNKS,
        active_fingerprint=None,
        chunk_count=0,
        created_at=now,
        updated_at=now,
    )
    job = ContextIndexJob(
        id=uuid4(),
        context_id=context_id,
        source_id=source_id,
        user_id=user_id,
        kind=source.kind,
        fingerprint="b" * 64,
        correlation_id="corr-runtime",
        chunks=(
            NormalizedContextChunk(
                chunk_id="p1-0",
                text="Требование заказчика по проекту.",
                page_number=1,
            ),
        ),
        state=ContextIndexJobState.RUNNING,
        attempt=1,
        max_attempts=3,
        deadline_at=now + timedelta(minutes=12),
        next_attempt_at=None,
        dispatched_at=now,
        lease_owner="worker-1",
        lease_expires_at=now + timedelta(seconds=60),
        last_error=None,
        created_at=now,
        updated_at=now,
    )
    return now, context, source, job


def test_runtime_indexes_candidate_then_activates_and_cleans_stale() -> None:
    """Проверяет candidate -> DB activation -> stale cleanup sequence."""
    now, context, source, job = build_fixtures()
    embedding = FakeEmbeddingGateway(
        model="Qwen/Qwen3-VL-Embedding-8B",
        dimension=4,
    )
    vector_store = FakeVectorStore()
    complete = FakeCompleteJob(job, now)
    use_case = IndexContextSourceUseCase(
        uow_factory=FakeUowFactory(context, source),
        embedding_gateway=embedding,
        vector_store=vector_store,
        complete_job=complete,
        expected_model="Qwen/Qwen3-VL-Embedding-8B",
        expected_dimension=4,
        index_instruction="temporary context",
    )

    result = asyncio.run(
        use_case.execute(
            job=job,
            worker_id="worker-1",
        )
    )

    assert result.state is ContextIndexJobState.SUCCEEDED
    assert embedding.calls == 1
    assert vector_store.upserts == 1
    assert complete.calls == 1
    assert vector_store.obsolete_cleanups == 1
    assert vector_store.deleted_versions == 0


def test_runtime_rejects_embedding_identity_drift_before_qdrant() -> None:
    """Не пишет vectors при несовместимой embedding model."""
    now, context, source, job = build_fixtures()
    embedding = FakeEmbeddingGateway(model="wrong-model", dimension=4)
    vector_store = FakeVectorStore()
    use_case = IndexContextSourceUseCase(
        uow_factory=FakeUowFactory(context, source),
        embedding_gateway=embedding,
        vector_store=vector_store,
        complete_job=FakeCompleteJob(job, now),
        expected_model="Qwen/Qwen3-VL-Embedding-8B",
        expected_dimension=4,
        index_instruction="temporary context",
    )

    with pytest.raises(ContextEmbeddingError):
        asyncio.run(
            use_case.execute(
                job=job,
                worker_id="worker-1",
            )
        )

    assert vector_store.upserts == 0
