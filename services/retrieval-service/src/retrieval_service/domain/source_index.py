# services/retrieval-service/src/retrieval_service/domain/source_index.py

"""Domain model persistent N/U source indexing lifecycle."""

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from uuid import NAMESPACE_URL, UUID, uuid5

from retrieval_service.domain.exceptions import RetrievalValidationError


class SourceKind(StrEnum):
    """Поддерживаемые persistent evidence source types Stage 9."""

    NORMATIVE = "N"
    USER = "U"


class SourceIndexState(StrEnum):
    """Lifecycle managed source внутри Retrieval registry."""

    AWAITING_CHUNKS = "awaiting_chunks"
    INDEXED = "indexed"
    DELETED = "deleted"


@dataclass(frozen=True, slots=True)
class ManagedSourceIndex:
    """Retrieval-owned metadata/fingerprint одного Catalog N/U source."""

    source_id: UUID
    user_id: UUID
    section_id: UUID
    kind: SourceKind
    original_name: str
    mime_type: str
    source_sha256: str
    state: SourceIndexState
    active_fingerprint: str | None
    model_name: str | None
    vector_dimension: int | None
    chunk_count: int
    last_error: str | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None

    def mark_indexed(
        self,
        *,
        fingerprint: str,
        model_name: str,
        vector_dimension: int,
        chunk_count: int,
        changed_at: datetime,
    ) -> "ManagedSourceIndex":
        """Атомарно переключает search-visible active fingerprint."""
        return replace(
            self,
            state=SourceIndexState.INDEXED,
            active_fingerprint=fingerprint,
            model_name=model_name,
            vector_dimension=vector_dimension,
            chunk_count=chunk_count,
            last_error=None,
            updated_at=changed_at,
            deleted_at=None,
        )

    def mark_deleted(self, *, changed_at: datetime) -> "ManagedSourceIndex":
        """Мгновенно исключает source из search registry перед Qdrant cleanup."""
        return replace(
            self,
            state=SourceIndexState.DELETED,
            active_fingerprint=None,
            chunk_count=0,
            last_error=None,
            updated_at=changed_at,
            deleted_at=changed_at,
        )


@dataclass(frozen=True, slots=True)
class NormalizedChunk:
    """Нормализованный фрагмент, который Stage 11 сможет производить из документа."""

    chunk_id: str
    text: str
    page_number: int | None = None
    fragment_index: int | None = None
    heading: str | None = None
    char_start: int | None = None
    char_end: int | None = None

    def validate(self, *, max_text_chars: int) -> None:
        """Проверяет bounded text и locator metadata без знания file parser."""
        if not self.chunk_id.strip() or len(self.chunk_id) > 128:
            raise RetrievalValidationError("Chunk id must contain 1..128 characters")

        if not self.text.strip():
            raise RetrievalValidationError("Chunk text must not be empty")

        if len(self.text) > max_text_chars:
            raise RetrievalValidationError(f"Chunk text exceeds {max_text_chars} character limit")

        if self.page_number is not None and self.page_number < 1:
            raise RetrievalValidationError("Page number must be positive")

        if self.fragment_index is not None and self.fragment_index < 0:
            raise RetrievalValidationError("Fragment index must be non-negative")

        if self.heading is not None and len(self.heading) > 500:
            raise RetrievalValidationError("Chunk heading is too long")

        if self.char_start is not None and self.char_start < 0:
            raise RetrievalValidationError("char_start must be non-negative")

        if self.char_end is not None and self.char_end < 0:
            raise RetrievalValidationError("char_end must be non-negative")

        if (
            self.char_start is not None
            and self.char_end is not None
            and self.char_end < self.char_start
        ):
            raise RetrievalValidationError("char_end must not be before char_start")


@dataclass(frozen=True, slots=True)
class IndexSourceJob:
    """Durable normalized source indexing command."""

    job_id: UUID
    source_id: UUID
    source_sha256: str
    chunks: tuple[NormalizedChunk, ...]
    correlation_id: str


@dataclass(frozen=True, slots=True)
class SourceIndexResult:
    """Результат idempotent source reindex lifecycle."""

    source_id: UUID
    fingerprint: str
    chunk_count: int
    reused: bool


def validate_chunks(
    chunks: tuple[NormalizedChunk, ...],
    *,
    max_chunks: int,
    max_text_chars: int,
) -> None:
    """Проверяет размер source batch и уникальность chunk identifiers."""
    if not chunks:
        raise RetrievalValidationError("Source index job must contain chunks")

    if len(chunks) > max_chunks:
        raise RetrievalValidationError(f"Source index job exceeds {max_chunks} chunk limit")

    identifiers: set[str] = set()

    for chunk in chunks:
        chunk.validate(max_text_chars=max_text_chars)
        normalized_id = chunk.chunk_id.strip()

        if normalized_id in identifiers:
            raise RetrievalValidationError(f"Duplicate chunk id: {normalized_id}")

        identifiers.add(normalized_id)


def calculate_index_fingerprint(
    *,
    source_sha256: str,
    model_name: str,
    vector_dimension: int,
    chunks: tuple[NormalizedChunk, ...],
) -> str:
    """Строит deterministic fingerprint source bytes + model identity + chunks."""
    payload = {
        "schema_version": 1,
        "source_sha256": source_sha256,
        "model_name": model_name,
        "vector_dimension": vector_dimension,
        "chunks": [
            {
                "chunk_id": chunk.chunk_id,
                "text": chunk.text,
                "page_number": chunk.page_number,
                "fragment_index": chunk.fragment_index,
                "heading": chunk.heading,
                "char_start": chunk.char_start,
                "char_end": chunk.char_end,
            }
            for chunk in sorted(chunks, key=lambda item: item.chunk_id)
        ],
    }
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return hashlib.sha256(serialized).hexdigest()


def build_version_key(*, source_id: UUID, fingerprint: str) -> str:
    """Создаёт keyword key одной search-visible source generation."""
    return f"{source_id}:{fingerprint}"


def build_point_id(
    *,
    source_id: UUID,
    fingerprint: str,
    chunk_id: str,
) -> UUID:
    """Создаёт deterministic Qdrant point UUID для idempotent upsert."""
    return uuid5(
        NAMESPACE_URL,
        f"plan-validator:{source_id}:{fingerprint}:{chunk_id}",
    )
