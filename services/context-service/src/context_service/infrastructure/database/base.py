# services/context-service/src/context_service/infrastructure/database/base.py

"""SQLAlchemy declarative base Context Service."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative metadata owner Context Service."""
