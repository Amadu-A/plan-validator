# tests/transport/retrieval_service/test_retrieval_service.py

"""Transport tests internal Retrieval HTTP contracts."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from retrieval_service.core.settings import RetrievalSettings
from retrieval_service.domain.search import SearchHit, SearchQuery
from retrieval_service.domain.source_index import ManagedSourceIndex, SourceIndexState, SourceKind
from retrieval_service.transport import app as app_module

USER_ID = UUID("11111111-1111-1111-1111-111111111111")
SECTION_ID = UUID("22222222-2222-2222-2222-222222222222")
SOURCE_ID = UUID("33333333-3333-3333-3333-333333333333")
JOB_ID = UUID("44444444-4444-4444-4444-444444444444")
NOW = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
SHA = "a" * 64


class FakeReadiness:
    """Всегда сообщает ready."""

    async def execute(self) -> bool:
        """Возвращает True."""
        return True


class FakeEnqueue:
    """Фиксирует normalized indexing request."""

    def __init__(self) -> None:
        """Инициализирует captured kind-neutral call."""
        self.source_id: UUID | None = None
        self.chunk_count = 0

    async def execute(self, **kwargs: object) -> UUID:
        """Возвращает deterministic job id."""
        self.source_id = kwargs["source_id"]  # type: ignore[assignment]
        self.chunk_count = len(kwargs["chunks"])  # type: ignore[arg-type]
        return JOB_ID


class FakeSearch:
    """Фиксирует route-selected N/U SourceKind."""

    def __init__(self) -> None:
        """Инициализирует captured queries."""
        self.queries: list[SearchQuery] = []

    async def execute(
        self,
        query: SearchQuery,
        *,
        correlation_id: str,
    ) -> tuple[SearchHit, ...]:
        """Возвращает один typed hit."""
        assert correlation_id
        self.queries.append(query)
        return (
            SearchHit(
                source_id=SOURCE_ID,
                user_id=USER_ID,
                section_id=SECTION_ID,
                kind=query.kind,
                source_name="СП 1.pdf",
                chunk_id="p1-0",
                text="Требование",
                score=0.91,
                fingerprint="f" * 64,
                page_number=1,
                fragment_index=0,
                heading="Раздел",
                char_start=0,
                char_end=10,
            ),
        )


class FakeStatus:
    """Возвращает indexed source registry state."""

    async def execute(self, source_id: UUID) -> ManagedSourceIndex:
        """Возвращает deterministic source status."""
        assert source_id == SOURCE_ID
        return ManagedSourceIndex(
            source_id=SOURCE_ID,
            user_id=USER_ID,
            section_id=SECTION_ID,
            kind=SourceKind.NORMATIVE,
            original_name="СП 1.pdf",
            mime_type="application/pdf",
            source_sha256=SHA,
            state=SourceIndexState.INDEXED,
            active_fingerprint="f" * 64,
            model_name="Qwen/Qwen3-VL-Embedding-8B",
            vector_dimension=4096,
            chunk_count=1,
            last_error=None,
            created_at=NOW,
            updated_at=NOW,
            deleted_at=None,
        )


class FakeContainer:
    """Transport-only container без PostgreSQL/Qdrant/RabbitMQ."""

    def __init__(self, settings: RetrievalSettings) -> None:
        """Собирает fake use-cases."""
        self.settings = settings
        self.check_readiness = FakeReadiness()
        self.enqueue_source_index = FakeEnqueue()
        self.search_sources = FakeSearch()
        self.get_source_status = FakeStatus()

    async def aclose(self) -> None:
        """Fake container не имеет внешних ресурсов."""


def test_internal_retrieval_routes_are_typed_and_clickable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Проверяет health/index/status и отдельные N/U search surfaces."""
    settings = RetrievalSettings(
        postgres_password=SecretStr("postgres-test"),
        rabbitmq_password=SecretStr("rabbit-test"),
        log_to_file=False,
        _env_file=None,
    )
    fake = FakeContainer(settings)

    monkeypatch.setattr(app_module, "build_container", lambda _: fake)
    app = app_module.create_app(settings)

    with TestClient(app) as client:
        live = client.get("/health/live")
        ready = client.get("/health/ready")
        queued = client.post(
            f"/internal/v1/retrieval/sources/{SOURCE_ID}/index",
            json={
                "source_sha256": SHA,
                "chunks": [
                    {
                        "chunk_id": "p1-0",
                        "text": "Нормативное требование",
                        "page_number": 1,
                    }
                ],
            },
        )
        status = client.get(f"/internal/v1/retrieval/sources/{SOURCE_ID}/status")
        normative = client.post(
            "/internal/v1/retrieval/normative/search",
            json={"user_id": str(USER_ID), "text": "требование"},
        )
        user = client.post(
            "/internal/v1/retrieval/user/search",
            json={"user_id": str(USER_ID), "text": "требование"},
        )

    assert live.status_code == 200
    assert ready.status_code == 200
    assert queued.status_code == 202
    assert queued.json()["job_id"] == str(JOB_ID)
    assert fake.enqueue_source_index.source_id == SOURCE_ID
    assert fake.enqueue_source_index.chunk_count == 1
    assert status.status_code == 200
    assert status.json()["state"] == "indexed"
    assert normative.status_code == 200
    assert user.status_code == 200
    assert fake.search_sources.queries[0].kind is SourceKind.NORMATIVE
    assert fake.search_sources.queries[1].kind is SourceKind.USER
    assert normative.json()["hits"][0]["source_content_url"] == (
        f"/api/v1/catalog/normative-documents/{SOURCE_ID}/content"
    )
    assert user.json()["hits"][0]["source_content_url"] == (
        f"/api/v1/catalog/user-documents/{SOURCE_ID}/content"
    )
