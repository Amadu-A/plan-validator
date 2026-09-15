#!/usr/bin/env bash
# scripts/check-context.sh
#
# Stage 10 Project Context quality/runtime gate.
# --fix синхронизирует dependencies, Rabbit policies, images, migration и runtime.
# --check выполняет immutable validation уже подготовленного runtime.

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

MODE="${1:---fix}"

print_step() {
  local step_name="$1"
  printf '\n=== %s ===\n' "${step_name}"
}

require_command() {
  local command_name="$1"

  if ! command -v "${command_name}" >/dev/null 2>&1; then
    printf 'ERROR: required command not found: %s\n' \
      "${command_name}" >&2
    exit 2
  fi
}

validate_mode() {
  case "${MODE}" in
    --fix|--check)
      ;;
    *)
      printf 'ERROR: unsupported mode: %s\n' \
        "${MODE}" >&2
      exit 3
      ;;
  esac
}

load_private_environment() {
  if [[ ! -f .env ]]; then
    printf 'ERROR: private .env is missing.\n' >&2
    exit 4
  fi

  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
}

check_required_files() {
  local required_files=(
    ".env.example"
    "compose.yaml"
    "services/context-service/Dockerfile"
    "services/context-service/pyproject.toml"
    "services/context-service/alembic.ini"
    "services/context-service/migrations/versions/0001_context.py"
    "services/context-service/src/context_service/core/settings.py"
    "services/context-service/src/context_service/infrastructure/messaging/worker.py"
    "services/context-service/src/context_service/infrastructure/messaging/maintenance.py"
    "services/context-service/src/context_service/infrastructure/messaging/healthcheck.py"
    "services/api-gateway/src/api_gateway/infrastructure/context_client.py"
    "services/api-gateway/src/api_gateway/transport/routers/project_contexts.py"
    "tests/unit/context_service/test_cleanup_context.py"
    "tests/transport/context_service/test_context_service.py"
    "tests/transport/api_gateway/test_project_contexts.py"
    "tests/architecture/test_context_service_contract.py"
    "tests/architecture/test_gateway_context_contract.py"
    "tests/architecture/test_rabbitmq_recovery_contract.py"
  )

  local relative_path

  for relative_path in "${required_files[@]}"; do
    if [[ ! -f "${relative_path}" ]]; then
      printf 'ERROR: required Context file is missing: %s\n' \
        "${relative_path}" >&2
      exit 5
    fi

    printf '[OK] %s\n' \
      "${relative_path}"
  done
}

check_python_dependencies() {
  python - <<'PY'
from importlib.metadata import PackageNotFoundError, version

EXPECTED = {
    "plan-validator-context-service": "0.1.0",
    "plan-validator-api-gateway": "0.1.0",
    "plan-validator-common": "0.1.0",
    "qdrant-client": "1.19.0",
    "aio-pika": "10.0.1",
    "SQLAlchemy": "2.0.52",
    "alembic": "1.19.2",
    "psycopg": "3.3.5",
    "fastapi": "0.141.1",
    "uvicorn": "0.52.1",
}

errors = []

for package_name, expected_version in EXPECTED.items():
    try:
        actual_version = version(package_name)
    except PackageNotFoundError:
        errors.append(f"{package_name}: not installed")
        continue

    if actual_version != expected_version:
        errors.append(
            f"{package_name}: expected {expected_version}, got {actual_version}"
        )

if errors:
    for error in errors:
        print(f"ERROR: {error}")
    raise SystemExit(1)

import api_gateway  # noqa: E402,F401
import context_service  # noqa: E402,F401

print("[OK] Context development dependencies are synchronized.")
PY
}

sync_python_dependencies() {
  if check_python_dependencies >/dev/null 2>&1; then
    printf '[OK] Context development dependencies already synchronized.\n'
    return 0
  fi

  printf '[FIX] Installing/updating root development dependencies...\n'
  python -m pip install -r requirements-dev.txt
  python -m pip check
  check_python_dependencies
}

prepare_runtime_directories() {
  mkdir -p \
    var/log/context-service \
    var/log/context-worker \
    var/log/context-maintenance

  printf '[OK] Context runtime log directories prepared.\n'
}

check_context_health() {
  docker compose exec -T context-service \
    python - <<'PY'
import json
import urllib.request

for path in ("/health/live", "/health/ready"):
    with urllib.request.urlopen(
        "http://127.0.0.1:8000" + path,
        timeout=8,
    ) as response:
        payload = json.load(response)
        assert response.status == 200
        assert payload["status"] in {"alive", "ready"}

print("[OK] Context Service liveness/readiness.")
PY
}

check_gateway_health() {
  docker compose exec -T api-gateway \
    python - <<'PY'
import json
import urllib.request

with urllib.request.urlopen(
    "http://127.0.0.1:8000/health/live",
    timeout=8,
) as response:
    payload = json.load(response)
    assert response.status == 200
    assert payload["status"] == "alive"

print("[OK] API Gateway liveness after Context wiring.")
PY
}

check_migration_head() {
  local migration_output

  migration_output="$(
    docker compose exec -T context-service \
      alembic \
      -c services/context-service/alembic.ini \
      current
  )"

  printf '%s\n' \
    "${migration_output}"

  if ! grep -Fq \
    "0001_context (head)" \
    <<<"${migration_output}"
  then
    printf 'ERROR: Context database is not at 0001_context head.\n' >&2
    exit 6
  fi

  printf '[OK] Context migration head.\n'
}

find_rabbitmq_container() {
  docker ps \
    --filter network=ai-shared \
    --filter label=com.docker.compose.service=rabbitmq \
    --format '{{.ID}}' \
    | sed -n '1p'
}

check_queue_consumers() {
  local rabbitmq_container
  local queue_output

  rabbitmq_container="$(
    find_rabbitmq_container
  )"

  if [[ -z "${rabbitmq_container}" ]]; then
    printf 'ERROR: shared RabbitMQ container was not found.\n' >&2
    exit 7
  fi

  queue_output="$(
    docker exec \
      "${rabbitmq_container}" \
      rabbitmqctl \
      list_queues \
      -p /plan-validator \
      name consumers \
      --silent
  )"

  local queue_name

  for queue_name in \
    "plan-validator.gpu.embedding" \
    "plan-validator.context.index"
  do
    local consumers=""

    while read -r candidate count; do
      if [[ "${candidate}" == "${queue_name}" ]]; then
        consumers="${count}"
        break
      fi
    done <<<"${queue_output}"

    if [[ \
      ! "${consumers}" =~ ^[0-9]+$ \
      || "${consumers}" -lt 1 \
    ]]; then
      printf 'ERROR: queue has no active consumer: %s\n' \
        "${queue_name}" >&2
      exit 8
    fi

    printf '[OK] %s consumers=%s\n' \
      "${queue_name}" \
      "${consumers}"
  done
}

check_runtime_users() {
  local service_uid
  local worker_uid
  local maintenance_uid

  service_uid="$(
    docker compose exec -T context-service id -u \
      | tr -d '\r'
  )"

  worker_uid="$(
    docker compose exec -T context-worker id -u \
      | tr -d '\r'
  )"

  maintenance_uid="$(
    docker compose exec -T context-maintenance id -u \
      | tr -d '\r'
  )"

  if [[ \
    "${service_uid}" == "0" \
    || "${worker_uid}" == "0" \
    || "${maintenance_uid}" == "0" \
  ]]; then
    printf 'ERROR: Context processes must not run as root.\n' >&2
    exit 9
  fi

  printf '[OK] Context Service UID: %s\n' \
    "${service_uid}"

  printf '[OK] Context Worker UID: %s\n' \
    "${worker_uid}"

  printf '[OK] Context Maintenance UID: %s\n' \
    "${maintenance_uid}"
}

check_structured_log() {
  local service_name="$1"
  local log_file="var/log/${service_name}/${service_name}.log"

  if [[ ! -s "${log_file}" ]]; then
    printf 'ERROR: structured log is missing: %s\n' \
      "${log_file}" >&2
    exit 10
  fi

  python - \
    "${log_file}" \
    "${service_name}" \
    <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
expected_service = sys.argv[2]

lines = [
    line
    for line in path.read_text(encoding="utf-8").splitlines()
    if line.strip()
]

if not lines:
    raise SystemExit("Structured log is empty")

payload = json.loads(lines[-1])

assert payload["service"] == expected_service
assert "timestamp" in payload
assert "level" in payload
assert "message" in payload

print(f"[OK] structured file log: {path}")
PY
}

validate_mode

require_command docker
require_command python
require_command pytest
require_command ruff

PLAN_VALIDATOR_RUNTIME_UID="${PLAN_VALIDATOR_RUNTIME_UID:-$(id -u)}"
PLAN_VALIDATOR_RUNTIME_GID="${PLAN_VALIDATOR_RUNTIME_GID:-$(id -g)}"

export PLAN_VALIDATOR_RUNTIME_UID
export PLAN_VALIDATOR_RUNTIME_GID

load_private_environment

print_step "Context Stage files"
check_required_files

if [[ "${MODE}" == "--fix" ]]; then
  print_step "Context dependency synchronization"
  sync_python_dependencies

  print_step "Automatic Ruff/format"
  ./scripts/check-common.sh --fix
else
  print_step "Context dependency check"
  check_python_dependencies

  print_step "Immutable Common check"
  ./scripts/check-common.sh --check

  printf '\nINFO: --check mode does not rebuild/migrate/start Context runtime.\n'
fi

print_step "Stage 9 predecessor contract"
./scripts/check-retrieval.sh --check

print_step "RabbitMQ project policies"

if [[ "${MODE}" == "--fix" ]]; then
  ./scripts/provision-rabbitmq.sh --fix
else
  ./scripts/provision-rabbitmq.sh --check
fi

print_step "Context unit tests"
pytest \
  tests/unit/context_service \
  tests/unit/api_gateway/test_context_client.py \
  tests/unit/embedding_service/test_settings.py

print_step "Context transport tests"
pytest \
  tests/transport/context_service \
  tests/transport/api_gateway/test_project_contexts.py

print_step "Architecture tests"
pytest tests/architecture

print_step "Compose validation"
docker compose config --quiet

if [[ "${MODE}" == "--fix" ]]; then
  print_step "Context runtime directories"
  prepare_runtime_directories

  print_step "Build Stage 10 images"
  docker compose build \
    embedding-worker \
    context-service \
    api-gateway

  print_step "Context database migration"
  docker compose \
    --profile ops \
    run \
    --rm \
    context-migrate

  print_step "Stage 10 runtime startup"
  docker compose up \
    -d \
    --wait \
    embedding-worker \
    context-worker \
    context-maintenance \
    context-service \
    api-gateway
fi

print_step "Stage 10 containers"
docker compose ps \
  embedding-worker \
  context-worker \
  context-maintenance \
  context-service \
  api-gateway

print_step "Context HTTP runtime"
check_context_health

print_step "Gateway runtime"
check_gateway_health

print_step "Context migration head"
check_migration_head

print_step "Context RabbitMQ consumers"
check_queue_consumers

print_step "RabbitMQ TTL policy validation"
./scripts/provision-rabbitmq.sh --check

print_step "Context runtime users"
check_runtime_users

print_step "Context structured logging"
check_structured_log context-service
check_structured_log context-worker
check_structured_log context-maintenance

print_step "Git whitespace"
git diff --check

printf '\nCONTEXT STAGE CHECKS PASSED\n'