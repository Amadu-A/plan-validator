# services/catalog-service/src/catalog_service/domain/source.py

"""Domain entities managed N/U sources и transactional outbox."""

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from catalog_service.domain.exceptions import ManagedSourceLifecycleConflictError


class SourceKind(StrEnum):
    """Семантический тип persistent managed source."""

    NORMATIVE = "N"
    USER = "U"


class SourceLifecycle(StrEnum):
    """Lifecycle физического managed source."""

    ACTIVE = "active"
    DELETE_PENDING = "delete_pending"
    CLEANUP_FAILED = "cleanup_failed"
    DELETED = "deleted"


SOURCE_UPLOADED_EVENT = "catalog.source.uploaded.v1"
SOURCE_DELETE_REQUESTED_EVENT = "catalog.source.delete_requested.v1"

SourceEventValue = str | int | None


@dataclass(frozen=True, slots=True)
class ManagedSource:
    """Persistent metadata одного нормативного или пользовательского документа."""

    id: UUID
    user_id: UUID
    section_id: UUID
    kind: SourceKind
    original_name: str
    storage_key: str
    mime_type: str
    size_bytes: int
    sha256: str
    lifecycle: SourceLifecycle
    last_cleanup_error: str | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None

    def mark_delete_pending(self, *, changed_at: datetime) -> "ManagedSource":
        """Переводит active source в durable delete_pending."""
        if self.lifecycle is SourceLifecycle.DELETED:
            return self

        if self.lifecycle not in {
            SourceLifecycle.ACTIVE,
            SourceLifecycle.CLEANUP_FAILED,
            SourceLifecycle.DELETE_PENDING,
        }:
            raise ManagedSourceLifecycleConflictError(
                f"Unsupported source lifecycle transition from {self.lifecycle.value}"
            )

        return replace(
            self,
            lifecycle=SourceLifecycle.DELETE_PENDING,
            last_cleanup_error=None,
            updated_at=changed_at,
        )

    def mark_cleanup_failed(
        self,
        *,
        changed_at: datetime,
        error_message: str,
    ) -> "ManagedSource":
        """Фиксирует сбой удаления физического объекта."""
        if self.lifecycle is SourceLifecycle.DELETED:
            return self

        return replace(
            self,
            lifecycle=SourceLifecycle.CLEANUP_FAILED,
            last_cleanup_error=error_message[:2000],
            updated_at=changed_at,
        )

    def mark_deleted(self, *, changed_at: datetime) -> "ManagedSource":
        """Фиксирует подтверждённое отсутствие физического объекта."""
        return replace(
            self,
            lifecycle=SourceLifecycle.DELETED,
            last_cleanup_error=None,
            updated_at=changed_at,
            deleted_at=changed_at,
        )


@dataclass(frozen=True, slots=True)
class SourceOutboxMessage:
    """Durable event, создаваемый в одной transaction с source metadata."""

    id: UUID
    source_id: UUID
    event_type: str
    payload: dict[str, SourceEventValue]
    created_at: datetime
    published_at: datetime | None
    attempt_count: int
    last_error: str | None


def build_source_event_payload(source: ManagedSource) -> dict[str, SourceEventValue]:
    """Создаёт storage-neutral payload для будущего indexing consumer."""
    return {
        "source_id": str(source.id),
        "user_id": str(source.user_id),
        "section_id": str(source.section_id),
        "kind": source.kind.value,
        "original_name": source.original_name,
        "mime_type": source.mime_type,
        "size_bytes": source.size_bytes,
        "sha256": source.sha256,
        "lifecycle": source.lifecycle.value,
    }
