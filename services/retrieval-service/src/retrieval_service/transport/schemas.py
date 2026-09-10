# services/retrieval-service/src/retrieval_service/transport/schemas.py

"""Internal HTTP schemas normalized indexing и typed N/U retrieval."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from retrieval_service.domain.search import SearchHit
from retrieval_service.domain.source_index import ManagedSourceIndex, SourceIndexState, SourceKind


class HealthResponse(BaseModel):
    """Operational health response Retrieval Service."""

    model_config = ConfigDict(frozen=True)

    status: Literal["alive", "ready", "not_ready"]
    service: str
    version: str


class NormalizedChunkRequest(BaseModel):
    """Transport DTO одного parser-neutral normalized source fragment."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1)
    page_number: int | None = Field(default=None, ge=1)
    fragment_index: int | None = Field(default=None, ge=0)
    heading: str | None = Field(default=None, max_length=500)
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_char_range(self) -> "NormalizedChunkRequest":
        """Не допускает inverted character locator range."""
        if (
            self.char_start is not None
            and self.char_end is not None
            and self.char_end < self.char_start
        ):
            raise ValueError("char_end must not be before char_start")

        return self


class SourceIndexRequest(BaseModel):
    """Complete normalized chunks snapshot одного Catalog source."""

    model_config = ConfigDict(extra="forbid")

    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    chunks: list[NormalizedChunkRequest] = Field(min_length=1, max_length=1024)


class SourceIndexAcceptedResponse(BaseModel):
    """Ответ постановки source reindex в durable queue."""

    job_id: UUID
    source_id: UUID
    status: Literal["queued"] = "queued"


class SearchRequest(BaseModel):
    """Internal tenant-scoped search request; source type задаёт route."""

    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    text: str = Field(min_length=1, max_length=60000)
    section_ids: list[UUID] = Field(default_factory=list, max_length=100)
    source_ids: list[UUID] = Field(default_factory=list, max_length=100)
    limit: int | None = Field(default=None, ge=1, le=100)
    score_threshold: float | None = Field(default=None, ge=-1.0, le=1.0)


class SearchHitResponse(BaseModel):
    """Search hit со stable clickable Catalog content URL."""

    source_id: UUID
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
    source_content_url: str

    @classmethod
    def from_domain(cls, hit: SearchHit) -> "SearchHitResponse":
        """Преобразует typed domain hit в storage-neutral API response."""
        resource = "normative-documents" if hit.kind is SourceKind.NORMATIVE else "user-documents"

        return cls(
            source_id=hit.source_id,
            section_id=hit.section_id,
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
            source_content_url=(f"/api/v1/catalog/{resource}/{hit.source_id}/content"),
        )


class SearchResponse(BaseModel):
    """Container ordered typed retrieval hits."""

    hits: list[SearchHitResponse]


class SourceIndexStatusResponse(BaseModel):
    """Safe Retrieval-owned indexing status одного Catalog source."""

    source_id: UUID
    user_id: UUID
    section_id: UUID
    kind: SourceKind
    original_name: str
    source_sha256: str
    state: SourceIndexState
    active_fingerprint: str | None
    model_name: str | None
    vector_dimension: int | None
    chunk_count: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None

    @classmethod
    def from_domain(cls, source: ManagedSourceIndex) -> "SourceIndexStatusResponse":
        """Преобразует registry entity в safe operational response."""
        return cls(
            source_id=source.source_id,
            user_id=source.user_id,
            section_id=source.section_id,
            kind=source.kind,
            original_name=source.original_name,
            source_sha256=source.source_sha256,
            state=source.state,
            active_fingerprint=source.active_fingerprint,
            model_name=source.model_name,
            vector_dimension=source.vector_dimension,
            chunk_count=source.chunk_count,
            created_at=source.created_at,
            updated_at=source.updated_at,
            deleted_at=source.deleted_at,
        )
