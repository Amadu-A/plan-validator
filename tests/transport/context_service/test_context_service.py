# tests/transport/context_service/test_context_service.py

"""Transport tests internal Context HTTP contracts."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from context_service.application.use_cases.index_jobs import (
    EnqueueContextIndexResult,
)
from context_service.core.settings import ContextSettings
from context_service.domain.exceptions import (
    ContextIndexJobNotFoundError,
)
from context_service.domain.models import (
    ContextIndexJob,
    ContextIndexJobState,
    ContextSource,
    ContextSourceKind,
    ContextSourceState,
    ProjectContext,
    ProjectContextState,
)
from context_service.domain.search import (
    ContextSearchHit,
    ContextSearchQuery,
)
from context_service.transport import app as app_module
from fastapi.testclient import TestClient
from pydantic import SecretStr

USER_ID = UUID("11111111-1111-1111-1111-111111111111")

CONTEXT_ID = UUID("22222222-2222-2222-2222-222222222222")

SOURCE_ID = UUID("33333333-3333-3333-3333-333333333333")

JOB_ID = UUID("44444444-4444-4444-4444-444444444444")

NOW = datetime(
    2026,
    9,
    15,
    12,
    0,
    tzinfo=UTC,
)

SHA = "a" * 64
FINGERPRINT = "f" * 64


def build_context(
    state: ProjectContextState = ProjectContextState.ACTIVE,
) -> ProjectContext:
    """Создаёт deterministic Project Context fixture."""
    return ProjectContext(
        id=CONTEXT_ID,
        user_id=USER_ID,
        state=state,
        cleanup_error=None,
        created_at=NOW,
        updated_at=NOW,
        expires_at=NOW + timedelta(hours=24),
    )


def build_source(
    kind: ContextSourceKind = ContextSourceKind.TECHNICAL_ASSIGNMENT,
) -> ContextSource:
    """Создаёт deterministic Context source fixture."""
    return ContextSource(
        id=SOURCE_ID,
        context_id=CONTEXT_ID,
        user_id=USER_ID,
        kind=kind,
        original_name=(
            "technical-assignment.pdf"
            if kind is ContextSourceKind.TECHNICAL_ASSIGNMENT
            else "project-note.pdf"
        ),
        source_sha256=SHA,
        state=ContextSourceState.INDEXED,
        active_fingerprint=FINGERPRINT,
        chunk_count=1,
        created_at=NOW,
        updated_at=NOW,
    )


def build_job() -> ContextIndexJob:
    """Создаёт safe queued job fixture."""
    return ContextIndexJob(
        id=JOB_ID,
        context_id=CONTEXT_ID,
        source_id=SOURCE_ID,
        user_id=USER_ID,
        kind=ContextSourceKind.TECHNICAL_ASSIGNMENT,
        fingerprint=FINGERPRINT,
        correlation_id="transport-test",
        chunks=(),
        state=ContextIndexJobState.QUEUED,
        attempt=0,
        max_attempts=3,
        deadline_at=NOW + timedelta(minutes=12),
        next_attempt_at=None,
        dispatched_at=NOW,
        lease_owner=None,
        lease_expires_at=None,
        last_error=None,
        created_at=NOW,
        updated_at=NOW,
    )


class FakeReadiness:
    """Всегда сообщает ready."""

    async def execute(self) -> bool:
        """Возвращает True."""
        return True


class FakeCreateContext:
    """Возвращает deterministic Context."""

    async def execute(
        self,
        *,
        user_id: UUID,
    ) -> ProjectContext:
        """Проверяет owner и возвращает fixture."""
        assert user_id == USER_ID
        return build_context()


class FakeGetContext:
    """Возвращает deterministic Context."""

    async def execute(
        self,
        *,
        user_id: UUID,
        context_id: UUID,
    ) -> ProjectContext:
        """Проверяет ownership scope."""
        assert user_id == USER_ID
        assert context_id == CONTEXT_ID
        return build_context()


class FakeRegisterSource:
    """Фиксирует typed T/PZ source registration."""

    def __init__(self) -> None:
        """Инициализирует captured kind."""
        self.kind: ContextSourceKind | None = None

    async def execute(
        self,
        **kwargs: object,
    ) -> ContextSource:
        """Возвращает source requested semantic kind."""
        assert kwargs["user_id"] == USER_ID
        assert kwargs["context_id"] == CONTEXT_ID

        self.kind = kwargs["kind"]  # type: ignore[assignment]

        return build_source(self.kind)


class FakeCleanup:
    """Возвращает cleanup_pending Context."""

    async def execute(
        self,
        *,
        user_id: UUID,
        context_id: UUID,
    ) -> ProjectContext:
        """Проверяет ownership scope."""
        assert user_id == USER_ID
        assert context_id == CONTEXT_ID

        return build_context(ProjectContextState.CLEANUP_PENDING)


class FakeEnqueue:
    """Фиксирует normalized chunks enqueue."""

    def __init__(self) -> None:
        """Инициализирует captured chunk count."""
        self.chunk_count = 0

    async def execute(
        self,
        **kwargs: object,
    ) -> EnqueueContextIndexResult:
        """Возвращает deterministic durable job."""
        assert kwargs["user_id"] == USER_ID
        assert kwargs["context_id"] == CONTEXT_ID
        assert kwargs["source_id"] == SOURCE_ID

        chunks = kwargs["chunks"]

        self.chunk_count = len(
            chunks  # type: ignore[arg-type]
        )

        assert kwargs["correlation_id"]

        return EnqueueContextIndexResult(
            job_id=JOB_ID,
            fingerprint=FINGERPRINT,
            reused=False,
        )


class FakeGetIndexJob:
    """Возвращает deterministic durable job."""

    async def execute(
        self,
        *,
        user_id: UUID,
        context_id: UUID,
        job_id: UUID,
    ) -> ContextIndexJob:
        """Проверяет owner/context scope."""
        assert user_id == USER_ID
        assert context_id == CONTEXT_ID
        assert job_id == JOB_ID

        return build_job()


class FakeSearch:
    """Фиксирует route-selected T/PZ kind."""

    def __init__(self) -> None:
        """Инициализирует captured queries."""
        self.queries: list[ContextSearchQuery] = []

    async def execute(
        self,
        query: ContextSearchQuery,
        *,
        correlation_id: str,
    ) -> tuple[ContextSearchHit, ...]:
        """Возвращает explicit non-normative hit."""
        assert correlation_id

        self.queries.append(query)

        return (
            ContextSearchHit(
                source_id=SOURCE_ID,
                context_id=CONTEXT_ID,
                user_id=USER_ID,
                kind=query.kind,
                source_name="project-context.pdf",
                chunk_id="p1-0",
                text="Требование проекта.",
                score=0.91,
                fingerprint=FINGERPRINT,
                page_number=1,
                fragment_index=0,
                heading=None,
                char_start=0,
                char_end=20,
            ),
        )


class FakeContainer:
    """Transport-only container без PostgreSQL/Qdrant/RabbitMQ."""

    def __init__(
        self,
        settings: ContextSettings,
    ) -> None:
        """Собирает fake use-cases."""
        self.settings = settings

        self.check_readiness = FakeReadiness()

        self.create_context = FakeCreateContext()
        self.get_context = FakeGetContext()

        self.register_source = FakeRegisterSource()
        self.request_cleanup = FakeCleanup()

        self.enqueue_index = FakeEnqueue()
        self.get_index_job = FakeGetIndexJob()

        self.search_context = FakeSearch()

    async def aclose(self) -> None:
        """Fake container не имеет external resources."""


class FakeMissingJob:
    """Всегда возвращает owner-safe job not-found."""

    async def execute(
        self,
        **_: object,
    ) -> ContextIndexJob:
        """Поднимает domain not-found."""
        raise ContextIndexJobNotFoundError("Context indexing job was not found")


def build_settings() -> ContextSettings:
    """Создаёт transport test settings без local .env."""
    return ContextSettings(
        postgres_password=SecretStr("postgres-test"),
        rabbitmq_password=SecretStr("rabbit-test"),
        log_to_file=False,
        _env_file=None,
    )


def test_internal_context_routes_are_typed_and_non_normative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Проверяет lifecycle/index/status/T-PZ search transport contract."""
    settings = build_settings()
    fake = FakeContainer(settings)

    monkeypatch.setattr(
        app_module,
        "build_container",
        lambda _: fake,
    )

    app = app_module.create_app(settings)

    with TestClient(app) as client:
        live = client.get("/health/live")

        ready = client.get("/health/ready")

        created = client.post(
            "/internal/v1/context/contexts",
            json={"user_id": str(USER_ID)},
        )

        fetched = client.get(
            (f"/internal/v1/context/contexts/{CONTEXT_ID}"),
            params={"user_id": str(USER_ID)},
        )

        source = client.post(
            (f"/internal/v1/context/contexts/{CONTEXT_ID}/sources"),
            json={
                "user_id": str(USER_ID),
                "kind": "T",
                "original_name": ("technical-assignment.pdf"),
                "source_sha256": SHA,
            },
        )

        queued = client.post(
            (f"/internal/v1/context/contexts/{CONTEXT_ID}/sources/{SOURCE_ID}/index"),
            headers={"X-Correlation-ID": ("context-transport-test")},
            json={
                "user_id": str(USER_ID),
                "chunks": [
                    {
                        "chunk_id": "p1-0",
                        "text": ("Требование технического задания."),
                        "page_number": 1,
                    }
                ],
            },
        )

        job_status = client.get(
            (f"/internal/v1/context/contexts/{CONTEXT_ID}/jobs/{JOB_ID}"),
            params={"user_id": str(USER_ID)},
        )

        technical_assignment = client.post(
            (f"/internal/v1/context/contexts/{CONTEXT_ID}/search/T"),
            json={
                "user_id": str(USER_ID),
                "text": ("Что требует заказчик?"),
            },
        )

        project_note = client.post(
            (f"/internal/v1/context/contexts/{CONTEXT_ID}/search/PZ"),
            json={
                "user_id": str(USER_ID),
                "text": ("Что указано в пояснительной записке?"),
            },
        )

        cleanup = client.delete(
            (f"/internal/v1/context/contexts/{CONTEXT_ID}"),
            params={"user_id": str(USER_ID)},
        )

    assert live.status_code == 200
    assert ready.status_code == 200

    assert created.status_code == 201
    assert created.json()["state"] == "active"

    assert fetched.status_code == 200
    assert fetched.json()["id"] == str(CONTEXT_ID)

    assert source.status_code == 201
    assert source.json()["kind"] == "T"

    assert queued.status_code == 202
    assert queued.json()["job_id"] == str(JOB_ID)
    assert queued.headers["X-Correlation-ID"] == "context-transport-test"
    assert fake.enqueue_index.chunk_count == 1

    assert job_status.status_code == 200
    assert job_status.json()["state"] == "queued"

    assert "chunks" not in job_status.json()

    assert "lease_owner" not in job_status.json()

    assert "last_error" not in job_status.json()

    assert technical_assignment.status_code == 200

    assert project_note.status_code == 200

    assert fake.search_context.queries[0].kind is ContextSourceKind.TECHNICAL_ASSIGNMENT

    assert fake.search_context.queries[1].kind is ContextSourceKind.PROJECT_NOTE

    assert (
        technical_assignment.json()["hits"][0]["semantic_role"] == "project_context_non_normative"
    )

    assert project_note.json()["hits"][0]["semantic_role"] == "project_context_non_normative"

    assert cleanup.status_code == 202
    assert cleanup.json()["state"] == "cleanup_pending"

    assert app.openapi_url is None


def test_context_job_not_found_has_safe_http_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Проверяет owner-safe 404 envelope для отсутствующего job."""
    settings = build_settings()

    fake = FakeContainer(settings)

    fake.get_index_job = FakeMissingJob()

    monkeypatch.setattr(
        app_module,
        "build_container",
        lambda _: fake,
    )

    app = app_module.create_app(settings)

    with TestClient(app) as client:
        response = client.get(
            (f"/internal/v1/context/contexts/{CONTEXT_ID}/jobs/{JOB_ID}"),
            params={"user_id": str(USER_ID)},
        )

    assert response.status_code == 404

    assert response.json() == {
        "error": {
            "code": ("context_resource_not_found"),
            "message": ("Context indexing job was not found"),
        }
    }
