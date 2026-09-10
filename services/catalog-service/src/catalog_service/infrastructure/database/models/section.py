# services/catalog-service/src/catalog_service/infrastructure/database/models/section.py

"""SQLAlchemy persistence model Catalog section."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from catalog_service.infrastructure.database.base import Base


class SectionModel(Base):
    """Persistence representation user-owned nested section."""

    __tablename__ = "sections"
    __table_args__ = (
        Index(
            "ix_catalog_sections_user_parent_order",
            "user_id",
            "parent_id",
            "sort_order",
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
    parent_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "catalog.sections.id",
            ondelete="CASCADE",
        ),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )
    sort_order: Mapped[int] = mapped_column(
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