# services/context-service/src/context_service/domain/search.py

"""Typed search contract временных T/PZ collections."""

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from context_service.domain.models import ContextSourceKind

ContextSemanticRole = Literal["project_context_non_normative"]


@dataclass(frozen=True, slots=True)
class ContextSearchQuery:
    """Owner-scoped typed vector search query одного Project Context."""

    user_id: UUID
    context_id: UUID
    kind: ContextSourceKind
    text: str
    limit: int | None = None
    score_threshold: float | None = None


@dataclass(frozen=True, slots=True)
class ContextSearchHit:
    """Search hit, который явно не является нормативным доказательством N."""

    source_id: UUID
    context_id: UUID
    user_id: UUID
    kind: ContextSourceKind
    source_name: str
    chunk_id: str
    text: str
    score: float
    fingerprint: str
    page_number: int | None
    fragment_index: int | None
    heading: str | None
    char_start: int | None
    char_end: int | None
    semantic_role: ContextSemanticRole = "project_context_non_normative"
