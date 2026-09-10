# tests/unit/retrieval_service/test_indexing.py

"""Unit tests crash-safe managed-source registration/reindex lifecycle."""

import asyncio
from datetime import UTC, datetime
from types import TracebackType
from uuid import UUID

import pytest
from retrieval_service.application.ports.embedding_gateway import EmbeddedTexts
from retrieval_service.application.use_cases.catalog_events import (
    DeleteCatalogSourceUseCase,
    RegisterCatalogSourceUseCase,
)
from retrieval_service.application.use_cases.index_source import IndexManagedSourceUseCase
from retrieval_service.domain.exceptions import RetrievalSourceConflictError
from retrieval_service.domain.source_index import (
    IndexSourceJob,
    ManagedSourceIndex,
    NormalizedChunk,
    SourceIndexState,
    SourceKind,
)

NOW = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
USER_ID = UUID("11111111-1111-1111-1111-111111111111")
SECTION_ID = UUID("22222222-2222-2222-2222-222222222222")
SOURCE_ID = UUID("33333333-3333-3333-3333-333333333333")
JOB_ID = UUID("44444444-4444-4444-4444-444444444444")
SHA = "a" * 64


class FakeClock:
    """Возвращает deterministic indexing timestamp."""

    def now(self) -> datetime:
        """Возвращает фиксированное UTC время."""
        return NOW


class MemorySourceIndexRepository:
    """In-memory source registry с теми же application semantics."""

    def __init__(self) -> None:
        """Создаёт пустое registry."""
        self.items: dict[UUID, ManagedSourceIndex] = {}

    async def add(self, source: ManagedSourceIndex) -> None:
        """Добавляет source."""
        self.items[source.source_id] = source

    async def get(self, source_id: UUID) -> ManagedSourceIndex | None:
        """Возвращает source."""
        return self.items.get(source_id)

    async def get_for_update(self, source_id: UUID) -> ManagedSourceIndex | None:
        """Имитирует row lock возвратом source."""
        return self.items.get(source_id)

    async def save(self, source: ManagedSourceIndex) -> None:
        """Сохраняет актуальное source state."""
        self.items[source.source_id] = source

    async def list_active_version_keys(
        self,
        *,
        user_id: UUID,
        kind: SourceKind,
        section_ids: tuple[UUID, ...],
        source_ids: tuple[UUID, ...],
    ) -> tuple[str, ...]:
        """Не используется этими indexing tests."""
        del user_id
        del kind
        del section_ids
        del source_ids
        return ()


class FakeUow:
    """In-memory Retrieval transaction boundary."""

    def __init__(self, repository: MemorySourceIndexRepository) -> None:
        """Сохраняет shared repository и commit count."""
        self.source_indexes = repository
        self.commit_count = 0

    async def __aenter__(self) -> "FakeUow":
        """Открывает fake transaction."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Закрывает fake transaction."""
        del exc_type
        del exc
        del traceback

    async def commit(self) -> None:
        """Фиксирует commit count."""
        self.commit_count += 1

    async def rollback(self) -> None:
        """Fake rollback ничего не меняет."""


class FakeUowFactory:
    """Создаёт UoW поверх общего memory repository."""

    def __init__(self, repository: MemorySourceIndexRepository) -> None:
        """Сохраняет repository."""
        self.repository = repository

    def __call__(self) -> FakeUow:
        """Создаёт новый fake transaction."""
        return FakeUow(self.repository)


class FakeEmbeddingGateway:
    """Возвращает deterministic vectors для всех chunks."""

    def __init__(self) -> None:
        """Инициализирует call counter."""
        self.calls = 0

    async def embed_texts(
        self,
        *,
        texts: tuple[str, ...],
        instruction: str,
        correlation_id: str,
    ) -> EmbeddedTexts:
        """Возвращает один 4-dimensional vector на text."""
        del instruction
        del correlation_id
        self.calls += 1
        return EmbeddedTexts(
            model="Qwen/Qwen3-VL-Embedding-8B",
            dimension=4,
            vectors=tuple((1.0, 0.0, 0.0, 0.0) for _ in texts),
        )


class FakeVectorStore:
    """Фиксирует candidate/cleanup lifecycle Qdrant adapter."""

    def __init__(self) -> None:
        """Инициализирует captured versions."""
        self.upserts: list[str] = []
        self.deleted_versions: list[str] = []
        self.deleted_sources: list[UUID] = []
        self.obsolete_cleanup: list[tuple[UUID, str]] = []

    async def upsert_version(
        self,
        *,
        source: ManagedSourceIndex,
        fingerprint: str,
        chunks: tuple[NormalizedChunk, ...],
        vectors: tuple[tuple[float, ...], ...],
    ) -> None:
        """Фиксирует candidate upsert."""
        assert source.source_id == SOURCE_ID
        assert len(chunks) == len(vectors)
        self.upserts.append(fingerprint)

    async def delete_version(self, *, source_id: UUID, fingerprint: str) -> None:
        """Фиксирует candidate compensation delete."""
        assert source_id == SOURCE_ID
        self.deleted_versions.append(fingerprint)

    async def delete_obsolete_versions(
        self,
        *,
        source_id: UUID,
        active_fingerprint: str,
    ) -> None:
        """Фиксирует stale generation cleanup."""
        self.obsolete_cleanup.append((source_id, active_fingerprint))

    async def delete_source(self, *, source_id: UUID) -> None:
        """Фиксирует полное source cleanup."""
        self.deleted_sources.append(source_id)

    async def search(self, **kwargs: object) -> tuple[object, ...]:
        """Не используется indexing tests."""
        del kwargs
        return ()

    async def ready(self) -> bool:
        """Fake store всегда готов."""
        return True


def _chunks() -> tuple[NormalizedChunk, ...]:
    """Возвращает два parser-neutral chunks."""
    return (
        NormalizedChunk(chunk_id="p1-0", text="Нормативное требование", page_number=1),
        NormalizedChunk(chunk_id="p2-0", text="Продолжение требования", page_number=2),
    )


def _register(factory: FakeUowFactory) -> ManagedSourceIndex:
    """Регистрирует Catalog source через application event use-case."""
    use_case = RegisterCatalogSourceUseCase(factory)  # type: ignore[arg-type]
    return asyncio.run(
        use_case.execute(
            source_id=SOURCE_ID,
            user_id=USER_ID,
            section_id=SECTION_ID,
            kind=SourceKind.NORMATIVE,
            original_name="СП runtime.pdf",
            mime_type="application/pdf",
            source_sha256=SHA,
            occurred_at=NOW,
        )
    )


def test_reindex_activates_fingerprint_after_candidate_write() -> None:
    """Проверяет candidate Qdrant write → DB activation → stale cleanup."""
    repository = MemorySourceIndexRepository()
    factory = FakeUowFactory(repository)
    _register(factory)
    embeddings = FakeEmbeddingGateway()
    vectors = FakeVectorStore()
    use_case = IndexManagedSourceUseCase(
        uow_factory=factory,  # type: ignore[arg-type]
        embedding_gateway=embeddings,
        vector_store=vectors,  # type: ignore[arg-type]
        clock=FakeClock(),
        expected_model="Qwen/Qwen3-VL-Embedding-8B",
        expected_dimension=4,
        max_chunks=10,
        max_chunk_chars=1000,
    )
    job = IndexSourceJob(
        job_id=JOB_ID,
        source_id=SOURCE_ID,
        source_sha256=SHA,
        chunks=_chunks(),
        correlation_id="test-correlation",
    )

    result = asyncio.run(use_case.execute(job))
    stored = repository.items[SOURCE_ID]

    assert result.reused is False
    assert stored.state is SourceIndexState.INDEXED
    assert stored.active_fingerprint == result.fingerprint
    assert stored.chunk_count == 2
    assert embeddings.calls == 1
    assert vectors.upserts == [result.fingerprint]
    assert vectors.obsolete_cleanup == [(SOURCE_ID, result.fingerprint)]

    second = asyncio.run(use_case.execute(job))
    assert second.reused is True
    assert embeddings.calls == 1
    assert len(vectors.upserts) == 1


def test_reindex_rejects_stale_source_hash_before_embedding() -> None:
    """Не позволяет индексировать chunks уже другой Catalog версии."""
    repository = MemorySourceIndexRepository()
    factory = FakeUowFactory(repository)
    _register(factory)
    embeddings = FakeEmbeddingGateway()
    use_case = IndexManagedSourceUseCase(
        uow_factory=factory,  # type: ignore[arg-type]
        embedding_gateway=embeddings,
        vector_store=FakeVectorStore(),  # type: ignore[arg-type]
        clock=FakeClock(),
        expected_model="Qwen/Qwen3-VL-Embedding-8B",
        expected_dimension=4,
        max_chunks=10,
        max_chunk_chars=1000,
    )

    with pytest.raises(RetrievalSourceConflictError):
        asyncio.run(
            use_case.execute(
                IndexSourceJob(
                    job_id=JOB_ID,
                    source_id=SOURCE_ID,
                    source_sha256="b" * 64,
                    chunks=_chunks(),
                    correlation_id="test-correlation",
                )
            )
        )

    assert embeddings.calls == 0


def test_delete_tombstones_registry_before_vector_cleanup_retry() -> None:
    """Проверяет immediate DB exclusion и идемпотентный Qdrant delete."""
    repository = MemorySourceIndexRepository()
    factory = FakeUowFactory(repository)
    _register(factory)
    vectors = FakeVectorStore()
    use_case = DeleteCatalogSourceUseCase(
        uow_factory=factory,  # type: ignore[arg-type]
        vector_store=vectors,  # type: ignore[arg-type]
    )

    deleted = asyncio.run(
        use_case.execute(
            source_id=SOURCE_ID,
            user_id=USER_ID,
            section_id=SECTION_ID,
            kind=SourceKind.NORMATIVE,
            original_name="СП runtime.pdf",
            mime_type="application/pdf",
            source_sha256=SHA,
            occurred_at=NOW,
        )
    )

    assert deleted.state is SourceIndexState.DELETED
    assert repository.items[SOURCE_ID].active_fingerprint is None
    assert vectors.deleted_sources == [SOURCE_ID]

    asyncio.run(
        use_case.execute(
            source_id=SOURCE_ID,
            user_id=USER_ID,
            section_id=SECTION_ID,
            kind=SourceKind.NORMATIVE,
            original_name="СП runtime.pdf",
            mime_type="application/pdf",
            source_sha256=SHA,
            occurred_at=NOW,
        )
    )
    assert vectors.deleted_sources == [SOURCE_ID, SOURCE_ID]
