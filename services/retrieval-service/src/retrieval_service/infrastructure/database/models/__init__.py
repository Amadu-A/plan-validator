# services/retrieval-service/src/retrieval_service/infrastructure/database/models/__init__.py

"""SQLAlchemy models Retrieval Service."""

from retrieval_service.infrastructure.database.models.source_index import ManagedSourceIndexModel

__all__ = ["ManagedSourceIndexModel"]
