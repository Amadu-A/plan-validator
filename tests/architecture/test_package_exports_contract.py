# tests/architecture/test_package_exports_contract.py

"""Architecture tests public package exports после Stage 9/10."""

from catalog_service.application.ports import (
    ManagedSourceRepository,
    SourceEventPublisher,
    SourceOutboxRepository,
    SourceStorage,
)
from catalog_service.application.use_cases import (
    DispatchNextSourceOutboxMessageUseCase,
    UploadManagedSourceUseCase,
)
from context_service.application.ports import (
    ContextEmbeddingGateway,
    ContextIndexJobPublisher,
    ContextIndexJobRepository,
    ContextSourceRepository,
    ContextUnitOfWorkFactory,
    ContextVectorStore,
    EmbeddedContextTexts,
    HealthProbe,
    ProjectContextRepository,
)
from context_service.application.use_cases import (
    CheckContextReadinessUseCase,
    ClaimContextIndexJobUseCase,
    CreateProjectContextUseCase,
    EnqueueContextIndexUseCase,
    FinalizeProjectContextCleanupUseCase,
    GetContextIndexJobUseCase,
    IndexContextSourceUseCase,
    ListProjectContextCleanupCandidatesUseCase,
    ReconcileContextIndexJobsUseCase,
    SearchProjectContextUseCase,
)
from context_service.domain import (
    ContextSearchHit,
    ContextSearchQuery,
)
from retrieval_service.application.ports import (
    EmbeddingGateway,
    IndexJobPublisher,
    ManagedSourceVectorStore,
    RetrievalUnitOfWorkFactory,
    SourceIndexRepository,
)
from retrieval_service.application.use_cases import (
    EnqueueSourceIndexUseCase,
    IndexManagedSourceUseCase,
    RegisterCatalogSourceUseCase,
    SearchManagedSourcesUseCase,
)


def test_catalog_stage9_exports_are_available() -> None:
    """Не позволяет снова забыть Stage 9 public application exports."""
    assert ManagedSourceRepository is not None
    assert SourceEventPublisher is not None
    assert SourceOutboxRepository is not None
    assert SourceStorage is not None
    assert DispatchNextSourceOutboxMessageUseCase is not None
    assert UploadManagedSourceUseCase is not None


def test_retrieval_stage9_exports_are_available() -> None:
    """Проверяет Retrieval package application surface."""
    assert EmbeddingGateway is not None
    assert IndexJobPublisher is not None
    assert ManagedSourceVectorStore is not None
    assert RetrievalUnitOfWorkFactory is not None
    assert SourceIndexRepository is not None

    assert EnqueueSourceIndexUseCase is not None
    assert IndexManagedSourceUseCase is not None
    assert RegisterCatalogSourceUseCase is not None
    assert SearchManagedSourcesUseCase is not None


def test_context_stage10_exports_are_available() -> None:
    """Проверяет Context ports/use-cases/domain exports."""
    assert ContextEmbeddingGateway is not None
    assert ContextIndexJobPublisher is not None
    assert ContextIndexJobRepository is not None
    assert ContextSourceRepository is not None
    assert ContextUnitOfWorkFactory is not None
    assert ContextVectorStore is not None
    assert EmbeddedContextTexts is not None
    assert HealthProbe is not None
    assert ProjectContextRepository is not None

    assert CheckContextReadinessUseCase is not None
    assert ClaimContextIndexJobUseCase is not None
    assert CreateProjectContextUseCase is not None
    assert EnqueueContextIndexUseCase is not None
    assert FinalizeProjectContextCleanupUseCase is not None
    assert GetContextIndexJobUseCase is not None
    assert IndexContextSourceUseCase is not None
    assert ListProjectContextCleanupCandidatesUseCase is not None
    assert ReconcileContextIndexJobsUseCase is not None
    assert SearchProjectContextUseCase is not None

    assert ContextSearchHit is not None
    assert ContextSearchQuery is not None
