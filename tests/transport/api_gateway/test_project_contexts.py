# tests/transport/api_gateway/test_project_contexts.py

"""Transport tests authenticated public Project Context facade."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from api_gateway.application.auth_service import AuthUser
from api_gateway.application.context_service import (
    ContextSourceKind,
    ContextSourceState,
    GatewayContextSource,
    GatewayProjectContext,
    ProjectContextState,
)
from api_gateway.core.settings import GatewaySettings
from api_gateway.transport.app import create_app
from fastapi.testclient import TestClient
from plan_validator_common.settings import Environment

USER_ID = UUID("11111111-1111-1111-1111-111111111111")

CONTEXT_ID = UUID("22222222-2222-2222-2222-222222222222")

SOURCE_ID = UUID("33333333-3333-3333-3333-333333333333")

NOW = datetime(
    2026,
    9,
    15,
    12,
    0,
    tzinfo=UTC,
)

SHA = "a" * 64


class FakeAuthServiceClient:
    """Auth double Project Context public transport tests."""

    def __init__(
        self,
        user: AuthUser,
    ) -> None:
        """Сохраняет authenticated user."""
        self.user = user

    async def get_current_user(
        self,
        *,
        session_token: str,
    ) -> AuthUser:
        """Разрешает deterministic session."""
        assert session_token == "context-session"

        return self.user

    async def aclose(self) -> None:
        """Fake client не имеет resources."""

    async def register_user(
        self,
        **kwargs: object,
    ) -> object:
        """Не используется в Context transport test."""
        del kwargs
        raise AssertionError("Unexpected registration")

    async def login_user(
        self,
        **kwargs: object,
    ) -> object:
        """Не используется в Context transport test."""
        del kwargs
        raise AssertionError("Unexpected login")

    async def logout_session(
        self,
        **kwargs: object,
    ) -> None:
        """Не используется в Context transport test."""
        del kwargs
        raise AssertionError("Unexpected logout")


class FakeContextServiceClient:
    """Context client double, фиксирующий server-selected ownership."""

    def __init__(self) -> None:
        """Инициализирует captured owner ids."""
        self.user_ids: list[UUID] = []
        self.register_calls = 0

    async def create_context(
        self,
        *,
        user_id: UUID,
    ) -> GatewayProjectContext:
        """Создаёт deterministic context."""
        self.user_ids.append(user_id)

        return self._context(ProjectContextState.ACTIVE)

    async def get_context(
        self,
        *,
        user_id: UUID,
        context_id: UUID,
    ) -> GatewayProjectContext:
        """Возвращает owner context."""
        assert context_id == CONTEXT_ID

        self.user_ids.append(user_id)

        return self._context(ProjectContextState.ACTIVE)

    async def request_cleanup(
        self,
        *,
        user_id: UUID,
        context_id: UUID,
    ) -> GatewayProjectContext:
        """Возвращает cleanup_pending state."""
        assert context_id == CONTEXT_ID

        self.user_ids.append(user_id)

        return self._context(ProjectContextState.CLEANUP_PENDING)

    async def register_source(
        self,
        *,
        user_id: UUID,
        context_id: UUID,
        kind: ContextSourceKind,
        original_name: str,
        source_sha256: str,
    ) -> GatewayContextSource:
        """Регистрирует typed metadata."""
        assert context_id == CONTEXT_ID
        assert original_name == "technical-assignment.pdf"
        assert source_sha256 == SHA

        self.user_ids.append(user_id)
        self.register_calls += 1

        return GatewayContextSource(
            id=SOURCE_ID,
            context_id=CONTEXT_ID,
            user_id=USER_ID,
            kind=kind,
            original_name=original_name,
            source_sha256=source_sha256,
            state=(ContextSourceState.AWAITING_CHUNKS),
            active_fingerprint=None,
            chunk_count=0,
            created_at=NOW,
            updated_at=NOW,
        )

    async def aclose(self) -> None:
        """Fake client не имеет resources."""

    @staticmethod
    def _context(
        state: ProjectContextState,
    ) -> GatewayProjectContext:
        """Создаёт deterministic context DTO."""
        return GatewayProjectContext(
            id=CONTEXT_ID,
            user_id=USER_ID,
            state=state,
            created_at=NOW,
            updated_at=NOW,
            expires_at=(NOW + timedelta(hours=24)),
        )


def test_project_context_facade_uses_authenticated_user_only(
    tmp_path: Path,
) -> None:
    """Не доверяет browser user_id и не публикует internal indexing/search."""
    settings = GatewaySettings(
        environment=Environment.TEST,
        log_to_file=False,
        log_root_dir=tmp_path,
        _env_file=None,
    )

    app = create_app(settings)

    user = AuthUser(
        id=USER_ID,
        email="context@example.com",
        created_at=NOW,
    )

    fake_context = FakeContextServiceClient()

    app.state.container.auth_service = FakeAuthServiceClient(user)

    app.state.container.context_service = fake_context

    spoofed_user_id = uuid4()

    with TestClient(app) as client:
        unauthorized = client.post("/api/v1/project-contexts")

        assert unauthorized.status_code == 401

        client.cookies.set(
            settings.session_cookie.name,
            "context-session",
        )

        created = client.post(f"/api/v1/project-contexts?user_id={spoofed_user_id}")

        fetched = client.get(f"/api/v1/project-contexts/{CONTEXT_ID}")

        source = client.post(
            (f"/api/v1/project-contexts/{CONTEXT_ID}/sources"),
            json={
                "kind": "T",
                "original_name": ("technical-assignment.pdf"),
                "source_sha256": SHA,
            },
        )

        spoofed_source = client.post(
            (f"/api/v1/project-contexts/{CONTEXT_ID}/sources"),
            json={
                "user_id": str(spoofed_user_id),
                "kind": "T",
                "original_name": ("technical-assignment.pdf"),
                "source_sha256": SHA,
            },
        )

        public_index = client.post(
            (f"/api/v1/project-contexts/{CONTEXT_ID}/sources/{SOURCE_ID}/index"),
            json={"chunks": []},
        )

        public_search = client.post(
            (f"/api/v1/project-contexts/{CONTEXT_ID}/search/T"),
            json={"text": "test"},
        )

        cleanup = client.delete(f"/api/v1/project-contexts/{CONTEXT_ID}")

    assert created.status_code == 201
    assert created.json()["id"] == str(CONTEXT_ID)
    assert "user_id" not in created.json()

    assert fetched.status_code == 200

    assert source.status_code == 201
    assert source.json()["kind"] == "T"
    assert "user_id" not in source.json()

    assert spoofed_source.status_code == 422

    assert fake_context.register_calls == 1

    assert public_index.status_code == 404
    assert public_search.status_code == 404

    assert cleanup.status_code == 202
    assert cleanup.json()["state"] == "cleanup_pending"

    assert fake_context.user_ids
    assert all(user_id == USER_ID for user_id in fake_context.user_ids)
