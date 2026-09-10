# services/catalog-service/src/catalog_service/infrastructure/database/models/source.py

"""SQLAlchemy persistence model managed N/U source."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from catalog_service.infrastructure.database.base import Base


class ManagedSourceModel(Base):
    """Persistence representation persistent managed source metadata."""

    __tablename__ = "managed_sources"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('N', 'U')",
            name="ck_catalog_managed_sources_kind",
        ),
        CheckConstraint(
            "lifecycle IN ('active', 'delete_pending', 'cleanup_failed', 'deleted')",
            name="ck_catalog_managed_sources_lifecycle",
        ),
        CheckConstraint(
            "size_bytes >= 0",
            name="ck_catalog_managed_sources_size_bytes",
        ),
        Index(
            "ix_catalog_managed_sources_user_kind_section_created",
            "user_id",
            "kind",
            "section_id",
            "created_at",
        ),
        {"schema": "catalog"},
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )
    section_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "catalog.sections.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(
        String(1),
        nullable=False,
    )
    original_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    storage_key: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        unique=True,
    )
    mime_type: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    size_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    lifecycle: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    last_cleanup_error: Mapped[str | None] = mapped_column(
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
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
