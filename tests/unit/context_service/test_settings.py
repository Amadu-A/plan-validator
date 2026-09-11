# tests/unit/context_service/test_settings.py

"""Unit tests Context Service bounded recovery settings."""

import pytest
from context_service.core.settings import ContextQueueSettings, ContextSettings
from pydantic import SecretStr, ValidationError


def test_context_settings_defaults_are_bounded() -> None:
    """Проверяет Stage 10 queue/deadline/lease/Qdrant defaults."""
    settings = ContextSettings(
        postgres_password=SecretStr("postgres-test"),
        rabbitmq_password=SecretStr("rabbit-test"),
        _env_file=None,
    )
    queue = settings.context_queue

    assert settings.service_name == "context-service"
    assert settings.context_database.schema_name == "context"
    assert settings.context_retention.grace_hours == 24
    assert settings.context_embedding.vector_dimension == 4096
    assert settings.context_embedding.queue_name == "plan-validator.gpu.embedding"
    assert settings.context_embedding.rpc_timeout_seconds == 480.0
    assert settings.context_qdrant.collection_prefix == "plan_validator"
    assert settings.context_search.max_query_chars == 60000

    assert queue.index_queue_name == "plan-validator.context.index"
    assert queue.prefetch_count == 1
    assert queue.message_ttl_ms == 900_000
    assert queue.execution_timeout_seconds == 600
    assert queue.job_deadline_seconds == 720
    assert queue.max_attempts == 3
    assert queue.lease_seconds == 60
    assert queue.heartbeat_seconds == 15
    assert queue.reconcile_seconds == 5
    assert queue.graceful_shutdown_seconds == 45


def test_context_queue_rejects_deadline_longer_than_message_ttl() -> None:
    """Не допускает job, способный жить дольше Rabbit work message."""
    with pytest.raises(ValidationError):
        ContextQueueSettings(
            message_ttl_ms=600_000,
            job_deadline_seconds=600,
            execution_timeout_seconds=500,
        )


def test_context_queue_rejects_unsafe_heartbeat_ratio() -> None:
    """Не допускает lease почти равный heartbeat interval."""
    with pytest.raises(ValidationError):
        ContextQueueSettings(
            lease_seconds=30,
            heartbeat_seconds=15,
        )


def test_context_settings_reject_embedding_rpc_longer_than_execution_budget() -> None:
    """Не допускает возврат к длинному GPU RPC внутри короткого Context job."""
    with pytest.raises(ValidationError):
        ContextSettings(
            postgres_password=SecretStr("postgres-test"),
            rabbitmq_password=SecretStr("rabbit-test"),
            context_queue={
                "execution_timeout_seconds": 300,
                "job_deadline_seconds": 600,
                "message_ttl_ms": 900_000,
            },
            context_embedding={"rpc_timeout_seconds": 300},
            _env_file=None,
        )
