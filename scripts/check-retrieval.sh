#!/usr/bin/env bash
# scripts/check-retrieval.sh
#
# Quality/migration/runtime gate Stage 9 N/U indexing and Retrieval Service.
# --fix синхронизирует зависимости, перестраивает изменённые images, мигрирует
# Retrieval registry, инициализирует Qdrant corpus и запускает runtime.
# --check выполняет только immutable проверки уже подготовленного Stage 9.

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
    printf 'ERROR: required command not found: %s\n' "${command_name}" >&2
    exit 2
  fi
}

validate_mode() {
  case "${MODE}" in
    --fix|--check)
      ;;
    *)
      printf 'ERROR: unsupported mode: %s\n' "${MODE}" >&2
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
    "packages/common/src/plan_validator_common/vector_codec.py"
    "services/retrieval-service/Dockerfile"
    "services/retrieval-service/pyproject.toml"
    "services/retrieval-service/alembic.ini"
    "services/retrieval-service/migrations/versions/0001_retrieval.py"
    "services/retrieval-service/src/retrieval_service/core/settings.py"
    "services/retrieval-service/src/retrieval_service/application/use_cases/index_source.py"
    "services/retrieval-service/src/retrieval_service/application/use_cases/search_sources.py"
    "services/retrieval-service/src/retrieval_service/infrastructure/qdrant_initializer.py"
    "services/retrieval-service/src/retrieval_service/infrastructure/vector_store/qdrant.py"
    "services/retrieval-service/src/retrieval_service/infrastructure/messaging/worker.py"
    "services/catalog-service/src/catalog_service/infrastructure/messaging/dispatcher.py"
    "services/embedding-service/src/embedding_service/infrastructure/messaging/worker.py"
    "tests/unit/retrieval_service/test_indexing.py"
    "tests/transport/retrieval_service/test_retrieval_service.py"
    "tests/architecture/test_retrieval_service_contract.py"
    "docs/RETRIEVAL_SERVICE.md"
  )

  local relative_path

  for relative_path in "${required_files[@]}"; do
    if [[ ! -f "${relative_path}" ]]; then
      printf 'ERROR: required Retrieval file is missing: %s\n' \
        "${relative_path}" >&2
      exit 5
    fi

    printf '[OK] %s\n' "${relative_path}"
  done
}

check_python_dependencies() {
  python - <<'PY'
from importlib.metadata import PackageNotFoundError, version

EXPECTED = {
    "plan-validator-retrieval-service": "0.1.0",
    "plan-validator-embedding-service": "0.1.0",
    "plan-validator-catalog-service": "0.1.0",
    "plan-validator-common": "0.1.0",
    "qdrant-client": "1.19.0",
    "aio-pika": "10.0.1",
    "SQLAlchemy": "2.0.52",
    "alembic": "1.19.2",
    "psycopg": "3.3.5",
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

import retrieval_service  # noqa: E402,F401

print("[OK] Retrieval development dependencies are synchronized.")
PY
}

sync_python_dependencies() {
  if check_python_dependencies >/dev/null 2>&1; then
    printf '[OK] Retrieval development dependencies already synchronized.\n'
    return 0
  fi

  printf '[FIX] Installing/updating root development dependencies...\n'
  python -m pip install -r requirements-dev.txt
  python -m pip check
  check_python_dependencies
}

prepare_runtime_directories() {
  mkdir -p \
    var/log/catalog-outbox \
    var/log/retrieval-service \
    var/log/retrieval-worker \
    var/log/retrieval-init

  printf '[OK] Retrieval runtime log directories prepared.\n'
}

check_retrieval_health() {
  docker compose exec -T retrieval-service \
    python -c "
import json
import urllib.request

for path in ('/health/live', '/health/ready'):
    with urllib.request.urlopen(
        'http://127.0.0.1:8000' + path,
        timeout=8,
    ) as response:
        payload = json.load(response)
        assert response.status == 200
        assert payload['status'] in {'alive', 'ready'}
"

  printf '[OK] Retrieval Service liveness/readiness.\n'
}

check_migration_head() {
  local migration_output

  migration_output="$(
    docker compose exec -T retrieval-service \
      alembic \
      -c services/retrieval-service/alembic.ini \
      current
  )"

  printf '%s\n' "${migration_output}"

  if ! grep -Fq "0001_retrieval (head)" <<<"${migration_output}"; then
    printf 'ERROR: Retrieval database is not at 0001_retrieval head.\n' >&2
    exit 6
  fi

  printf '[OK] Retrieval migration head.\n'
}

check_qdrant_contract() {
  docker compose exec -T retrieval-service \
    python - <<'PY'
from qdrant_client import QdrantClient

client = QdrantClient(
    host="qdrant",
    port=6333,
    prefer_grpc=False,
    timeout=10,
)

try:
    info = client.get_collection("plan_validator_managed_sources")
    vectors = info.config.params.vectors
    assert getattr(vectors, "size", None) == 4096

    aliases = client.get_aliases().aliases
    matches = [
        alias
        for alias in aliases
        if alias.alias_name == "plan_validator_managed_sources"
    ]
    assert len(matches) == 1
    assert matches[0].collection_name == "plan_validator_managed_sources_v1"

    schema = info.payload_schema
    for field in ("user_id", "kind", "section_id", "source_id", "version_key"):
        assert field in schema, f"missing payload index: {field}"
finally:
    client.close()

print("[OK] Retrieval shared Qdrant alias/vector/payload-index contract.")
PY
}

check_runtime_users() {
  local service_uid
  local worker_uid
  local outbox_uid

  service_uid="$(docker compose exec -T retrieval-service id -u | tr -d '\r')"
  worker_uid="$(docker compose exec -T retrieval-worker id -u | tr -d '\r')"
  outbox_uid="$(docker compose exec -T catalog-outbox id -u | tr -d '\r')"

  if [[ "${service_uid}" == "0" || "${worker_uid}" == "0" || "${outbox_uid}" == "0" ]]; then
    printf 'ERROR: Retrieval/Catalog-outbox processes must not run as root.\n' >&2
    exit 7
  fi

  printf '[OK] Retrieval Service UID: %s\n' "${service_uid}"
  printf '[OK] Retrieval Worker UID: %s\n' "${worker_uid}"
  printf '[OK] Catalog Outbox UID: %s\n' "${outbox_uid}"
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
  rabbitmq_container="$(find_rabbitmq_container)"

  if [[ -z "${rabbitmq_container}" ]]; then
    printf 'ERROR: shared RabbitMQ container was not found.\n' >&2
    exit 8
  fi

  local queue_output
  queue_output="$(
    docker exec "${rabbitmq_container}" \
      rabbitmqctl \
      list_queues \
      -p /plan-validator \
      name consumers \
      --silent
  )"

  local queue_name
  for queue_name in \
    "plan-validator.gpu.embedding" \
    "plan-validator.retrieval.catalog-events" \
    "plan-validator.retrieval.index"
  do
    local consumers=""

    while read -r candidate count; do
      if [[ "${candidate}" == "${queue_name}" ]]; then
        consumers="${count}"
        break
      fi
    done <<<"${queue_output}"

    if [[ ! "${consumers}" =~ ^[0-9]+$ || "${consumers}" -lt 1 ]]; then
      printf 'ERROR: queue has no active consumer: %s\n' "${queue_name}" >&2
      exit 9
    fi

    printf '[OK] %s consumers=%s\n' "${queue_name}" "${consumers}"
  done
}

check_structured_log() {
  local service_name="$1"
  local log_file="var/log/${service_name}/${service_name}.log"

  if [[ ! -s "${log_file}" ]]; then
    printf 'ERROR: structured log is missing: %s\n' "${log_file}" >&2
    exit 10
  fi

  python - "${log_file}" "${service_name}" <<'PY'
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

print_step "Retrieval Stage files"
check_required_files

if [[ "${MODE}" == "--fix" ]]; then
  print_step "Retrieval dependency synchronization"
  sync_python_dependencies

  print_step "Automatic Ruff/format"
  ./scripts/check-common.sh --fix
else
  print_step "Retrieval dependency check"
  check_python_dependencies

  print_step "Immutable Common check"
  ./scripts/check-common.sh --check

  printf '\nINFO: --check mode does not rebuild/migrate/initialize Retrieval.\n'
fi

print_step "Embedding predecessor contract"
./scripts/check-embedding.sh --check

print_step "Retrieval unit tests"
pytest tests/unit/retrieval_service tests/unit/catalog_service/test_source_outbox_dispatch.py \
  tests/unit/embedding_service/test_batch_embedding.py

print_step "Retrieval transport tests"
pytest tests/transport/retrieval_service

print_step "Architecture tests"
pytest tests/architecture

print_step "Compose validation"
docker compose config --quiet

if [[ "${MODE}" == "--fix" ]]; then
  print_step "Runtime directories"
  prepare_runtime_directories

  print_step "Build Stage 9 images"
  docker compose build \
    catalog-service \
    embedding-worker \
    retrieval-service

  print_step "Retrieval database migration"
  docker compose \
    --profile ops \
    run \
    --rm \
    retrieval-migrate

  print_step "Shared Qdrant managed-source corpus initialization"
  docker compose \
    --profile ops \
    run \
    --rm \
    retrieval-init

  print_step "Stage 9 runtime startup"
  docker compose up \
    -d \
    --wait \
    embedding-worker \
    catalog-outbox \
    retrieval-worker \
    retrieval-service
fi

print_step "Stage 9 containers"
docker compose ps \
  catalog-outbox \
  embedding-worker \
  retrieval-worker \
  retrieval-service

print_step "Retrieval HTTP runtime"
check_retrieval_health

print_step "Retrieval migration head"
check_migration_head

print_step "Retrieval Qdrant contract"
check_qdrant_contract

print_step "Stage 9 runtime users"
check_runtime_users

print_step "Stage 9 RabbitMQ consumers"
check_queue_consumers

print_step "Stage 9 structured logging"
check_structured_log catalog-outbox
check_structured_log retrieval-service
check_structured_log retrieval-worker

print_step "Git whitespace"
git diff --check

printf '\nRETRIEVAL STAGE CHECKS PASSED\n'
