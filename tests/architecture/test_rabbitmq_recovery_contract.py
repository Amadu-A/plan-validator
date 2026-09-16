# tests/architecture/test_rabbitmq_recovery_contract.py

"""Architecture contract bounded Rabbit/restart recovery Stage 10."""

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    """Читает UTF-8 project file."""
    return (_ROOT / relative_path).read_text(encoding="utf-8")


def test_project_rabbitmq_has_combined_ttl_and_consumer_timeout_policies() -> None:
    """TTL и delivery timeout объединены в policies каждой группы очередей."""
    script = _read("scripts/provision-rabbitmq.sh")
    env = _read(".env.example")

    assert "plan-validator-work-queue-ttl" in script
    assert "plan-validator-catalog-event-queue-ttl" in script

    expected_work_pattern = (
        r"^(plan-validator\.gpu\.embedding|"
        r"plan-validator\.retrieval\.index|"
        r"plan-validator\.context\.index)$"
    )
    expected_catalog_pattern = r"^plan-validator\.retrieval\.catalog-events$"

    assert f"WORK_QUEUE_POLICY_PATTERN='{expected_work_pattern}'" in script
    assert f"CATALOG_QUEUE_POLICY_PATTERN='{expected_catalog_pattern}'" in script

    assert "PLAN_VALIDATOR_RABBITMQ_WORK_QUEUE_TTL_MS=900000" in env
    assert "PLAN_VALIDATOR_RABBITMQ_WORK_QUEUE_CONSUMER_TIMEOUT_MS=720000" in env
    assert "PLAN_VALIDATOR_RABBITMQ_CATALOG_EVENT_QUEUE_TTL_MS=604800000" in env
    assert "PLAN_VALIDATOR_RABBITMQ_CATALOG_EVENT_QUEUE_CONSUMER_TIMEOUT_MS=300000" in env

    start = script.index("load_policy_settings() {")
    end = script.index("discover_shared_rabbitmq() {")
    policy_settings = script[start:end]

    assert '"${\n' not in policy_settings
    assert (
        'WORK_QUEUE_TTL_MS="${PLAN_VALIDATOR_RABBITMQ_WORK_QUEUE_TTL_MS:-900000}"'
        in policy_settings
    )
    assert (
        'WORK_QUEUE_CONSUMER_TIMEOUT_MS="'
        '${PLAN_VALIDATOR_RABBITMQ_WORK_QUEUE_CONSUMER_TIMEOUT_MS:-720000}"' in policy_settings
    )
    assert (
        'CATALOG_QUEUE_TTL_MS="'
        '${PLAN_VALIDATOR_RABBITMQ_CATALOG_EVENT_QUEUE_TTL_MS:-604800000}"' in policy_settings
    )
    assert (
        'CATALOG_QUEUE_CONSUMER_TIMEOUT_MS="'
        '${PLAN_VALIDATOR_RABBITMQ_CATALOG_EVENT_QUEUE_CONSUMER_TIMEOUT_MS:-300000}"'
        in policy_settings
    )

    start = script.index("apply_queue_policy() {")
    end = script.index("apply_rabbitmq_fixes() {")
    policy_apply = script[start:end]

    assert policy_apply.count("set_policy") == 1
    assert r"\"message-ttl\":${ttl_ms}" in policy_apply
    assert r"\"consumer-timeout\":${consumer_timeout_ms}" in policy_apply


def test_rabbitmq_policy_validation_checks_ttl_and_consumer_timeout() -> None:
    """Immutable check проверяет оба параметра уже применённой policy."""
    script = _read("scripts/provision-rabbitmq.sh")

    start = script.index("rabbitmq_policy_matches() {")
    end = script.index("apply_queue_policy() {")
    policy_check = script[start:end]

    assert "expected_ttl" in policy_check
    assert "expected_consumer_timeout" in policy_check
    assert r"\"message-ttl\":${expected_ttl}" in policy_check
    assert r"\"consumer-timeout\":${expected_consumer_timeout}" in policy_check


def test_rabbitmq_policy_validation_uses_rabbitmq_41_cli_contract() -> None:
    """list_policies не получает неподдерживаемый RabbitMQ 4.1 список колонок."""
    script = _read("scripts/provision-rabbitmq.sh")

    start = script.index("rabbitmq_policy_matches() {")
    end = script.index("apply_queue_policy() {")
    policy_check = script[start:end]

    assert "list_policies" in policy_check
    assert '-p "${RABBITMQ_VHOST}"' in policy_check
    assert "--silent" in policy_check

    assert "local vhost_name" in policy_check

    unsupported_column_selection = (
        "name \\\n      pattern \\\n      apply-to \\\n      definition \\\n      priority"
    )

    assert unsupported_column_selection not in policy_check

    assert '"${vhost_name}" != "${RABBITMQ_VHOST}"' in policy_check


def test_rabbitmq_recovery_never_depends_on_queue_purge() -> None:
    """Manual purge не является частью production recovery contract."""
    script = _read("scripts/provision-rabbitmq.sh").casefold()

    assert "purge_queue" not in script
    assert "purge queue" not in script


def test_stage10_compose_has_context_runtime_and_graceful_workers() -> None:
    """Фиксирует service/worker/maintenance/migrate deployment topology."""
    compose = _read("compose.yaml")

    for service in (
        "context-service:",
        "context-worker:",
        "context-maintenance:",
        "context-migrate:",
    ):
        assert service in compose

    assert "context_service.infrastructure.messaging.worker" in compose
    assert "context_service.infrastructure.messaging.maintenance" in compose
    assert compose.count("stop_grace_period: 60s") >= 2


def test_embedding_worker_has_no_poison_requeue_and_supports_drain() -> None:
    """Shared GPU queue не может бесконечно блокироваться одним delivery."""
    worker = _read(
        "services/embedding-service/src/embedding_service/infrastructure/messaging/worker.py"
    )

    assert "nack(requeue=True)" not in worker
    assert "queue.cancel(" in worker
    assert "graceful_shutdown_seconds" in worker
    assert "signal.SIGTERM" in worker


def test_context_cleanup_removes_persisted_normalized_chunks() -> None:
    """Physical cleanup удаляет не только Qdrant, но и DB job payload."""
    cleanup = _read(
        "services/context-service/src/context_service/application/use_cases/cleanup_context.py"
    )

    repository = _read(
        "services/context-service/src/context_service/infrastructure/database/context_repository.py"
    )

    assert "uow.jobs.delete_for_context" in cleanup
    assert "uow.sources.delete_for_context" in cleanup
    assert "delete(ContextIndexJobModel)" in repository


def test_committed_runtime_timeouts_do_not_restore_thirty_minute_waits() -> None:
    """Проверяет реальные env values, которые перекрывают Pydantic defaults."""
    env = _read(".env.example")

    forbidden = (
        "PLAN_VALIDATOR_EMBEDDING_MODEL__ADMISSION_WAIT_TIMEOUT_SECONDS=1800",
        "PLAN_VALIDATOR_EMBEDDING_MODEL__GPU_LEASE_TIMEOUT_SECONDS=1800",
        "PLAN_VALIDATOR_EMBEDDING_QUEUE__RPC_TIMEOUT_SECONDS=1800",
        "PLAN_VALIDATOR_RETRIEVAL_QUEUES__RPC_TIMEOUT_SECONDS=1800",
    )

    for value in forbidden:
        assert value not in env

    assert "PLAN_VALIDATOR_CONTEXT_QUEUE__JOB_DEADLINE_SECONDS=720" in env
    assert "PLAN_VALIDATOR_CONTEXT_QUEUE__EXECUTION_TIMEOUT_SECONDS=600" in env
