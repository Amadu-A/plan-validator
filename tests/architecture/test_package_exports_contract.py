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
    ContextIndexJobPublisher,
    ContextIndexJobRepository,
    ContextSourceRepository,
    ContextUnitOfWorkFactory,
    ProjectContextRepository,
)
from context_service.application.use_cases import (
    ClaimContextIndexJobUseCase,
    CreateProjectContextUseCase,
    EnqueueContextIndexUseCase,
    ReconcileContextIndexJobsUseCase,
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
    """Проверяет новый Context package application surface."""
    assert ContextIndexJobPublisher is not None
    assert ContextIndexJobRepository is not None
    assert ContextSourceRepository is not None
    assert ContextUnitOfWorkFactory is not None
    assert ProjectContextRepository is not None

    assert ClaimContextIndexJobUseCase is not None
    assert CreateProjectContextUseCase is not None
    assert EnqueueContextIndexUseCase is not None
    assert ReconcileContextIndexJobsUseCase is not None
