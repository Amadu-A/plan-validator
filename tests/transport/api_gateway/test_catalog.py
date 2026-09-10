# tests/transport/api_gateway/test_catalog.py

"""Transport tests authenticated public Catalog facade Gateway."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from api_gateway.application.auth_service import AuthUser
from api_gateway.application.catalog_service import (
    CatalogSection,
    CatalogSystemPrompt,
)
from api_gateway.core.settings import GatewaySettings
from api_gateway.transport.app import create_app
from fastapi.testclient import TestClient
from plan_validator_common.settings import Environment


class FakeAuthServiceClient:
    """Auth double для Catalog transport tests."""

    def __init__(self, user: AuthUser) -> None:
        """Сохраняет authenticated user."""
        self.user = user

    async def get_current_user(
        self,
        *,
        session_token: str,
    ) -> AuthUser:
        """Разрешает известный test token."""
        assert session_token == "catalog-session"
        return self.user

    async def aclose(self) -> None:
        """Fake client не имеет resources."""

    async def register_user(self, **kwargs: object) -> object:
        """Недоступен в Catalog transport test."""
        del kwargs
        raise AssertionError("Unexpected registration")

    async def login_user(self, **kwargs: object) -> object:
        """Недоступен в Catalog transport test."""
        del kwargs
        raise AssertionError("Unexpected login")

    async def logout_session(self, **kwargs: object) -> None:
        """Недоступен в Catalog transport test."""
        del kwargs
        raise AssertionError("Unexpected logout")


class FakeCatalogServiceClient:
    """In-memory Catalog client transport double."""

    def __init__(self) -> None:
        """Создаёт mutable test state."""
        self.sections: dict[UUID, CatalogSection] = {}
        self.prompt = CatalogSystemPrompt(
            prompt="",
            updated_at=None,
        )

    async def list_sections(
        self,
        *,
        user_id: UUID,
    ) -> list[CatalogSection]:
        """Возвращает fake sections."""
        del user_id
        return list(self.sections.values())

    async def create_section(
        self,
        *,
        user_id: UUID,
        title: str,
        parent_id: UUID | None,
        sort_order: int,
    ) -> CatalogSection:
        """Создаёт fake section."""
        del user_id

        section = CatalogSection(
            id=uuid4(),
            parent_id=parent_id,
            title=title,
            sort_order=sort_order,
            created_at=datetime(2026, 9, 10, tzinfo=UTC),
            updated_at=datetime(2026, 9, 10, tzinfo=UTC),
        )

        self.sections[section.id] = section
        return section

    async def update_section(
        self,
        *,
        user_id: UUID,
        section_id: UUID,
        title: str | None,
        parent_id: UUID | None,
        parent_id_supplied: bool,
        sort_order: int | None,
    ) -> CatalogSection:
        """Обновляет fake section."""
        del user_id

        current = self.sections[section_id]

        updated = CatalogSection(
            id=current.id,
            parent_id=(parent_id if parent_id_supplied else current.parent_id),
            title=title if title is not None else current.title,
            sort_order=(sort_order if sort_order is not None else current.sort_order),
            created_at=current.created_at,
            updated_at=current.updated_at,
        )

        self.sections[section_id] = updated
        return updated

    async def delete_section(
        self,
        *,
        user_id: UUID,
        section_id: UUID,
    ) -> None:
        """Удаляет fake section."""
        del user_id
        self.sections.pop(section_id)

    async def get_system_prompt(
        self,
        *,
        user_id: UUID,
    ) -> CatalogSystemPrompt:
        """Возвращает fake prompt."""
        del user_id
        return self.prompt

    async def save_system_prompt(
        self,
        *,
        user_id: UUID,
        prompt: str,
    ) -> CatalogSystemPrompt:
        """Сохраняет fake prompt."""
        del user_id

        self.prompt = CatalogSystemPrompt(
            prompt=prompt,
            updated_at=datetime(2026, 9, 10, tzinfo=UTC),
        )
        return self.prompt

    async def aclose(self) -> None:
        """Fake client не имеет network resources."""


def test_catalog_requires_authentication_and_supports_crud(
    tmp_path: Path,
) -> None:
    """Проверяет public Catalog auth boundary и basic CRUD."""
    settings = GatewaySettings(
        environment=Environment.TEST,
        log_to_file=False,
        log_root_dir=tmp_path,
        _env_file=None,
    )

    app = create_app(settings)

    user = AuthUser(
        id=uuid4(),
        email="catalog@example.com",
        created_at=datetime(2026, 9, 10, tzinfo=UTC),
    )

    app.state.container.auth_service = FakeAuthServiceClient(user)
    app.state.container.catalog_service = FakeCatalogServiceClient()

    with TestClient(app) as client:
        unauthorized = client.get("/api/v1/catalog/sections")
        assert unauthorized.status_code == 401

        client.cookies.set(
            settings.session_cookie.name,
            "catalog-session",
        )

        created = client.post(
            "/api/v1/catalog/sections",
            json={
                "title": "Нормативные документы",
                "sort_order": 0,
            },
        )

        assert created.status_code == 201

        section_id = created.json()["id"]

        listed = client.get("/api/v1/catalog/sections")
        assert listed.status_code == 200
        assert len(listed.json()["sections"]) == 1

        renamed = client.patch(
            f"/api/v1/catalog/sections/{section_id}",
            json={"title": "Нормативная база"},
        )

        assert renamed.status_code == 200
        assert renamed.json()["title"] == "Нормативная база"

        prompt = client.put(
            "/api/v1/catalog/system-prompt",
            json={"prompt": "Проверяй строго."},
        )

        assert prompt.status_code == 200
        assert prompt.json()["prompt"] == "Проверяй строго."

        deleted = client.delete(f"/api/v1/catalog/sections/{section_id}")

        assert deleted.status_code == 204
