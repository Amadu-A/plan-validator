# services/context-service/src/context_service/infrastructure/database/models.py

"""SQLAlchemy persistence models Context Service."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from context_service.infrastructure.database.base import Base


class ProjectContextModel(Base):
    """Persistence representation temporary Project Context."""

    __tablename__ = "project_contexts"
    __table_args__ = (
        CheckConstraint(
            "state IN ('active', 'cleanup_pending', 'cleaned')",
            name="ck_context_project_context_state",
        ),
        Index(
            "ix_context_project_contexts_user_state",
            "user_id",
            "state",
        ),
        Index(
            "ix_context_project_contexts_expiration",
            "state",
            "expires_at",
        ),
        {"schema": "context"},
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    state: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    cleanup_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )


class ContextSourceModel(Base):
    """Persistence representation временного T/PZ source."""

    __tablename__ = "sources"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('T', 'PZ')",
            name="ck_context_source_kind",
        ),
        CheckConstraint(
            "state IN ('awaiting_chunks', 'indexed', 'deleted')",
            name="ck_context_source_state",
        ),
        CheckConstraint(
            "chunk_count >= 0",
            name="ck_context_source_chunk_count",
        ),
        UniqueConstraint(
            "context_id",
            "kind",
            name="uq_context_source_kind",
        ),
        Index(
            "ix_context_sources_owner",
            "user_id",
            "context_id",
            "kind",
            "state",
        ),
        {"schema": "context"},
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
    )
    context_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "context.project_contexts.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(
        String(2),
        nullable=False,
    )
    original_name: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
    )
    source_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    state: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    active_fingerprint: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    chunk_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )


class ContextIndexJobModel(Base):
    """Persistence representation recoverable indexing execution."""

    __tablename__ = "index_jobs"
    __table_args__ = (
        CheckConstraint(
            ("state IN ('queued', 'running', 'retry_wait', 'succeeded', 'failed', 'canceled')"),
            name="ck_context_index_job_state",
        ),
        CheckConstraint(
            "attempt >= 0",
            name="ck_context_index_job_attempt",
        ),
        CheckConstraint(
            "max_attempts >= 1",
            name="ck_context_index_job_max_attempts",
        ),
        Index(
            "ix_context_index_jobs_source_fingerprint",
            "source_id",
            "fingerprint",
            "state",
        ),
        Index(
            "ix_context_index_jobs_recovery",
            "state",
            "deadline_at",
            "next_attempt_at",
            "lease_expires_at",
            "dispatched_at",
        ),
        {"schema": "context"},
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
    )
    context_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "context.project_contexts.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    source_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "context.sources.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(
        String(2),
        nullable=False,
    )
    fingerprint: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    correlation_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    chunks: Mapped[list[dict[str, object]]] = mapped_column(
        JSON,
        nullable=False,
    )
    state: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    attempt: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    deadline_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    dispatched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    lease_owner: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
