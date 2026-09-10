# services/catalog-service/src/catalog_service/infrastructure/database/models/system_prompt.py

"""SQLAlchemy persistence model пользовательского system prompt."""

from datetime import datetime
from typing import ClassVar
from uuid import UUID

from sqlalchemy import DateTime, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from catalog_service.infrastructure.database.base import Base


class SystemPromptModel(Base):
    """Persistence representation singleton prompt пользователя."""

    __tablename__ = "system_prompts"
    __table_args__: ClassVar[dict[str, str]] = {"schema": "catalog"}

    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
    )
    prompt: Mapped[str] = mapped_column(
        Text,
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
