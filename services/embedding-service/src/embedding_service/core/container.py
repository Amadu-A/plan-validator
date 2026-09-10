# services/embedding-service/src/embedding_service/core/container.py

"""Composition root Embedding HTTP Service."""

from dataclasses import dataclass

from embedding_service.application.use_cases.runtime_status import (
    CheckReadinessUseCase,
    GetRuntimeStatusUseCase,
)
from embedding_service.core.settings import EmbeddingSettings
from embedding_service.infrastructure.model_cache import HuggingFaceModelCacheProbe


@dataclass(slots=True)
class EmbeddingContainer:
    """Хранит process-level dependencies HTTP Embedding Service."""

    settings: EmbeddingSettings
    check_readiness: CheckReadinessUseCase
    get_runtime_status: GetRuntimeStatusUseCase


def build_container(settings: EmbeddingSettings) -> EmbeddingContainer:
    """Собирает safe filesystem dependencies без CUDA/model load."""
    cache_probe = HuggingFaceModelCacheProbe(
        hf_home=settings.embedding_model.hf_home,
        model_name=settings.embedding_model.name,
    )

    return EmbeddingContainer(
        settings=settings,
        check_readiness=CheckReadinessUseCase(cache_probe),
        get_runtime_status=GetRuntimeStatusUseCase(
            model=settings.embedding_model.name,
            dimension=settings.embedding_model.output_dimension,
            queue=settings.embedding_queue.name,
            cache_probe=cache_probe,
        ),
    )
