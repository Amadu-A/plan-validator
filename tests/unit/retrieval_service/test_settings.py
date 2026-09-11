# tests/unit/retrieval_service/test_settings.py

"""Unit tests Retrieval Pydantic Settings."""

from pydantic import SecretStr
from retrieval_service.core.settings import RetrievalSettings


def test_retrieval_settings_defaults() -> None:
    """Проверяет shared Qdrant, queues и bounded embedding compatibility."""
    settings = RetrievalSettings(
        postgres_password=SecretStr("postgres-test"),
        rabbitmq_password=SecretStr("rabbit-test"),
        _env_file=None,
    )

    assert settings.service_name == "retrieval-service"
    assert settings.retrieval_database.schema_name == "retrieval"

    assert settings.retrieval_qdrant.collection_name == "plan_validator_managed_sources_v1"
    assert settings.retrieval_qdrant.alias_name == "plan_validator_managed_sources"
    assert settings.retrieval_qdrant.vector_size == 4096

    assert settings.retrieval_embedding.model_name == "Qwen/Qwen3-VL-Embedding-8B"
    assert settings.retrieval_embedding.vector_dimension == 4096

    assert settings.retrieval_queues.index_queue_name == "plan-validator.retrieval.index"
    assert settings.retrieval_queues.index_prefetch_count == 1
    assert settings.retrieval_queues.embedding_queue_name == "plan-validator.gpu.embedding"

    assert settings.retrieval_queues.rpc_timeout_seconds == 600.0

    assert settings.database_url.startswith("postgresql+psycopg://")
    assert settings.broker_url.startswith("amqp://")
