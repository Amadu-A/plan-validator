# services/context-service/src/context_service/application/ports/__init__.py

"""Application ports Context Service."""

from context_service.application.ports.clock import Clock
from context_service.application.ports.embedding_gateway import (
    ContextEmbeddingGateway,
    EmbeddedContextTexts,
)
from context_service.application.ports.health import HealthProbe
from context_service.application.ports.job_publisher import ContextIndexJobPublisher
from context_service.application.ports.repositories import (
    ContextIndexJobRepository,
    ContextSourceRepository,
    ProjectContextRepository,
)
from context_service.application.ports.unit_of_work import (
    ContextUnitOfWork,
    ContextUnitOfWorkFactory,
)
from context_service.application.ports.vector_store import ContextVectorStore

__all__ = [
    "Clock",
    "ContextEmbeddingGateway",
    "ContextIndexJobPublisher",
    "ContextIndexJobRepository",
    "ContextSourceRepository",
    "ContextUnitOfWork",
    "ContextUnitOfWorkFactory",
    "ContextVectorStore",
    "EmbeddedContextTexts",
    "HealthProbe",
    "ProjectContextRepository",
]
