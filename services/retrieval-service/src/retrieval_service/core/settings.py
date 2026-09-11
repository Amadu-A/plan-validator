# services/retrieval-service/src/retrieval_service/core/settings.py

"""Pydantic Settings Retrieval Service, worker и one-shot initializer."""

from urllib.parse import quote

from plan_validator_common.settings import CommonSettings
from pydantic import BaseModel, Field, SecretStr, field_validator


class RetrievalDatabaseSettings(BaseModel):
    """Safe PostgreSQL registry connection/pool settings."""

    host: str = Field(default="postgres", min_length=1)
    port: int = Field(default=5432, ge=1, le=65535)
    database: str = Field(default="plan_validator", min_length=1)
    user: str = Field(default="plan_validator", min_length=1)
    schema_name: str = Field(default="retrieval", min_length=1)
    pool_size: int = Field(default=10, ge=1)
    max_overflow: int = Field(default=10, ge=0)
    pool_timeout_seconds: float = Field(default=30.0, gt=0)


class RetrievalQdrantSettings(BaseModel):
    """Safe Qdrant shared managed-source corpus contract."""

    host: str = Field(default="qdrant", min_length=1)
    http_port: int = Field(default=6333, ge=1, le=65535)
    grpc_port: int = Field(default=6334, ge=1, le=65535)
    prefer_grpc: bool = True
    timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    collection_name: str = Field(
        default="plan_validator_managed_sources_v1",
        min_length=1,
    )
    alias_name: str = Field(
        default="plan_validator_managed_sources",
        min_length=1,
    )
    vector_size: int = Field(default=4096, ge=64, le=4096)


class RetrievalEmbeddingSettings(BaseModel):
    """Expected embedding identity совместимости Retrieval corpus."""

    model_name: str = Field(
        default="Qwen/Qwen3-VL-Embedding-8B",
        min_length=1,
    )
    vector_dimension: int = Field(
        default=4096,
        ge=64,
        le=4096,
    )


class RetrievalBrokerSettings(BaseModel):
    """Safe shared RabbitMQ endpoint Retrieval processes."""

    host: str = Field(default="rabbitmq", min_length=1)
    port: int = Field(default=5672, ge=1, le=65535)
    user: str = Field(default="plan_validator", min_length=1)
    virtual_host: str = Field(default="/plan-validator", min_length=1)
    heartbeat_seconds: int = Field(default=60, ge=10, le=600)


class RetrievalQueueSettings(BaseModel):
    """Durable Catalog/index queues и bounded embedding RPC."""

    catalog_exchange_name: str = Field(
        default="plan-validator.catalog.events",
        min_length=1,
    )
    catalog_queue_name: str = Field(
        default="plan-validator.retrieval.catalog-events",
        min_length=1,
    )
    index_queue_name: str = Field(
        default="plan-validator.retrieval.index",
        min_length=1,
    )
    catalog_prefetch_count: int = Field(default=10, ge=1, le=100)
    index_prefetch_count: int = Field(default=1, ge=1, le=1)
    embedding_queue_name: str = Field(
        default="plan-validator.gpu.embedding",
        min_length=1,
    )
    rpc_timeout_seconds: float = Field(
        default=600.0,
        gt=0,
        le=900,
    )


class RetrievalIndexingSettings(BaseModel):
    """Bounds normalized source indexing commands."""

    max_chunks_per_source: int = Field(default=256, ge=1, le=1024)
    max_chunk_chars: int = Field(default=8000, ge=128, le=60000)


class RetrievalSearchSettings(BaseModel):
    """Bounds direct typed retrieval requests."""

    default_limit: int = Field(default=10, ge=1, le=50)
    max_limit: int = Field(default=50, ge=1, le=100)
    default_score_threshold: float = Field(
        default=0.3,
        ge=-1.0,
        le=1.0,
    )


class RetrievalSettings(CommonSettings):
    """Объединяет Retrieval configuration с двумя существующими secrets."""

    service_name: str = "retrieval-service"
    service_version: str = "0.1.0"

    postgres_password: SecretStr
    rabbitmq_password: SecretStr

    retrieval_database: RetrievalDatabaseSettings = Field(default_factory=RetrievalDatabaseSettings)
    retrieval_qdrant: RetrievalQdrantSettings = Field(default_factory=RetrievalQdrantSettings)
    retrieval_embedding: RetrievalEmbeddingSettings = Field(
        default_factory=RetrievalEmbeddingSettings
    )
    retrieval_broker: RetrievalBrokerSettings = Field(default_factory=RetrievalBrokerSettings)
    retrieval_queues: RetrievalQueueSettings = Field(default_factory=RetrievalQueueSettings)
    retrieval_indexing: RetrievalIndexingSettings = Field(default_factory=RetrievalIndexingSettings)
    retrieval_search: RetrievalSearchSettings = Field(default_factory=RetrievalSearchSettings)

    @field_validator(
        "postgres_password",
        "rabbitmq_password",
    )
    @classmethod
    def validate_secret(
        cls,
        value: SecretStr,
    ) -> SecretStr:
        """Запрещает committed placeholders для runtime secrets."""
        secret = value.get_secret_value()

        if not secret or secret.startswith("CHANGE_ME"):
            raise ValueError("Real runtime secret is required")

        return value

    @property
    def database_url(self) -> str:
        """Собирает SQLAlchemy URL без логирования password."""
        user = quote(
            self.retrieval_database.user,
            safe="",
        )
        password = quote(
            self.postgres_password.get_secret_value(),
            safe="",
        )
        database = quote(
            self.retrieval_database.database,
            safe="",
        )

        return (
            "postgresql+psycopg://"
            f"{user}:{password}@{self.retrieval_database.host}:"
            f"{self.retrieval_database.port}/{database}"
        )

    @property
    def broker_url(self) -> str:
        """Собирает AMQP URL без логирования credential."""
        user = quote(
            self.retrieval_broker.user,
            safe="",
        )
        password = quote(
            self.rabbitmq_password.get_secret_value(),
            safe="",
        )
        virtual_host = quote(
            self.retrieval_broker.virtual_host,
            safe="",
        )

        return (
            f"amqp://{user}:{password}@{self.retrieval_broker.host}:"
            f"{self.retrieval_broker.port}/{virtual_host}"
        )


class RetrievalWorkerSettings(RetrievalSettings):
    """Process identity Retrieval background worker."""

    service_name: str = "retrieval-worker"


def load_retrieval_settings() -> RetrievalSettings:
    """Загружает HTTP/ops Retrieval settings."""
    return RetrievalSettings()


def load_retrieval_worker_settings() -> RetrievalWorkerSettings:
    """Загружает Retrieval worker settings."""
    return RetrievalWorkerSettings()
