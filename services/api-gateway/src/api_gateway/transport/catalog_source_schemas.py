# services/api-gateway/src/api_gateway/transport/catalog_source_schemas.py

"""Public HTTP schemas managed Catalog sources API Gateway."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from api_gateway.application.catalog_sources import (
    CatalogManagedSource,
    CatalogSourceKind,
    CatalogSourceLifecycle,
)


class ManagedSourceResponse(BaseModel):
    """Public safe managed source metadata."""

    model_config = ConfigDict(frozen=True)

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

    @classmethod
    def from_dto(cls, source: CatalogManagedSource) -> "ManagedSourceResponse":
        """Преобразует Gateway DTO в public response."""
        return cls(
            id=source.id,
            section_id=source.section_id,
            kind=source.kind,
            original_name=source.original_name,
            mime_type=source.mime_type,
            size_bytes=source.size_bytes,
            sha256=source.sha256,
            lifecycle=source.lifecycle,
            created_at=source.created_at,
            updated_at=source.updated_at,
            deleted_at=source.deleted_at,
        )


class ManagedSourceListResponse(BaseModel):
    """Public container списка N либо U sources."""

    sources: list[ManagedSourceResponse]
