# services/api-gateway/src/api_gateway/application/catalog_service.py

"""Application port Catalog Service для API Gateway."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class CatalogSection:
    """Typed Gateway representation Catalog section."""

    id: UUID
    parent_id: UUID | None
    title: str
    sort_order: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class CatalogSystemPrompt:
    """Typed Gateway representation saved system prompt."""

    prompt: str
    updated_at: datetime | None


class CatalogServiceClient(Protocol):
    """Transport-neutral Gateway port Catalog Service."""

    async def list_sections(self, *, user_id: UUID) -> list[CatalogSection]:
        """Возвращает sections пользователя."""

    async def create_section(
        self,
        *,
        user_id: UUID,
        title: str,
        parent_id: UUID | None,
        sort_order: int,
    ) -> CatalogSection:
        """Создаёт user-owned section."""

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
        """Изменяет section."""

    async def delete_section(
        self,
        *,
        user_id: UUID,
        section_id: UUID,
    ) -> None:
        """Удаляет section."""

    async def get_system_prompt(
        self,
        *,
        user_id: UUID,
    ) -> CatalogSystemPrompt:
        """Возвращает saved prompt."""

    async def save_system_prompt(
        self,
        *,
        user_id: UUID,
        prompt: str,
    ) -> CatalogSystemPrompt:
        """Сохраняет prompt."""

    async def aclose(self) -> None:
        """Закрывает owned HTTP resources."""
