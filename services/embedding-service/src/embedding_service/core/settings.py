# services/embedding-service/src/embedding_service/core/settings.py

"""Pydantic Settings Embedding Service и GPU worker."""

from pathlib import Path
from typing import Literal
from urllib.parse import quote

from plan_validator_common.settings import CommonSettings
from pydantic import (
    BaseModel,
    Field,
    SecretStr,
    field_validator,
)

EmbeddingDtype = Literal[
    "bfloat16",
    "float16",
]


class EmbeddingModelSettings(BaseModel):
    """Описывает безопасный локальный Qwen embedding runtime."""

    name: str = "Qwen/Qwen3-VL-Embedding-8B"

    output_dimension: int = Field(
        default=4096,
        ge=64,
        le=4096,
    )

    hf_home: Path = Path("/models/huggingface")

    max_input_tokens: int = Field(
        default=8192,
        ge=512,
        le=32768,
    )

    max_text_chars: int = Field(
        default=60000,
        ge=1,
        le=500000,
    )

    max_batch_size: int = Field(
        default=1,
        ge=1,
        le=8,
    )

    max_job_items: int = Field(
        default=256,
        ge=1,
        le=1024,
    )

    min_free_ram_gib: float = Field(
        default=20.0,
        ge=1.0,
        le=1024.0,
    )

    min_free_vram_gib: float = Field(
        default=18.0,
        ge=1.0,
        le=128.0,
    )

    admission_wait_timeout_seconds: float = Field(
        default=480.0,
        gt=0,
        le=900,
    )

    admission_poll_seconds: float = Field(
        default=1.0,
        gt=0,
        le=30,
    )

    gpu_lease_path: Path = Path("/var/lock/plan-validator-gpu/gpu.lock")

    gpu_lease_timeout_seconds: float = Field(
        default=480.0,
        gt=0,
        le=900,
    )

    gpu_lease_poll_seconds: float = Field(
        default=0.25,
        gt=0,
        le=30,
    )

    dtype: EmbeddingDtype = "bfloat16"

    @property
    def min_free_ram_bytes(
        self,
    ) -> int:
        """Возвращает RAM admission threshold в bytes."""
        return int(self.min_free_ram_gib * 1024**3)

    @property
    def min_free_vram_bytes(
        self,
    ) -> int:
        """Возвращает VRAM admission threshold в bytes."""
        return int(self.min_free_vram_gib * 1024**3)


class EmbeddingBrokerSettings(BaseModel):
    """Описывает shared RabbitMQ endpoint без credentials."""

    host: str = Field(
        default="rabbitmq",
        min_length=1,
    )

    port: int = Field(
        default=5672,
        ge=1,
        le=65535,
    )

    user: str = Field(
        default="plan_validator",
        min_length=1,
    )

    virtual_host: str = Field(
        default="/plan-validator",
        min_length=1,
    )

    heartbeat_seconds: int = Field(
        default=60,
        ge=10,
        le=600,
    )


class EmbeddingQueueSettings(BaseModel):
    """Описывает dedicated GPU queue и bounded lifecycle."""

    name: str = Field(
        default="plan-validator.gpu.embedding",
        min_length=1,
    )

    prefetch_count: int = Field(
        default=1,
        ge=1,
        le=1,
    )

    rpc_timeout_seconds: float = Field(
        default=600.0,
        gt=0,
        le=900,
    )

    graceful_shutdown_seconds: int = Field(
        default=45,
        ge=5,
        le=55,
    )


class EmbeddingSettings(CommonSettings):
    """Safe settings HTTP Embedding Service и model cache contract."""

    service_name: str = "embedding-service"

    service_version: str = "0.1.0"

    embedding_model: EmbeddingModelSettings = Field(default_factory=EmbeddingModelSettings)

    embedding_broker: EmbeddingBrokerSettings = Field(default_factory=EmbeddingBrokerSettings)

    embedding_queue: EmbeddingQueueSettings = Field(default_factory=EmbeddingQueueSettings)


class EmbeddingWorkerSettings(EmbeddingSettings):
    """Расширяет safe settings единственным RabbitMQ secret worker-процесса."""

    service_name: str = "embedding-worker"

    rabbitmq_password: SecretStr

    @field_validator("rabbitmq_password")
    @classmethod
    def validate_rabbitmq_password(
        cls,
        value: SecretStr,
    ) -> SecretStr:
        """Запрещает placeholder вместо реального RabbitMQ password."""
        secret = value.get_secret_value()

        if not secret or secret.startswith("CHANGE_ME"):
            raise ValueError("Real RabbitMQ password is required")

        return value

    @property
    def broker_url(
        self,
    ) -> str:
        """Собирает AMQP URL без логирования credential."""
        user = quote(
            self.embedding_broker.user,
            safe="",
        )

        password = quote(
            self.rabbitmq_password.get_secret_value(),
            safe="",
        )

        virtual_host = quote(
            self.embedding_broker.virtual_host,
            safe="",
        )

        return (
            f"amqp://{user}:{password}@"
            f"{self.embedding_broker.host}:"
            f"{self.embedding_broker.port}/"
            f"{virtual_host}"
        )


def load_embedding_settings() -> EmbeddingSettings:
    """Загружает safe settings Embedding HTTP process."""
    return EmbeddingSettings()


def load_embedding_worker_settings() -> EmbeddingWorkerSettings:
    """Загружает settings GPU worker с обязательным RabbitMQ secret."""
    return EmbeddingWorkerSettings()
