# tests/unit/document_service/test_domain.py

"""Unit tests multimodal domain invariants Document Service."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from document_service.domain.exceptions import DocumentValidationError
from document_service.domain.models import (
    BoundingBox,
    ContentModality,
    DocumentLifecycle,
    ProjectDocument,
    TextOrigin,
)


def test_bbox_rejects_outside_normalized_range() -> None:
    """BBox не может выходить за page coordinate contract."""
    with pytest.raises(DocumentValidationError):
        BoundingBox(-0.1, 0.0, 1.0, 1.0)


def test_selection_is_sorted_unique_and_bounded() -> None:
    """Page selection не хранит duplicates и проверяет page count."""
    now = datetime(2026, 9, 16, tzinfo=UTC)
    document = ProjectDocument(
        id=uuid4(),
        user_id=uuid4(),
        original_name="project.pdf",
        storage_key="x",
        mime_type="application/pdf",
        size_bytes=1,
        sha256="f" * 64,
        page_count=5,
        selected_pages=(1, 2, 3, 4, 5),
        lifecycle=DocumentLifecycle.ACTIVE,
        cleanup_error=None,
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(days=30),
    )
    assert document.select_pages(page_numbers=(3, 1, 3), changed_at=now).selected_pages == (1, 3)
    with pytest.raises(DocumentValidationError):
        document.select_pages(page_numbers=(6,), changed_at=now)


def test_generated_origin_is_distinct() -> None:
    """Generated text нельзя спутать с source text."""
    assert TextOrigin.GENERATED.value == "generated"
    assert ContentModality.MIXED.value == "mixed"
