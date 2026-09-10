# tests/transport/api_gateway/test_catalog_sources.py

"""Transport tests authenticated public managed source Gateway facade."""

from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote
from uuid import UUID, uuid4

from api_gateway.application.auth_service import AuthUser
from api_gateway.application.catalog_sources import (
    CatalogManagedSource,
    CatalogSourceContent,
    CatalogSourceKind,
    CatalogSourceLifecycle,
)
from api_gateway.core.settings import GatewaySettings
from api_gateway.transport.app import create_app
from fastapi.testclient import TestClient
from plan_validator_common.settings import Environment


class FakeAuthServiceClient:
    """Auth double managed source transport tests."""

    def __init__(self, user: AuthUser) -> None:
        """Сохраняет authenticated user."""
        self.user = user

    async def get_current_user(
        self,
        *,
        session_token: str,
    ) -> AuthUser:
        """Разрешает известный test token."""
        assert session_token == "source-session"
        return self.user

    async def aclose(self) -> None:
        """Fake client не имеет resources."""

    async def register_user(self, **kwargs: object) -> object:
        """Недоступен в source transport test."""
        del kwargs
        raise AssertionError("Unexpected registration")

    async def login_user(self, **kwargs: object) -> object:
        """Недоступен в source transport test."""
        del kwargs
        raise AssertionError("Unexpected login")

    async def logout_session(self, **kwargs: object) -> None:
        """Недоступен в source transport test."""
        del kwargs
        raise AssertionError("Unexpected logout")


class FakeCatalogSourceServiceClient:
    """In-memory managed source client double."""

    def __init__(self) -> None:
        """Создаёт empty source/content state."""
        self.sources: dict[UUID, CatalogManagedSource] = {}
        self.contents: dict[UUID, bytes] = {}

    async def list_sources(
        self,
        *,
        user_id: UUID,
        section_id: UUID,
        kind: CatalogSourceKind,
    ) -> list[CatalogManagedSource]:
        """Возвращает sources matching section/kind."""
        del user_id

        return [
            source
            for source in self.sources.values()
            if source.section_id == section_id and source.kind is kind
        ]

    async def upload_source(
        self,
        *,
        user_id: UUID,
        section_id: UUID,
        kind: CatalogSourceKind,
        file_name: str,
        content: bytes,
    ) -> CatalogManagedSource:
        """Создаёт fake source."""
        del user_id

        now = datetime(2026, 9, 10, 8, 0, tzinfo=UTC)
        source = CatalogManagedSource(
            id=uuid4(),
            section_id=section_id,
            kind=kind,
            original_name=file_name,
            mime_type="application/pdf",
            size_bytes=len(content),
            sha256="a" * 64,
            lifecycle=CatalogSourceLifecycle.ACTIVE,
            created_at=now,
            updated_at=now,
            deleted_at=None,
        )

        self.sources[source.id] = source
        self.contents[source.id] = content
        return source

    async def get_source(
        self,
        *,
        user_id: UUID,
        source_id: UUID,
        kind: CatalogSourceKind,
    ) -> CatalogManagedSource:
        """Возвращает fake source."""
        del user_id

        source = self.sources[source_id]
        assert source.kind is kind
        return source

    async def get_source_content(
        self,
        *,
        user_id: UUID,
        source_id: UUID,
        kind: CatalogSourceKind,
    ) -> CatalogSourceContent:
        """Возвращает fake content."""
        del user_id

        source = self.sources[source_id]
        assert source.kind is kind

        return CatalogSourceContent(
            source_id=source_id,
            file_name=source.original_name,
            mime_type=source.mime_type,
            content=self.contents[source_id],
        )

    async def delete_source(
        self,
        *,
        user_id: UUID,
        source_id: UUID,
        kind: CatalogSourceKind,
    ) -> None:
        """Удаляет fake source."""
        del user_id

        source = self.sources[source_id]
        assert source.kind is kind
        self.sources.pop(source_id)
        self.contents.pop(source_id, None)

    async def aclose(self) -> None:
        """Fake client не имеет network resources."""


def test_managed_sources_require_auth_and_support_content(
    tmp_path: Path,
) -> None:
    """Проверяет auth, upload/list/content/delete public contract."""
    settings = GatewaySettings(
        environment=Environment.TEST,
        log_to_file=False,
        log_root_dir=tmp_path,
        gateway_upload={"max_managed_source_bytes": 1024},
        _env_file=None,
    )

    app = create_app(settings)

    user = AuthUser(
        id=uuid4(),
        email="sources@example.com",
        created_at=datetime(2026, 9, 10, tzinfo=UTC),
    )

    app.state.container.auth_service = FakeAuthServiceClient(user)
    app.state.container.catalog_sources = FakeCatalogSourceServiceClient()

    section_id = uuid4()
    pdf = b"%PDF-1.7\nmanaged-source\n"

    with TestClient(app) as client:
        unauthorized = client.get(
            "/api/v1/catalog/normative-documents",
            params={"section_id": str(section_id)},
        )
        assert unauthorized.status_code == 401

        client.cookies.set(
            settings.session_cookie.name,
            "source-session",
        )

        uploaded = client.post(
            "/api/v1/catalog/normative-documents",
            params={"section_id": str(section_id)},
            headers={
                "X-Source-Filename": quote("СП 1.pdf", safe=""),
                "Content-Type": "application/octet-stream",
            },
            content=pdf,
        )

        assert uploaded.status_code == 201
        assert uploaded.json()["kind"] == "N"
        assert uploaded.json()["original_name"] == "СП 1.pdf"
        assert "storage_key" not in uploaded.json()

        source_id = uploaded.json()["id"]

        listed = client.get(
            "/api/v1/catalog/normative-documents",
            params={"section_id": str(section_id)},
        )

        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()["sources"]] == [source_id]

        content = client.get(f"/api/v1/catalog/normative-documents/{source_id}/content")

        assert content.status_code == 200
        assert content.content == pdf
        assert "filename*=UTF-8''" in content.headers["content-disposition"]

        deleted = client.delete(f"/api/v1/catalog/normative-documents/{source_id}")

        assert deleted.status_code == 204


def test_gateway_rejects_oversized_source_before_downstream(
    tmp_path: Path,
) -> None:
    """Проверяет Gateway memory boundary до Catalog Service call."""
    settings = GatewaySettings(
        environment=Environment.TEST,
        log_to_file=False,
        log_root_dir=tmp_path,
        gateway_upload={"max_managed_source_bytes": 4},
        _env_file=None,
    )

    app = create_app(settings)

    user = AuthUser(
        id=uuid4(),
        email="source-limit@example.com",
        created_at=datetime(2026, 9, 10, tzinfo=UTC),
    )

    app.state.container.auth_service = FakeAuthServiceClient(user)
    app.state.container.catalog_sources = FakeCatalogSourceServiceClient()

    with TestClient(app) as client:
        client.cookies.set(
            settings.session_cookie.name,
            "source-session",
        )

        response = client.post(
            "/api/v1/catalog/user-documents",
            params={"section_id": str(uuid4())},
            headers={
                "X-Source-Filename": "file.pdf",
                "Content-Type": "application/octet-stream",
            },
            content=b"12345",
        )

        assert response.status_code == 400
