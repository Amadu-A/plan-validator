# services/embedding-service/src/embedding_service/domain/embedding.py

"""Domain types и invariants text embedding операций."""

from dataclasses import dataclass
from uuid import UUID


class EmbeddingDomainError(ValueError):
    """Базовая domain-ошибка embedding запроса."""


class InvalidEmbeddingInputError(EmbeddingDomainError):
    """Embedding input нарушает bounded contract."""


@dataclass(frozen=True, slots=True)
class EmbeddingTextInput:
    """Представляет один text input для unified Qwen checkpoint."""

    text: str
    instruction: str | None = None

    def validate(self, *, max_text_chars: int) -> None:
        """Проверяет непустой bounded text и optional instruction."""
        if not self.text.strip():
            raise InvalidEmbeddingInputError("Embedding text must not be empty")

        if len(self.text) > max_text_chars:
            raise InvalidEmbeddingInputError(
                f"Embedding text exceeds {max_text_chars} character limit"
            )

        if self.instruction is not None and len(self.instruction) > 2000:
            raise InvalidEmbeddingInputError("Embedding instruction is too long")


@dataclass(frozen=True, slots=True)
class EmbeddingTelemetry:
    """Хранит безопасные runtime measurements одной GPU операции."""

    available_ram_bytes: int
    free_vram_before_bytes: int
    total_vram_bytes: int
    model_load_ms: float
    encode_ms: float
    total_ms: float
    peak_allocated_vram_bytes: int


@dataclass(frozen=True, slots=True)
class EmbeddingResult:
    """Результат одного normalized embedding job."""

    job_id: UUID
    model: str
    dimension: int
    vector: tuple[float, ...]
    telemetry: EmbeddingTelemetry


@dataclass(frozen=True, slots=True)
class EmbeddingBatchResult:
    """Результат batch text embedding внутри одного model-load lifecycle."""

    job_id: UUID
    model: str
    dimension: int
    vectors: tuple[tuple[float, ...], ...]
    telemetry: EmbeddingTelemetry
