# tests/unit/context_service/test_search_context.py

"""Unit tests typed temporary T/PZ retrieval semantics."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from context_service.application.ports.embedding_gateway import EmbeddedContextTexts
from context_service.application.use_cases.search_context import SearchProjectContextUseCase
from context_service.domain.models import (
    ContextSource,
    ContextSourceKind,
    ContextSourceState,
    ProjectContext,
    ProjectContextState,
)
from context_service.domain.search import ContextSearchHit, ContextSearchQuery


class FakeContexts:
    """Возвращает заданный Project Context."""

    def __init__(self, context: ProjectContext) -> None:
        """Сохраняет fixture."""
        self.context = context

    async def get_for_user(self, **_: object) -> ProjectContext:
        """Возвращает fixture."""
        return self.context


class FakeSources:
    """Возвращает заданный typed Context source."""

    def __init__(self, source: ContextSource) -> None:
        """Сохраняет fixture."""
        self.source = source

    async def get_for_context_kind(self, **_: object) -> ContextSource:
        """Возвращает fixture."""
        return self.source


class FakeUow:
    """Read-only fake UoW search use-case."""

    def __init__(self, context: ProjectContext, source: ContextSource) -> None:
        """Создаёт fake repositories."""
        self.contexts = FakeContexts(context)
        self.sources = FakeSources(source)

    async def __aenter__(self) -> "FakeUow":
        """Возвращает себя."""
        return self

    async def __aexit__(self, *args: object) -> None:
        """Ничего не закрывает."""
        del args


class FakeUowFactory:
    """Создаёт fake UoW."""

    def __init__(self, context: ProjectContext, source: ContextSource) -> None:
        """Сохраняет fixtures."""
        self.context = context
        self.source = source

    def __call__(self) -> FakeUow:
        """Создаёт новый fake scope."""
        return FakeUow(self.context, self.source)


class FakeEmbedding:
    """Возвращает один query vector."""

    def __init__(self) -> None:
        """Инициализирует call state."""
        self.correlation_id: str | None = None
        self.calls = 0

    async def embed_texts(
        self,
        *,
        correlation_id: str,
        **_: object,
    ) -> EmbeddedContextTexts:
        """Фиксирует correlation id."""
        self.calls += 1
        self.correlation_id = correlation_id
        return EmbeddedContextTexts(
            model="Qwen/Qwen3-VL-Embedding-8B",
            dimension=4,
            vectors=((0.5, 0.5, 0.5, 0.5),),
        )


class FakeVectorStore:
    """Возвращает explicit non-normative hit."""

    def __init__(self, hit: ContextSearchHit) -> None:
        """Сохраняет hit."""
        self.hit = hit
        self.query: ContextSearchQuery | None = None

    async def search(
        self,
        *,
        query: ContextSearchQuery,
        **_: object,
    ) -> tuple[ContextSearchHit, ...]:
        """Фиксирует normalized query."""
        self.query = query
        return (self.hit,)


def build_search_fixtures(
    state: ProjectContextState = ProjectContextState.ACTIVE,
) -> tuple[ProjectContext, ContextSource, ContextSearchHit]:
    """Создаёт indexed T fixture для typed search."""
    now = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)
    user_id = uuid4()
    context_id = uuid4()
    source_id = uuid4()
    context = ProjectContext(
        id=context_id,
        user_id=user_id,
        state=state,
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
        original_name="tz.pdf",
        source_sha256="a" * 64,
        state=ContextSourceState.INDEXED,
        active_fingerprint="b" * 64,
        chunk_count=1,
        created_at=now,
        updated_at=now,
    )
    hit = ContextSearchHit(
        source_id=source_id,
        context_id=context_id,
        user_id=user_id,
        kind=source.kind,
        source_name=source.original_name,
        chunk_id="p1-0",
        text="Требование проекта.",
        score=0.91,
        fingerprint="b" * 64,
        page_number=1,
        fragment_index=0,
        heading=None,
        char_start=None,
        char_end=None,
    )
    return context, source, hit


def test_search_preserves_typed_non_normative_semantics() -> None:
    """T search не превращает project context в нормативное доказательство."""
    context, source, hit = build_search_fixtures()
    embedding = FakeEmbedding()
    vector_store = FakeVectorStore(hit)
    use_case = SearchProjectContextUseCase(
        uow_factory=FakeUowFactory(context, source),
        embedding_gateway=embedding,
        vector_store=vector_store,
        expected_model="Qwen/Qwen3-VL-Embedding-8B",
        expected_dimension=4,
        query_instruction="temporary query",
        default_limit=10,
        max_limit=50,
        default_score_threshold=0.3,
        max_query_chars=60000,
    )
    query = ContextSearchQuery(
        user_id=context.user_id,
        context_id=context.id,
        kind=ContextSourceKind.TECHNICAL_ASSIGNMENT,
        text="Что требует заказчик?",
    )

    result = asyncio.run(use_case.execute(query, correlation_id="corr-search"))

    assert len(result) == 1
    assert result[0].semantic_role == "project_context_non_normative"
    assert result[0].kind is ContextSourceKind.TECHNICAL_ASSIGNMENT
    assert embedding.correlation_id == "corr-search"
    assert vector_store.query is not None
    assert vector_store.query.kind is ContextSourceKind.TECHNICAL_ASSIGNMENT


def test_search_hides_cleanup_pending_context_without_embedding() -> None:
    """Logical cleanup делает T/PZ невидимыми до physical Qdrant delete."""
    context, source, hit = build_search_fixtures(ProjectContextState.CLEANUP_PENDING)
    embedding = FakeEmbedding()
    use_case = SearchProjectContextUseCase(
        uow_factory=FakeUowFactory(context, source),
        embedding_gateway=embedding,
        vector_store=FakeVectorStore(hit),
        expected_model="Qwen/Qwen3-VL-Embedding-8B",
        expected_dimension=4,
        query_instruction="temporary query",
        default_limit=10,
        max_limit=50,
        default_score_threshold=0.3,
        max_query_chars=60000,
    )
    query = ContextSearchQuery(
        user_id=context.user_id,
        context_id=context.id,
        kind=ContextSourceKind.TECHNICAL_ASSIGNMENT,
        text="query",
    )

    result = asyncio.run(use_case.execute(query, correlation_id="corr-hidden"))

    assert result == ()
    assert embedding.calls == 0
