# services/document-service/src/document_service/application/dto.py

"""Transport-neutral processing DTO Document Service."""

from dataclasses import dataclass

from document_service.domain.models import (
    BoundingBox,
    ContentModality,
    NormalizedContentFragment,
    TextOrigin,
)


@dataclass(frozen=True, slots=True)
class OcrFragment:
    """OCR line в pixel coordinates rendered page."""

    text: str
    left: int
    top: int
    width: int
    height: int
    confidence: float


@dataclass(frozen=True, slots=True)
class PdfInspection:
    """Минимальная metadata проверенного PDF."""

    page_count: int


@dataclass(frozen=True, slots=True)
class DraftFragment:
    """Fragment до присвоения persistent render artifact reference."""

    fragment_id: str
    page_number: int
    modality: ContentModality
    text_origin: TextOrigin
    text: str | None
    bbox: BoundingBox
    ocr_confidence: float | None = None


@dataclass(frozen=True, slots=True)
class ProcessedPageDraft:
    """Extraction/render одной страницы до storage."""

    page_number: int
    render_png: bytes
    fragments: tuple[DraftFragment, ...]
    native_text_chars: int
    visual_area_ratio: float
    used_ocr: bool


@dataclass(frozen=True, slots=True)
class ProcessedPage:
    """Persisted page artifacts для downstream Analysis Service."""

    page_number: int
    render_artifact_id: str
    fragments: tuple[NormalizedContentFragment, ...]
    native_text_chars: int
    visual_area_ratio: float
    used_ocr: bool
