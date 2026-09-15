# services/context-service/src/context_service/transport/schemas.py

"""Internal HTTP schemas временного Project Context."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from context_service.application.use_cases.index_jobs import (
    EnqueueContextIndexResult,
)
from context_service.domain.models import (
    ContextIndexJob,
    ContextIndexJobState,
    ContextSource,
    ContextSourceKind,
    ContextSourceState,
    NormalizedContextChunk,
    ProjectContext,
    ProjectContextState,
)
from context_service.domain.search import (
    ContextSearchHit,
    ContextSemanticRole,
)


class HealthResponse(BaseModel):
    """Operational health response Context Service."""

    model_config = ConfigDict(frozen=True)

    status: Literal[
        "alive",
        "ready",
        "not_ready",
    ]
    service: str
    version: str


class CreateProjectContextRequest(BaseModel):
    """Создание owner-scoped временного Project Context."""

    model_config = ConfigDict(extra="forbid")

    user_id: UUID


class ProjectContextResponse(BaseModel):
    """Safe lifecycle representation временного Project Context."""

    id: UUID
    user_id: UUID
    state: ProjectContextState

    created_at: datetime
    updated_at: datetime
    expires_at: datetime

    @classmethod
    def from_domain(
        cls,
        context: ProjectContext,
    ) -> "ProjectContextResponse":
        """Преобразует domain Project Context без cleanup internals."""
        return cls(
            id=context.id,
            user_id=context.user_id,
            state=context.state,
            created_at=context.created_at,
            updated_at=context.updated_at,
            expires_at=context.expires_at,
        )


class RegisterContextSourceRequest(BaseModel):
    """Регистрирует metadata одного временного T либо PZ source."""

    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    kind: ContextSourceKind

    original_name: str = Field(
        min_length=1,
        max_length=512,
    )

    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ContextSourceResponse(BaseModel):
    """Safe metadata временного T/PZ source."""

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

    @classmethod
    def from_domain(
        cls,
        source: ContextSource,
    ) -> "ContextSourceResponse":
        """Преобразует domain source в HTTP DTO."""
        return cls(
            id=source.id,
            context_id=source.context_id,
            user_id=source.user_id,
            kind=source.kind,
            original_name=source.original_name,
            source_sha256=source.source_sha256,
            state=source.state,
            active_fingerprint=source.active_fingerprint,
            chunk_count=source.chunk_count,
            created_at=source.created_at,
            updated_at=source.updated_at,
        )


class NormalizedContextChunkRequest(BaseModel):
    """Parser-neutral normalized T/PZ chunk."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: str = Field(
        min_length=1,
        max_length=128,
    )

    text: str = Field(min_length=1)

    page_number: int | None = Field(
        default=None,
        ge=1,
    )

    fragment_index: int | None = Field(
        default=None,
        ge=0,
    )

    heading: str | None = Field(
        default=None,
        max_length=500,
    )

    char_start: int | None = Field(
        default=None,
        ge=0,
    )

    char_end: int | None = Field(
        default=None,
        ge=0,
    )

    @model_validator(mode="after")
    def validate_char_range(
        self,
    ) -> "NormalizedContextChunkRequest":
        """Не допускает inverted character locator range."""
        if (
            self.char_start is not None
            and self.char_end is not None
            and self.char_end < self.char_start
        ):
            raise ValueError("char_end must not be before char_start")

        return self

    def to_domain(
        self,
    ) -> NormalizedContextChunk:
        """Преобразует transport DTO в parser-neutral domain chunk."""
        return NormalizedContextChunk(
            chunk_id=self.chunk_id,
            text=self.text,
            page_number=self.page_number,
            fragment_index=self.fragment_index,
            heading=self.heading,
            char_start=self.char_start,
            char_end=self.char_end,
        )


class EnqueueContextIndexRequest(BaseModel):
    """Complete normalized snapshot одного временного source."""

    model_config = ConfigDict(extra="forbid")

    user_id: UUID

    chunks: list[NormalizedContextChunkRequest] = Field(
        min_length=1,
        max_length=1024,
    )


class ContextIndexAcceptedResponse(BaseModel):
    """Результат durable Context indexing enqueue."""

    job_id: UUID | None
    fingerprint: str
    reused: bool

    status: Literal[
        "queued",
        "already_indexed",
    ]

    @classmethod
    def from_application(
        cls,
        result: EnqueueContextIndexResult,
    ) -> "ContextIndexAcceptedResponse":
        """Преобразует application result в safe transport response."""
        status = "already_indexed" if result.reused and result.job_id is None else "queued"

        return cls(
            job_id=result.job_id,
            fingerprint=result.fingerprint,
            reused=result.reused,
            status=status,
        )


class ContextIndexJobResponse(BaseModel):
    """Safe durable job status без chunks, lease owner и raw errors."""

    id: UUID
    context_id: UUID
    source_id: UUID
    user_id: UUID

    kind: ContextSourceKind
    fingerprint: str
    state: ContextIndexJobState

    attempt: int
    max_attempts: int

    deadline_at: datetime
    next_attempt_at: datetime | None

    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(
        cls,
        job: ContextIndexJob,
    ) -> "ContextIndexJobResponse":
        """Преобразует persistent job в безопасный status DTO."""
        return cls(
            id=job.id,
            context_id=job.context_id,
            source_id=job.source_id,
            user_id=job.user_id,
            kind=job.kind,
            fingerprint=job.fingerprint,
            state=job.state,
            attempt=job.attempt,
            max_attempts=job.max_attempts,
            deadline_at=job.deadline_at,
            next_attempt_at=job.next_attempt_at,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )


class ContextSearchRequest(BaseModel):
    """Owner-scoped typed T/PZ search request."""

    model_config = ConfigDict(extra="forbid")

    user_id: UUID

    text: str = Field(
        min_length=1,
        max_length=60000,
    )

    limit: int | None = Field(
        default=None,
        ge=1,
        le=100,
    )

    score_threshold: float | None = Field(
        default=None,
        ge=-1.0,
        le=1.0,
    )


class ContextSearchHitResponse(BaseModel):
    """Explicit non-normative T/PZ retrieval hit."""

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

    semantic_role: ContextSemanticRole

    @classmethod
    def from_domain(
        cls,
        hit: ContextSearchHit,
    ) -> "ContextSearchHitResponse":
        """Преобразует domain hit без изменения semantic role."""
        return cls(
            source_id=hit.source_id,
            context_id=hit.context_id,
            user_id=hit.user_id,
            kind=hit.kind,
            source_name=hit.source_name,
            chunk_id=hit.chunk_id,
            text=hit.text,
            score=hit.score,
            fingerprint=hit.fingerprint,
            page_number=hit.page_number,
            fragment_index=hit.fragment_index,
            heading=hit.heading,
            char_start=hit.char_start,
            char_end=hit.char_end,
            semantic_role=hit.semantic_role,
        )


class ContextSearchResponse(BaseModel):
    """Ordered typed temporary Project Context search hits."""

    hits: list[ContextSearchHitResponse]
