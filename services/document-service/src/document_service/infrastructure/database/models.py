# services/document-service/src/document_service/infrastructure/database/models.py

"""SQLAlchemy models Document Service registry."""

from datetime import datetime
from typing import ClassVar
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from document_service.infrastructure.database.base import Base


class ProjectDocumentModel(Base):
    """Persistence model owner-scoped main PDF document."""

    __tablename__ = "project_documents"
    __table_args__: ClassVar[dict[str, str]] = {"schema": "document"}

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        index=True,
    )
    original_name: Mapped[str] = mapped_column(
        String(255),
    )
    storage_key: Mapped[str] = mapped_column(
        String(1024),
        unique=True,
    )
    mime_type: Mapped[str] = mapped_column(
        String(128),
    )
    size_bytes: Mapped[int] = mapped_column(
        BigInteger,
    )
    sha256: Mapped[str] = mapped_column(
        String(64),
    )
    page_count: Mapped[int] = mapped_column(
        Integer,
    )
    selected_pages: Mapped[list[int]] = mapped_column(
        JSONB,
    )
    lifecycle: Mapped[str] = mapped_column(
        String(32),
        index=True,
    )
    cleanup_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )
