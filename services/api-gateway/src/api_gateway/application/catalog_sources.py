# services/api-gateway/src/api_gateway/application/catalog_sources.py

"""Application port managed Catalog sources для API Gateway."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID


class CatalogSourceKind(StrEnum):
    """Typed N/U discriminator публичного Gateway contract."""

    NORMATIVE = "N"
    USER = "U"


class CatalogSourceLifecycle(StrEnum):
    """Lifecycle managed source, возвращаемый Catalog Service."""

    ACTIVE = "active"
    DELETE_PENDING = "delete_pending"
    CLEANUP_FAILED = "cleanup_failed"
    DELETED = "deleted"


@dataclass(frozen=True, slots=True)
class CatalogManagedSource:
    """Typed Gateway representation managed N/U source metadata."""

    id: UUID
    section_id: UUID
    kind: CatalogSourceKind
    original_name: str
    mime_type: str
    size_bytes: int
    sha256: str
    lifecycle: CatalogSourceLifecycle
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


@dataclass(frozen=True, slots=True)
class CatalogSourceContent:
    """Typed Gateway representation source content response."""

    source_id: UUID
    file_name: str
    mime_type: str
    content: bytes


class CatalogSourceServiceClient(Protocol):
    """Transport-neutral Gateway port managed Catalog source API."""

    async def list_sources(
        self,
        *,
        user_id: UUID,
        section_id: UUID,
        kind: CatalogSourceKind,
    ) -> list[CatalogManagedSource]:
        """Возвращает managed sources одной section."""

    async def upload_source(
        self,
        *,
        user_id: UUID,
        section_id: UUID,
        kind: CatalogSourceKind,
        file_name: str,
        content: bytes,
    ) -> CatalogManagedSource:
        """Загружает managed source через internal Catalog API."""

    async def get_source(
        self,
        *,
        user_id: UUID,
        source_id: UUID,
        kind: CatalogSourceKind,
    ) -> CatalogManagedSource:
        """Возвращает metadata одного managed source."""

    async def get_source_content(
        self,
        *,
        user_id: UUID,
        source_id: UUID,
        kind: CatalogSourceKind,
    ) -> CatalogSourceContent:
        """Возвращает source content."""

    async def delete_source(
        self,
        *,
        user_id: UUID,
        source_id: UUID,
        kind: CatalogSourceKind,
    ) -> None:
        """Удаляет managed source."""

    async def aclose(self) -> None:
        """Закрывает owned HTTP resources."""
