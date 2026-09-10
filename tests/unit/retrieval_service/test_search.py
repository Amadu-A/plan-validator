# tests/unit/retrieval_service/test_search.py

"""Unit tests typed tenant-safe N/U search use-case."""

import asyncio
from types import TracebackType
from uuid import UUID

from retrieval_service.application.ports.embedding_gateway import EmbeddedTexts
from retrieval_service.application.use_cases.search_sources import SearchManagedSourcesUseCase
from retrieval_service.domain.search import SearchHit, SearchQuery
from retrieval_service.domain.source_index import SourceKind

USER_ID = UUID("11111111-1111-1111-1111-111111111111")
SECTION_ID = UUID("22222222-2222-2222-2222-222222222222")
SOURCE_ID = UUID("33333333-3333-3333-3333-333333333333")


class FakeSourceIndexRepository:
    """Возвращает configured active generation keys."""

    def __init__(self, version_keys: tuple[str, ...]) -> None:
        """Сохраняет active keys и captured query filters."""
        self.version_keys = version_keys
        self.calls: list[tuple[UUID, SourceKind]] = []

    async def list_active_version_keys(
        self,
        *,
        user_id: UUID,
        kind: SourceKind,
        section_ids: tuple[UUID, ...],
        source_ids: tuple[UUID, ...],
    ) -> tuple[str, ...]:
        """Фиксирует mandatory tenant/type filter."""
        del section_ids
        del source_ids
        self.calls.append((user_id, kind))
        return self.version_keys


class FakeUow:
    """Минимальный read-only Retrieval UoW."""

    def __init__(self, repository: FakeSourceIndexRepository) -> None:
        """Сохраняет source repository."""
        self.source_indexes = repository

    async def __aenter__(self) -> "FakeUow":
        """Открывает fake scope."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Закрывает fake scope."""
        del exc_type
        del exc
        del traceback

    async def commit(self) -> None:
        """Read-only test не commit'ит."""

    async def rollback(self) -> None:
        """Read-only test не rollback'ит."""


class FakeUowFactory:
    """Возвращает read-only fake UoW."""

    def __init__(self, repository: FakeSourceIndexRepository) -> None:
        """Сохраняет repository."""
        self.repository = repository

    def __call__(self) -> FakeUow:
        """Создаёт fake UoW."""
        return FakeUow(self.repository)


class FakeEmbeddingGateway:
    """Считает query embedding calls."""

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
        """Возвращает один compatible query vector."""
        assert len(texts) == 1
        assert instruction
        assert correlation_id
        self.calls += 1
        return EmbeddedTexts(
            model="Qwen/Qwen3-VL-Embedding-8B",
            dimension=4,
            vectors=((1.0, 0.0, 0.0, 0.0),),
        )


class FakeVectorStore:
    """Фиксирует typed search и возвращает один hit."""

    def __init__(self) -> None:
        """Инициализирует captured query."""
        self.query: SearchQuery | None = None
        self.version_keys: tuple[str, ...] = ()

    async def search(
        self,
        *,
        query: SearchQuery,
        query_vector: tuple[float, ...],
        active_version_keys: tuple[str, ...],
    ) -> tuple[SearchHit, ...]:
        """Возвращает deterministic hit с тем же type/tenant."""
        assert query_vector == (1.0, 0.0, 0.0, 0.0)
        self.query = query
        self.version_keys = active_version_keys
        return (
            SearchHit(
                source_id=SOURCE_ID,
                user_id=USER_ID,
                section_id=SECTION_ID,
                kind=query.kind,
                source_name="СП 1.pdf",
                chunk_id="p1-0",
                text="Требование",
                score=0.9,
                fingerprint="f" * 64,
                page_number=1,
                fragment_index=0,
                heading=None,
                char_start=0,
                char_end=10,
            ),
        )

    async def ready(self) -> bool:
        """Fake store всегда готов."""
        return True


def test_search_skips_gpu_when_registry_has_no_active_sources() -> None:
    """Не расходует shared GPU для пустого N/U corpus."""
    repository = FakeSourceIndexRepository(())
    embeddings = FakeEmbeddingGateway()
    vectors = FakeVectorStore()
    use_case = SearchManagedSourcesUseCase(
        uow_factory=FakeUowFactory(repository),  # type: ignore[arg-type]
        embedding_gateway=embeddings,
        vector_store=vectors,  # type: ignore[arg-type]
        expected_model="Qwen/Qwen3-VL-Embedding-8B",
        expected_dimension=4,
        max_limit=50,
    )
    query = SearchQuery(
        user_id=USER_ID,
        kind=SourceKind.USER,
        text="требование",
    )

    assert asyncio.run(use_case.execute(query, correlation_id="c1")) == ()
    assert embeddings.calls == 0
    assert repository.calls == [(USER_ID, SourceKind.USER)]


def test_search_passes_tenant_kind_and_active_generation_to_vector_store() -> None:
    """Проверяет обязательную isolation N/U + user_id + active fingerprint."""
    version_key = f"{SOURCE_ID}:{'f' * 64}"
    repository = FakeSourceIndexRepository((version_key,))
    embeddings = FakeEmbeddingGateway()
    vectors = FakeVectorStore()
    use_case = SearchManagedSourcesUseCase(
        uow_factory=FakeUowFactory(repository),  # type: ignore[arg-type]
        embedding_gateway=embeddings,
        vector_store=vectors,  # type: ignore[arg-type]
        expected_model="Qwen/Qwen3-VL-Embedding-8B",
        expected_dimension=4,
        max_limit=50,
    )
    query = SearchQuery(
        user_id=USER_ID,
        kind=SourceKind.NORMATIVE,
        text="норматив",
        section_ids=(SECTION_ID,),
        source_ids=(SOURCE_ID,),
        limit=5,
        score_threshold=0.2,
    )

    hits = asyncio.run(use_case.execute(query, correlation_id="c2"))

    assert len(hits) == 1
    assert hits[0].kind is SourceKind.NORMATIVE
    assert embeddings.calls == 1
    assert repository.calls == [(USER_ID, SourceKind.NORMATIVE)]
    assert vectors.query == query
    assert vectors.version_keys == (version_key,)
