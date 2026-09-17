# services/document-service/src/document_service/domain/models.py

"""Domain модели Project Document и parser-neutral multimodal fragments."""

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from document_service.domain.exceptions import DocumentValidationError


class DocumentLifecycle(StrEnum):
    """Lifecycle основного project document."""

    ACTIVE = "active"
    DELETE_PENDING = "delete_pending"
    DELETED = "deleted"


class ContentModality(StrEnum):
    """Семантическая modality нормализованного fragment."""

    TEXT = "text"
    IMAGE = "image"
    MIXED = "mixed"


class TextOrigin(StrEnum):
    """Происхождение text для аудита source/generated content."""

    NATIVE = "native"
    OCR = "ocr"
    CAPTION = "caption"
    GENERATED = "generated"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class BoundingBox:
    """Normalized bbox 0..1 относительно page."""

    x0: float
    y0: float
    x1: float
    y1: float

    def __post_init__(self) -> None:
        """Проверяет geometry и normalized range."""
        values = (self.x0, self.y0, self.x1, self.y1)
        if any(value < 0.0 or value > 1.0 for value in values):
            raise DocumentValidationError("Bounding box must be normalized to 0..1")
        if self.x1 <= self.x0 or self.y1 <= self.y0:
            raise DocumentValidationError("Bounding box geometry is invalid")


@dataclass(frozen=True, slots=True)
class NormalizedContentFragment:
    """Parser-neutral unit для дальнейшего text/image/mixed analysis."""

    fragment_id: str
    page_number: int
    modality: ContentModality
    text_origin: TextOrigin
    text: str | None
    image_artifact_id: str | None
    bbox: BoundingBox
    ocr_confidence: float | None = None

    def __post_init__(self) -> None:
        """Защищает modality/text-origin invariants."""
        if not self.fragment_id.strip():
            raise DocumentValidationError("Fragment id must not be empty")
        if self.page_number < 1:
            raise DocumentValidationError("Page number must be positive")
        if self.modality is ContentModality.TEXT and not (self.text or "").strip():
            raise DocumentValidationError("Text fragment requires text")
        if self.modality is ContentModality.IMAGE and not self.image_artifact_id:
            raise DocumentValidationError("Image fragment requires image artifact")
        if self.text_origin is TextOrigin.NONE and self.text:
            raise DocumentValidationError("Text origin NONE cannot contain text")
        if self.ocr_confidence is not None and not 0.0 <= self.ocr_confidence <= 100.0:
            raise DocumentValidationError("OCR confidence must be 0..100")


@dataclass(frozen=True, slots=True)
class ProjectDocument:
    """Owner-scoped main project PDF metadata."""

    id: UUID
    user_id: UUID
    original_name: str
    storage_key: str
    mime_type: str
    size_bytes: int
    sha256: str
    page_count: int
    selected_pages: tuple[int, ...]
    lifecycle: DocumentLifecycle
    cleanup_error: str | None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime

    def select_pages(
        self,
        *,
        page_numbers: tuple[int, ...],
        changed_at: datetime,
    ) -> "ProjectDocument":
        """Сохраняет уникальный ordered page selection внутри bounds."""
        if self.lifecycle is not DocumentLifecycle.ACTIVE:
            raise DocumentValidationError("Only active document can change page selection")
        normalized = tuple(sorted(set(page_numbers)))
        if not normalized:
            raise DocumentValidationError("At least one page must be selected")
        if normalized[0] < 1 or normalized[-1] > self.page_count:
            raise DocumentValidationError("Selected page is outside document bounds")
        return replace(self, selected_pages=normalized, updated_at=changed_at)

    def request_delete(self, *, changed_at: datetime) -> "ProjectDocument":
        """Фиксирует retryable logical delete intent."""
        if self.lifecycle is DocumentLifecycle.DELETED:
            return self
        return replace(
            self,
            lifecycle=DocumentLifecycle.DELETE_PENDING,
            cleanup_error=None,
            updated_at=changed_at,
        )

    def mark_deleted(self, *, changed_at: datetime) -> "ProjectDocument":
        """Подтверждает physical cleanup."""
        return replace(
            self,
            lifecycle=DocumentLifecycle.DELETED,
            cleanup_error=None,
            updated_at=changed_at,
        )

    def mark_cleanup_failed(
        self,
        *,
        changed_at: datetime,
        error_message: str,
    ) -> "ProjectDocument":
        """Сохраняет retryable cleanup failure."""
        return replace(
            self,
            lifecycle=DocumentLifecycle.DELETE_PENDING,
            cleanup_error=error_message[:1000],
            updated_at=changed_at,
        )
