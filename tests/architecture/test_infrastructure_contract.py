# tests/architecture/test_infrastructure_contract.py

"""Architecture tests для infrastructure/bootstrap contract Plan Validator.

Тесты защищают ownership shared infrastructure, изоляцию project databases,
Pydantic-first application configuration, bounded logging, sparse secrets и
отсутствие опасного Docker socket coupling.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def read_project_file(
    relative_path: str,
) -> str:
    """Читает project file для infrastructure architecture assertions."""
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def test_infrastructure_stage_files_exist() -> None:
    """Проверяет наличие обязательных файлов infrastructure stage."""
    required_files = (
        ".env.example",
        "compose.yaml",
        "docs/INFRASTRUCTURE.md",
        "scripts/bootstrap-env.sh",
        "scripts/preflight-shared.sh",
        "scripts/provision-rabbitmq.sh",
        "scripts/check-infrastructure.sh",
        "scripts/up.sh",
    )

    missing_files = [
        relative_path
        for relative_path in required_files
        if not (PROJECT_ROOT / relative_path).is_file()
    ]

    assert not missing_files, f"Missing infrastructure files: {missing_files}"


def test_compose_uses_project_specific_storage() -> None:
    """Проверяет наличие отдельных PostgreSQL/Qdrant и persistent volumes."""
    compose = read_project_file("compose.yaml")

    required_markers = (
        "postgres:16-alpine",
        "qdrant/qdrant:v1.19.0",
        "postgres-data",
        "qdrant-data",
        "plan-validator-private",
    )

    for marker in required_markers:
        assert marker in compose, f"Compose infrastructure marker is missing: {marker}"


def test_compose_declares_shared_network_as_external() -> None:
    """Защищает ownership external ai-shared за shared infrastructure project."""
    compose = read_project_file("compose.yaml")

    assert "ai-shared:" in compose
    assert "external: true" in compose
    assert "PLAN_VALIDATOR_SHARED_NETWORK_NAME" in compose


def test_compose_does_not_duplicate_shared_services() -> None:
    """Не позволяет добавить собственные Ollama, RabbitMQ или n8n."""
    compose = read_project_file("compose.yaml")

    forbidden_service_definitions = (
        "\n  ollama:\n",
        "\n  rabbitmq:\n",
        "\n  n8n:\n",
    )

    for service_definition in forbidden_service_definitions:
        assert service_definition not in compose


def test_compose_has_bounded_container_logging() -> None:
    """Проверяет ограничение размера Docker stdout/stderr logs."""
    compose = read_project_file("compose.yaml")

    required_markers = (
        "driver: local",
        "PLAN_VALIDATOR_DOCKER_LOG_MAX_SIZE",
        "PLAN_VALIDATOR_DOCKER_LOG_MAX_FILE",
        "max-size:",
        "max-file:",
    )

    for marker in required_markers:
        assert marker in compose, f"Logging marker is missing: {marker}"


def test_compose_does_not_mount_docker_socket() -> None:
    """Запрещает выдавать containers управление host Docker daemon."""
    compose = read_project_file("compose.yaml")

    assert "/var/run/docker.sock" not in compose
    assert "container_name:" not in compose


def test_application_services_do_not_duplicate_pydantic_environment() -> None:
    """Фиксирует отсутствие больших application `environment:` blocks."""
    compose = read_project_file("compose.yaml")

    auth_start = compose.index("\n  auth-service:\n")
    auth_end = compose.index("\n  auth-migrate:\n")

    gateway_start = compose.index("\n  api-gateway:\n")
    gateway_end = compose.index("\nnetworks:\n")

    auth_block = compose[auth_start:auth_end]
    gateway_block = compose[gateway_start:gateway_end]

    assert "\n    environment:" not in auth_block
    assert "\n    environment:" not in gateway_block


def test_env_example_defines_only_two_required_project_secrets() -> None:
    """Фиксирует минимальную модель из двух private project secrets."""
    env_example = read_project_file(".env.example")

    required_secret_names = (
        "PLAN_VALIDATOR_POSTGRES_PASSWORD",
        "PLAN_VALIDATOR_RABBITMQ_PASSWORD",
    )

    for secret_name in required_secret_names:
        assert secret_name in env_example

    forbidden_secret_names = (
        "JWT_SECRET",
        "JWT_SIGNING_KEY",
        "RABBITMQ_DEFAULT_PASS",
        "N8N_ENCRYPTION_KEY",
    )

    for secret_name in forbidden_secret_names:
        assert secret_name not in env_example


def test_rabbitmq_isolation_is_explicit() -> None:
    """Проверяет отдельный project vhost/user без shared bootstrap identity."""
    env_example = read_project_file(".env.example")
    provisioning_script = read_project_file("scripts/provision-rabbitmq.sh")

    assert "PLAN_VALIDATOR_RABBITMQ_USER=plan_validator" in env_example
    assert "PLAN_VALIDATOR_RABBITMQ_VHOST=/plan-validator" in env_example
    assert "set_permissions" in provisioning_script
    assert "authenticate_user" in provisioning_script
    assert "shared_admin" not in provisioning_script


def test_shared_checks_use_runtime_not_shared_repository_checkout() -> None:
    """Запрещает обязательную зависимость от локального checkout shared repo."""
    preflight = read_project_file("scripts/preflight-shared.sh")
    provisioning = read_project_file("scripts/provision-rabbitmq.sh")

    assert "com.docker.compose.service" in preflight
    assert "com.docker.compose.service" in provisioning
    assert "docker exec" in preflight
    assert "docker exec" in provisioning
    assert "SHARED_INFRA_DIR" not in preflight
    assert "SHARED_INFRA_DIR" not in provisioning
    assert "docker compose up" not in preflight


def test_rabbitmq_checks_do_not_short_circuit_runtime_queries() -> None:
    """Запрещает `grep -q` pipelines с rabbitmqctl при включённом pipefail."""
    provisioning = read_project_file("scripts/provision-rabbitmq.sh")

    assert "set -Eeuo pipefail" in provisioning
    assert "rabbitmqctl_shared list_vhosts --silent" in provisioning
    assert "rabbitmqctl_shared list_users --silent" in provisioning
    assert "list_user_permissions" in provisioning
    assert "| grep" not in provisioning


def test_startup_orders_runtime_dependencies_before_consumers() -> None:
    """Фиксирует first-run order Infrastructure -> Gateway -> Auth -> Catalog."""
    startup = read_project_file("scripts/up.sh")

    infrastructure_position = startup.index("./scripts/check-infrastructure.sh --fix")
    gateway_position = startup.index("./scripts/check-gateway.sh --fix")
    auth_position = startup.index("./scripts/check-auth.sh --fix")
    catalog_position = startup.index("./scripts/check-catalog.sh --fix")

    assert infrastructure_position < gateway_position < auth_position < catalog_position


def test_bootstrap_does_not_print_generated_secrets() -> None:
    """Проверяет, что bootstrap не выводит generated secret values."""
    bootstrap_script = read_project_file("scripts/bootstrap-env.sh")

    assert "openssl rand -hex 32" in bootstrap_script
    assert "printf '[FIX] generated secret: %s\\n'" in bootstrap_script
    assert "printf '%s=%s\\n'" in bootstrap_script
