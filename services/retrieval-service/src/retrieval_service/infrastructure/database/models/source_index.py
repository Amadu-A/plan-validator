# services/retrieval-service/src/retrieval_service/infrastructure/database/models/source_index.py

"""SQLAlchemy persistence model Retrieval source-index registry."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from retrieval_service.infrastructure.database.base import Base


class ManagedSourceIndexModel(Base):
    """Persistence representation active fingerprint и Catalog source identity."""

    __tablename__ = "managed_source_indexes"
    __table_args__ = (
        CheckConstraint("kind IN ('N', 'U')", name="ck_retrieval_source_kind"),
        CheckConstraint(
            "state IN ('awaiting_chunks', 'indexed', 'deleted')",
            name="ck_retrieval_source_state",
        ),
        CheckConstraint("chunk_count >= 0", name="ck_retrieval_chunk_count"),
        Index(
            "ix_retrieval_sources_user_kind_state",
            "user_id",
            "kind",
            "state",
        ),
        Index(
            "ix_retrieval_sources_section",
            "user_id",
            "section_id",
            "kind",
        ),
        {"schema": "retrieval"},
    )

    source_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    section_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(1), nullable=False)
    original_name: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    active_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    vector_dimension: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
