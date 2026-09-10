# services/retrieval-service/src/retrieval_service/domain/search.py

"""Domain contracts typed N/U vector search."""

from dataclasses import dataclass
from uuid import UUID

from retrieval_service.domain.exceptions import RetrievalValidationError
from retrieval_service.domain.source_index import SourceKind


@dataclass(frozen=True, slots=True)
class SearchQuery:
    """Typed exact-filter search request одного user corpus."""

    user_id: UUID
    kind: SourceKind
    text: str
    section_ids: tuple[UUID, ...] = ()
    source_ids: tuple[UUID, ...] = ()
    limit: int = 10
    score_threshold: float = 0.3

    def validate(self, *, max_limit: int) -> None:
        """Проверяет query bounds и не позволяет untyped cross-user search."""
        if not self.text.strip():
            raise RetrievalValidationError("Search query must not be empty")

        if self.limit < 1 or self.limit > max_limit:
            raise RetrievalValidationError(f"Search limit must be within 1..{max_limit}")

        if self.score_threshold < -1.0 or self.score_threshold > 1.0:
            raise RetrievalValidationError("Score threshold must be within -1..1")

        if len(self.section_ids) > 100 or len(self.source_ids) > 100:
            raise RetrievalValidationError("Exact filter list exceeds 100 identifiers")


@dataclass(frozen=True, slots=True)
class SearchHit:
    """Один typed retrieval fragment со stable Catalog source identity."""

    source_id: UUID
    user_id: UUID
    section_id: UUID
    kind: SourceKind
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
