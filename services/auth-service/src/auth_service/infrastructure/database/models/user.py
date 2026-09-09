# services/auth-service/src/auth_service/infrastructure/database/models/user.py

"""SQLAlchemy model persistent пользователя."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    Index,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from auth_service.infrastructure.database.base import (
    Base,
)


class UserModel(Base):
    """Persistence representation aggregate User."""

    __tablename__ = "users"
    __table_args__ = (
        Index(
            "uq_auth_users_email",
            "email",
            unique=True,
        ),
        {
            "schema": "auth",
        },
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
    )
    email: Mapped[str] = mapped_column(
        String(320),
        nullable=False,
    )
    password_hash: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
