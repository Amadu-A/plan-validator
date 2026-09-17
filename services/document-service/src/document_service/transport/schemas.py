# services/document-service/src/document_service/transport/schemas.py

"""Pydantic HTTP schemas Document Service."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from document_service.application.dto import ProcessedPage
from document_service.domain.models import ProjectDocument


class DocumentResponse(BaseModel):
    """Public-safe internal Project Document metadata."""

    id: UUID
    user_id: UUID
    original_name: str
    mime_type: str
    size_bytes: int
    sha256: str
    page_count: int
    selected_pages: list[int]
    lifecycle: str
    created_at: datetime
    updated_at: datetime
    expires_at: datetime

    @classmethod
    def from_domain(cls, document: ProjectDocument) -> "DocumentResponse":
        """Преобразует domain model без storage key."""
        return cls(
            id=document.id,
            user_id=document.user_id,
            original_name=document.original_name,
            mime_type=document.mime_type,
            size_bytes=document.size_bytes,
            sha256=document.sha256,
            page_count=document.page_count,
            selected_pages=list(document.selected_pages),
            lifecycle=document.lifecycle.value,
            created_at=document.created_at,
            updated_at=document.updated_at,
            expires_at=document.expires_at,
        )


class SelectPagesRequest(BaseModel):
    """Bounded page selection request."""

    page_numbers: list[int] = Field(min_length=1, max_length=4096)


class ProcessPagesRequest(BaseModel):
    """Optional explicit page subset."""

    page_numbers: list[int] | None = None


class ProcessPagesResponse(BaseModel):
    """Parser-neutral page processing response."""

    pages: list[dict[str, object]]


def page_to_payload(page: ProcessedPage) -> dict[str, object]:
    """Преобразует application DTO в JSON-safe payload."""
    fragments = []
    for fragment in page.fragments:
        fragments.append(
            {
                "fragment_id": fragment.fragment_id,
                "page_number": fragment.page_number,
                "modality": fragment.modality.value,
                "text_origin": fragment.text_origin.value,
                "text": fragment.text,
                "image_artifact_id": fragment.image_artifact_id,
                "bbox": {
                    "x0": fragment.bbox.x0,
                    "y0": fragment.bbox.y0,
                    "x1": fragment.bbox.x1,
                    "y1": fragment.bbox.y1,
                },
                "ocr_confidence": fragment.ocr_confidence,
            }
        )
    return {
        "page_number": page.page_number,
        "render_artifact_id": page.render_artifact_id,
        "native_text_chars": page.native_text_chars,
        "visual_area_ratio": page.visual_area_ratio,
        "used_ocr": page.used_ocr,
        "fragments": fragments,
    }
