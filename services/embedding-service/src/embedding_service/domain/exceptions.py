# services/embedding-service/src/embedding_service/domain/exceptions.py

"""Domain/application-neutral ошибки GPU embedding runtime."""


class EmbeddingRuntimeError(RuntimeError):
    """Базовая ошибка execution embedding runtime."""


class EmbeddingModelCacheError(EmbeddingRuntimeError):
    """Локальный Qwen checkpoint отсутствует или неполон."""


class EmbeddingGpuLeaseTimeoutError(EmbeddingRuntimeError):
    """Project GPU lease не получен за bounded timeout."""


class EmbeddingRamAdmissionError(EmbeddingRuntimeError):
    """Свободной RAM недостаточно для безопасной загрузки модели."""


class EmbeddingVramAdmissionError(EmbeddingRuntimeError):
    """CUDA/VRAM не удовлетворяет admission policy."""


class EmbeddingModelExecutionError(EmbeddingRuntimeError):
    """Ошибка загрузки или inference Qwen checkpoint."""
