# services/document-service/src/document_service/domain/__init__.py

"""Domain contracts Document Service."""

from document_service.domain.models import (
    BoundingBox,
    ContentModality,
    DocumentLifecycle,
    NormalizedContentFragment,
    ProjectDocument,
    TextOrigin,
)

__all__ = [
    "BoundingBox",
    "ContentModality",
    "DocumentLifecycle",
    "NormalizedContentFragment",
    "ProjectDocument",
    "TextOrigin",
]
