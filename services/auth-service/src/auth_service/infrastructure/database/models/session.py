# services/auth-service/src/auth_service/infrastructure/database/models/session.py

"""SQLAlchemy model opaque authentication session."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Uuid,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from auth_service.infrastructure.database.base import (
    Base,
)


class AuthSessionModel(Base):
    """Persistence representation opaque session token hash."""

    __tablename__ = "sessions"
    __table_args__ = (
        Index(
            "uq_auth_sessions_token_hash",
            "token_hash",
            unique=True,
        ),
        Index(
            "ix_auth_sessions_user_id",
            "user_id",
        ),
        Index(
            "ix_auth_sessions_expires_at",
            "expires_at",
        ),
        {
            "schema": "auth",
        },
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "auth.users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
