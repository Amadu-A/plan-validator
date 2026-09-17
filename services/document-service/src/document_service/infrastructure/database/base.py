# services/document-service/src/document_service/infrastructure/database/base.py

"""SQLAlchemy declarative base Document Service."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Базовый metadata registry Document Service."""
