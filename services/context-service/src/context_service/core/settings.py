# services/context-service/src/context_service/core/settings.py

"""Pydantic Settings Context Service и recoverable indexing contract."""

from urllib.parse import quote

from plan_validator_common.settings import CommonSettings
from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator


class ContextDatabaseSettings(BaseModel):
    """Safe PostgreSQL settings Context registry."""

    host: str = Field(default="postgres", min_length=1)
    port: int = Field(default=5432, ge=1, le=65535)
    database: str = Field(default="plan_validator", min_length=1)
    user: str = Field(default="plan_validator", min_length=1)
    schema_name: str = Field(default="context", min_length=1)
    pool_size: int = Field(default=10, ge=1)
    max_overflow: int = Field(default=10, ge=0)
    pool_timeout_seconds: float = Field(default=30.0, gt=0)


class ContextBrokerSettings(BaseModel):
    """Safe shared RabbitMQ endpoint Context workers."""

    host: str = Field(default="rabbitmq", min_length=1)
    port: int = Field(default=5672, ge=1, le=65535)
    user: str = Field(default="plan_validator", min_length=1)
    virtual_host: str = Field(default="/plan-validator", min_length=1)
    heartbeat_seconds: int = Field(default=60, ge=10, le=600)


class ContextQueueSettings(BaseModel):
    """Bounded queue, deadline, lease и retry policy."""

    index_queue_name: str = Field(
        default="plan-validator.context.index",
        min_length=1,
    )
    prefetch_count: int = Field(default=1, ge=1, le=1)
    message_ttl_ms: int = Field(
        default=15 * 60 * 1000,
        ge=60_000,
        le=60 * 60 * 1000,
    )
    execution_timeout_seconds: int = Field(
        default=10 * 60,
        ge=30,
        le=20 * 60,
    )
    job_deadline_seconds: int = Field(
        default=12 * 60,
        ge=60,
        le=25 * 60,
    )
    max_attempts: int = Field(default=3, ge=1, le=5)
    lease_seconds: int = Field(default=60, ge=20, le=300)
    heartbeat_seconds: int = Field(default=15, ge=5, le=120)
    reconcile_seconds: int = Field(default=5, ge=1, le=60)
    retry_backoff_base_seconds: int = Field(default=5, ge=1, le=60)
    retry_backoff_max_seconds: int = Field(default=60, ge=1, le=300)
    reconciliation_batch_size: int = Field(default=50, ge=1, le=500)
    graceful_shutdown_seconds: int = Field(default=45, ge=5, le=120)

    @model_validator(mode="after")
    def validate_recovery_contract(self) -> "ContextQueueSettings":
        """Не допускает timeout policy, способную снова ждать 30 минут."""
        message_ttl_seconds = self.message_ttl_ms / 1000

        if self.job_deadline_seconds >= message_ttl_seconds:
            raise ValueError("Job deadline must be shorter than Rabbit message TTL")

        if self.execution_timeout_seconds >= self.job_deadline_seconds:
            raise ValueError("Execution timeout must be shorter than job deadline")

        if self.heartbeat_seconds * 2 >= self.lease_seconds:
            raise ValueError("Lease must allow at least two heartbeat periods")

        if self.retry_backoff_base_seconds > self.retry_backoff_max_seconds:
            raise ValueError("Retry base backoff must not exceed maximum backoff")

        return self


class ContextRetentionSettings(BaseModel):
    """Retention временного T/PZ context."""

    grace_hours: int = Field(default=24, ge=1, le=168)


class ContextIndexingSettings(BaseModel):
    """Bounds normalized T/PZ indexing input."""

    max_chunks_per_source: int = Field(default=256, ge=1, le=1024)
    max_chunk_chars: int = Field(default=8000, ge=128, le=60000)


class ContextEmbeddingSettings(BaseModel):
    """Embedding compatibility и bounded RPC для T/PZ."""

    model_name: str = Field(
        default="Qwen/Qwen3-VL-Embedding-8B",
        min_length=1,
    )
    vector_dimension: int = Field(default=4096, ge=64, le=4096)
    queue_name: str = Field(
        default="plan-validator.gpu.embedding",
        min_length=1,
    )
    rpc_timeout_seconds: float = Field(default=480.0, gt=0, le=600)
    index_instruction: str = Field(
        default=(
            "Represent this temporary project requirement fragment for semantic "
            "retrieval. It is project context, not normative evidence."
        ),
        min_length=1,
    )
    query_instruction: str = Field(
        default=(
            "Represent this query for retrieval from temporary project context. "
            "Retrieved T/PZ text is not normative evidence."
        ),
        min_length=1,
    )


class ContextQdrantSettings(BaseModel):
    """Per-context temporary Qdrant collection contract."""

    host: str = Field(default="qdrant", min_length=1)
    http_port: int = Field(default=6333, ge=1, le=65535)
    grpc_port: int = Field(default=6334, ge=1, le=65535)
    prefer_grpc: bool = True
    timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    collection_prefix: str = Field(
        default="plan_validator",
        min_length=1,
        max_length=64,
        pattern=r"^[a-z0-9_]+$",
    )


class ContextSearchSettings(BaseModel):
    """Bounds typed T/PZ search request."""

    default_limit: int = Field(default=10, ge=1, le=50)
    max_limit: int = Field(default=50, ge=1, le=100)
    default_score_threshold: float = Field(default=0.3, ge=-1.0, le=1.0)
    max_query_chars: int = Field(default=60000, ge=128, le=120000)


class ContextSettings(CommonSettings):
    """Объединяет Context configuration и runtime secrets."""

    service_name: str = "context-service"
    service_version: str = "0.1.0"

    postgres_password: SecretStr
    rabbitmq_password: SecretStr

    context_database: ContextDatabaseSettings = Field(default_factory=ContextDatabaseSettings)
    context_broker: ContextBrokerSettings = Field(default_factory=ContextBrokerSettings)
    context_queue: ContextQueueSettings = Field(default_factory=ContextQueueSettings)
    context_retention: ContextRetentionSettings = Field(default_factory=ContextRetentionSettings)
    context_indexing: ContextIndexingSettings = Field(default_factory=ContextIndexingSettings)
    context_embedding: ContextEmbeddingSettings = Field(default_factory=ContextEmbeddingSettings)
    context_qdrant: ContextQdrantSettings = Field(default_factory=ContextQdrantSettings)
    context_search: ContextSearchSettings = Field(default_factory=ContextSearchSettings)

    @model_validator(mode="after")
    def validate_runtime_timeout_contract(self) -> "ContextSettings":
        """Не допускает embedding RPC дольше execution budget worker."""
        if (
            self.context_embedding.rpc_timeout_seconds
            >= self.context_queue.execution_timeout_seconds
        ):
            raise ValueError("Context embedding RPC timeout must be shorter than execution timeout")
        return self

    @field_validator(
        "postgres_password",
        "rabbitmq_password",
    )
    @classmethod
    def validate_secret(
        cls,
        value: SecretStr,
    ) -> SecretStr:
        """Запрещает placeholder вместо real runtime secret."""
        secret = value.get_secret_value()

        if not secret or secret.startswith("CHANGE_ME"):
            raise ValueError("Real runtime secret is required")

        return value

    @property
    def database_url(self) -> str:
        """Собирает SQLAlchemy URL без логирования password."""
        user = quote(self.context_database.user, safe="")
        password = quote(self.postgres_password.get_secret_value(), safe="")
        database = quote(self.context_database.database, safe="")

        return (
            "postgresql+psycopg://"
            f"{user}:{password}@{self.context_database.host}:"
            f"{self.context_database.port}/{database}"
        )

    @property
    def broker_url(self) -> str:
        """Собирает AMQP URL без раскрытия password."""
        user = quote(self.context_broker.user, safe="")
        password = quote(self.rabbitmq_password.get_secret_value(), safe="")
        virtual_host = quote(self.context_broker.virtual_host, safe="")

        return (
            f"amqp://{user}:{password}@{self.context_broker.host}:"
            f"{self.context_broker.port}/{virtual_host}"
        )


def load_context_settings() -> ContextSettings:
    """Загружает Context settings через layered environment contract."""
    return ContextSettings()
