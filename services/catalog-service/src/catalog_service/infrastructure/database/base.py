# services/catalog-service/src/catalog_service/infrastructure/database/base.py

"""SQLAlchemy declarative base Catalog Service."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Базовый SQLAlchemy metadata registry Catalog Service."""
