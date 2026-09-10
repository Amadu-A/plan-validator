# services/retrieval-service/src/retrieval_service/infrastructure/database/base.py

"""Declarative SQLAlchemy base Retrieval Service."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Базовый класс Retrieval persistence models."""
