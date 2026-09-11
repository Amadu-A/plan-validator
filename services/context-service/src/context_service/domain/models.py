# services/context-service/src/context_service/domain/models.py

"""Domain models temporary T/PZ contexts и recoverable indexing jobs."""

import json
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from uuid import UUID

from context_service.domain.exceptions import (
    ContextIndexJobConflictError,
    ContextValidationError,
    ProjectContextConflictError,
)


class ContextSourceKind(StrEnum):
    """Semantic type временного project context source."""

    TECHNICAL_ASSIGNMENT = "T"
    PROJECT_NOTE = "PZ"


class ProjectContextState(StrEnum):
    """Lifecycle временного analysis context."""

    ACTIVE = "active"
    CLEANUP_PENDING = "cleanup_pending"
    CLEANED = "cleaned"


class ContextSourceState(StrEnum):
    """Lifecycle normalized T/PZ source."""

    AWAITING_CHUNKS = "awaiting_chunks"
    INDEXED = "indexed"
    DELETED = "deleted"


class ContextIndexJobState(StrEnum):
    """Persistent lifecycle expensive Context indexing job."""

    QUEUED = "queued"
    RUNNING = "running"
    RETRY_WAIT = "retry_wait"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"


TERMINAL_JOB_STATES = frozenset(
    {
        ContextIndexJobState.SUCCEEDED,
        ContextIndexJobState.FAILED,
        ContextIndexJobState.CANCELED,
    }
)


@dataclass(frozen=True, slots=True)
class NormalizedContextChunk:
    """Parser-neutral normalized fragment T либо PZ."""

    chunk_id: str
    text: str
    page_number: int | None = None
    fragment_index: int | None = None
    heading: str | None = None
    char_start: int | None = None
    char_end: int | None = None

    def validate(self, *, max_text_chars: int) -> None:
        """Проверяет bounded normalized chunk contract."""
        chunk_id = self.chunk_id.strip()
        text = self.text.strip()

        if not chunk_id:
            raise ContextValidationError("Chunk id must not be empty")

        if len(chunk_id) > 128:
            raise ContextValidationError("Chunk id must not exceed 128 characters")

        if not text:
            raise ContextValidationError("Chunk text must not be empty")

        if len(text) > max_text_chars:
            raise ContextValidationError(f"Chunk text must not exceed {max_text_chars} characters")

        if self.page_number is not None and self.page_number < 1:
            raise ContextValidationError("Page number must be positive")

        if self.fragment_index is not None and self.fragment_index < 0:
            raise ContextValidationError("Fragment index must not be negative")

        if self.char_start is not None and self.char_start < 0:
            raise ContextValidationError("char_start must not be negative")

        if self.char_end is not None and self.char_end < 0:
            raise ContextValidationError("char_end must not be negative")

        if (
            self.char_start is not None
            and self.char_end is not None
            and self.char_end < self.char_start
        ):
            raise ContextValidationError("char_end must not be before char_start")

    def to_payload(self) -> dict[str, object]:
        """Преобразует normalized chunk в JSON-safe persistence payload."""
        return {
            "chunk_id": self.chunk_id,
            "text": self.text,
            "page_number": self.page_number,
            "fragment_index": self.fragment_index,
            "heading": self.heading,
            "char_start": self.char_start,
            "char_end": self.char_end,
        }

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, object],
    ) -> "NormalizedContextChunk":
        """Восстанавливает immutable chunk из persistence payload."""
        return cls(
            chunk_id=str(payload["chunk_id"]),
            text=str(payload["text"]),
            page_number=_optional_int(payload.get("page_number")),
            fragment_index=_optional_int(payload.get("fragment_index")),
            heading=_optional_str(payload.get("heading")),
            char_start=_optional_int(payload.get("char_start")),
            char_end=_optional_int(payload.get("char_end")),
        )


@dataclass(frozen=True, slots=True)
class ProjectContext:
    """Временный owner-scoped context одной будущей проверки."""

    id: UUID
    user_id: UUID
    state: ProjectContextState
    cleanup_error: str | None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime

    def touch(
        self,
        *,
        changed_at: datetime,
        ttl: timedelta,
    ) -> "ProjectContext":
        """Продлевает TTL только активного context."""
        if self.state is not ProjectContextState.ACTIVE:
            raise ProjectContextConflictError("Project Context is not active")

        return replace(
            self,
            updated_at=changed_at,
            expires_at=changed_at + ttl,
            cleanup_error=None,
        )

    def request_cleanup(
        self,
        *,
        changed_at: datetime,
    ) -> "ProjectContext":
        """Делает context невидимым до physical cleanup."""
        if self.state is ProjectContextState.CLEANED:
            return self

        return replace(
            self,
            state=ProjectContextState.CLEANUP_PENDING,
            updated_at=changed_at,
            cleanup_error=None,
        )

    def mark_cleanup_failed(
        self,
        *,
        changed_at: datetime,
        error_message: str,
    ) -> "ProjectContext":
        """Оставляет cleanup retryable после infrastructure failure."""
        return replace(
            self,
            state=ProjectContextState.CLEANUP_PENDING,
            updated_at=changed_at,
            cleanup_error=error_message[:2000],
        )

    def mark_cleaned(
        self,
        *,
        changed_at: datetime,
    ) -> "ProjectContext":
        """Фиксирует завершённый physical cleanup."""
        return replace(
            self,
            state=ProjectContextState.CLEANED,
            updated_at=changed_at,
            cleanup_error=None,
        )


@dataclass(frozen=True, slots=True)
class ContextSource:
    """Metadata одного временного T либо PZ source."""

    id: UUID
    context_id: UUID
    user_id: UUID
    kind: ContextSourceKind
    original_name: str
    source_sha256: str
    state: ContextSourceState
    active_fingerprint: str | None
    chunk_count: int
    created_at: datetime
    updated_at: datetime

    def mark_indexed(
        self,
        *,
        fingerprint: str,
        chunk_count: int,
        changed_at: datetime,
    ) -> "ContextSource":
        """Активирует новую vector generation source."""
        if self.state is ContextSourceState.DELETED:
            raise ProjectContextConflictError("Deleted Context source cannot be indexed")

        return replace(
            self,
            state=ContextSourceState.INDEXED,
            active_fingerprint=fingerprint,
            chunk_count=chunk_count,
            updated_at=changed_at,
        )

    def mark_deleted(
        self,
        *,
        changed_at: datetime,
    ) -> "ContextSource":
        """Исключает source из дальнейшего indexing/search."""
        return replace(
            self,
            state=ContextSourceState.DELETED,
            active_fingerprint=None,
            chunk_count=0,
            updated_at=changed_at,
        )


@dataclass(frozen=True, slots=True)
class ContextIndexJob:
    """Persistent execution state одного expensive T/PZ indexing request."""

    id: UUID
    context_id: UUID
    source_id: UUID
    user_id: UUID
    kind: ContextSourceKind
    fingerprint: str
    correlation_id: str
    chunks: tuple[NormalizedContextChunk, ...]
    state: ContextIndexJobState
    attempt: int
    max_attempts: int
    deadline_at: datetime
    next_attempt_at: datetime | None
    dispatched_at: datetime | None
    lease_owner: str | None
    lease_expires_at: datetime | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime

    @property
    def is_terminal(self) -> bool:
        """Возвращает True для состояний без последующего выполнения."""
        return self.state in TERMINAL_JOB_STATES

    def claim(
        self,
        *,
        worker_id: str,
        changed_at: datetime,
        lease_seconds: int,
    ) -> tuple["ContextIndexJob", bool]:
        """Атомарно определяет возможность выполнения и создаёт process lease."""
        if self.is_terminal:
            return self, False

        if changed_at >= self.deadline_at:
            return self.fail(
                changed_at=changed_at,
                error_message="job_deadline_exceeded",
            ), False

        if (
            self.state is ContextIndexJobState.RUNNING
            and self.lease_expires_at is not None
            and self.lease_expires_at > changed_at
        ):
            return self, False

        if (
            self.state is ContextIndexJobState.RETRY_WAIT
            and self.next_attempt_at is not None
            and self.next_attempt_at > changed_at
        ):
            return self, False

        if self.attempt >= self.max_attempts:
            return self.fail(
                changed_at=changed_at,
                error_message="job_attempt_limit_exceeded",
            ), False

        claimed = replace(
            self,
            state=ContextIndexJobState.RUNNING,
            attempt=self.attempt + 1,
            next_attempt_at=None,
            lease_owner=worker_id,
            lease_expires_at=changed_at + timedelta(seconds=lease_seconds),
            updated_at=changed_at,
        )
        return claimed, True

    def heartbeat(
        self,
        *,
        worker_id: str,
        changed_at: datetime,
        lease_seconds: int,
    ) -> "ContextIndexJob":
        """Продлевает process-owned lease активного job."""
        if self.state is not ContextIndexJobState.RUNNING:
            raise ContextIndexJobConflictError("Only running job can heartbeat")

        if self.lease_owner != worker_id:
            raise ContextIndexJobConflictError("Index job lease belongs to another worker")

        return replace(
            self,
            lease_expires_at=changed_at + timedelta(seconds=lease_seconds),
            updated_at=changed_at,
        )

    def succeed(
        self,
        *,
        changed_at: datetime,
    ) -> "ContextIndexJob":
        """Фиксирует terminal success и освобождает lease."""
        if self.state is not ContextIndexJobState.RUNNING:
            raise ContextIndexJobConflictError("Only running job can succeed")

        return replace(
            self,
            state=ContextIndexJobState.SUCCEEDED,
            next_attempt_at=None,
            lease_owner=None,
            lease_expires_at=None,
            last_error=None,
            updated_at=changed_at,
        )

    def schedule_retry(
        self,
        *,
        changed_at: datetime,
        next_attempt_at: datetime,
        error_message: str,
    ) -> "ContextIndexJob":
        """Переводит failed attempt в bounded retry_wait."""
        if self.is_terminal:
            return self

        return replace(
            self,
            state=ContextIndexJobState.RETRY_WAIT,
            next_attempt_at=next_attempt_at,
            dispatched_at=None,
            lease_owner=None,
            lease_expires_at=None,
            last_error=error_message[:2000],
            updated_at=changed_at,
        )

    def fail(
        self,
        *,
        changed_at: datetime,
        error_message: str,
    ) -> "ContextIndexJob":
        """Фиксирует terminal failure и освобождает lease."""
        if self.state is ContextIndexJobState.SUCCEEDED:
            return self

        return replace(
            self,
            state=ContextIndexJobState.FAILED,
            next_attempt_at=None,
            lease_owner=None,
            lease_expires_at=None,
            last_error=error_message[:2000],
            updated_at=changed_at,
        )

    def cancel(
        self,
        *,
        changed_at: datetime,
        reason: str,
    ) -> "ContextIndexJob":
        """Фиксирует terminal cancellation."""
        if self.is_terminal:
            return self

        return replace(
            self,
            state=ContextIndexJobState.CANCELED,
            next_attempt_at=None,
            lease_owner=None,
            lease_expires_at=None,
            last_error=reason[:2000],
            updated_at=changed_at,
        )

    def mark_dispatched(
        self,
        *,
        changed_at: datetime,
    ) -> "ContextIndexJob":
        """Фиксирует последнюю подтверждённую Rabbit publish attempt."""
        if self.is_terminal:
            return self

        return replace(
            self,
            dispatched_at=changed_at,
            updated_at=changed_at,
        )


def validate_chunks(
    chunks: tuple[NormalizedContextChunk, ...],
    *,
    max_chunks: int,
    max_text_chars: int,
) -> None:
    """Проверяет bounded complete normalized snapshot."""
    if not chunks:
        raise ContextValidationError("At least one normalized chunk is required")

    if len(chunks) > max_chunks:
        raise ContextValidationError(f"Context source cannot contain more than {max_chunks} chunks")

    identifiers: set[str] = set()

    for chunk in chunks:
        chunk.validate(max_text_chars=max_text_chars)

        if chunk.chunk_id in identifiers:
            raise ContextValidationError("Chunk identifiers must be unique")

        identifiers.add(chunk.chunk_id)


def build_context_index_fingerprint(
    *,
    source_sha256: str,
    model_name: str,
    vector_dimension: int,
    chunks: tuple[NormalizedContextChunk, ...],
) -> str:
    """Строит deterministic fingerprint normalized source generation."""
    payload = {
        "source_sha256": source_sha256,
        "model_name": model_name,
        "vector_dimension": vector_dimension,
        "chunks": [chunk.to_payload() for chunk in chunks],
    }
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return sha256(serialized).hexdigest()


def _optional_int(value: object) -> int | None:
    """Нормализует optional integer JSON value."""
    return None if value is None else int(value)


def _optional_str(value: object) -> str | None:
    """Нормализует optional string JSON value."""
    return None if value is None else str(value)
