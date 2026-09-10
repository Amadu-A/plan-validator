# services/catalog-service/src/catalog_service/transport/source_schemas.py

"""Internal HTTP schemas managed N/U source API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from catalog_service.domain.source import ManagedSource, SourceKind, SourceLifecycle


class ManagedSourceResponse(BaseModel):
    """Safe transport representation managed source без storage key."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    section_id: UUID
    kind: SourceKind
    original_name: str
    mime_type: str
    size_bytes: int
    sha256: str
    lifecycle: SourceLifecycle
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None

    @classmethod
    def from_domain(cls, source: ManagedSource) -> "ManagedSourceResponse":
        """Преобразует Domain ManagedSource в safe HTTP schema."""
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
    """Container списка managed sources."""

    sources: list[ManagedSourceResponse]
