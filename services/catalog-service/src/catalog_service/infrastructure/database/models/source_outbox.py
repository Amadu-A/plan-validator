# services/catalog-service/src/catalog_service/infrastructure/database/models/source_outbox.py

"""SQLAlchemy persistence model transactional outbox managed sources."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from catalog_service.infrastructure.database.base import Base


class SourceOutboxMessageModel(Base):
    """Persistence representation durable source lifecycle event."""

    __tablename__ = "source_outbox_messages"
    __table_args__ = (
        CheckConstraint(
            "attempt_count >= 0",
            name="ck_catalog_source_outbox_attempt_count",
        ),
        Index(
            "ix_catalog_source_outbox_pending",
            "published_at",
            "created_at",
        ),
        Index(
            "ix_catalog_source_outbox_source_id",
            "source_id",
        ),
        {"schema": "catalog"},
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
    )
    source_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    payload: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
