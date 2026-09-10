# services/retrieval-service/src/retrieval_service/infrastructure/messaging/schemas.py

"""Pydantic schemas Catalog lifecycle и normalized indexing messages."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CatalogSourceEventPayload(BaseModel):
    """Storage-neutral payload Catalog source lifecycle event."""

    model_config = ConfigDict(extra="forbid")

    source_id: UUID
    user_id: UUID
    section_id: UUID
    kind: Literal["N", "U"]
    original_name: str = Field(min_length=1, max_length=512)
    mime_type: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    lifecycle: str = Field(min_length=1, max_length=32)


class CatalogSourceEvent(BaseModel):
    """Версионированный envelope Catalog transactional outbox."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    event_id: UUID
    event_type: Literal[
        "catalog.source.uploaded.v1",
        "catalog.source.delete_requested.v1",
    ]
    occurred_at: datetime
    source: CatalogSourceEventPayload


class NormalizedChunkMessage(BaseModel):
    """Transport representation одного normalized source fragment."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1)
    page_number: int | None = Field(default=None, ge=1)
    fragment_index: int | None = Field(default=None, ge=0)
    heading: str | None = Field(default=None, max_length=500)
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)


class SourceIndexJobMessage(BaseModel):
    """Durable normalized source indexing command."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    job_id: UUID
    source_id: UUID
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    correlation_id: str = Field(min_length=1, max_length=128)
    chunks: list[NormalizedChunkMessage] = Field(min_length=1, max_length=1024)
