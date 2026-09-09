# services/auth-service/src/auth_service/infrastructure/database/base.py

"""SQLAlchemy declarative base Authentication Service."""

from sqlalchemy.orm import (
    DeclarativeBase,
)


class Base(DeclarativeBase):
    """Базовый SQLAlchemy metadata registry auth schema."""
