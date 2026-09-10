#!/usr/bin/env bash
# scripts/check-catalog.sh
#
# Автоматический quality/migration/runtime gate Catalog stage.
#
# --fix выполняет auto-fix, build, migration и mutating runtime E2E.
# --check ничего намеренно не изменяет.

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

check_python_dependencies() {
  python - <<'PY'
from importlib.metadata import PackageNotFoundError, version

EXPECTED = {
    "plan-validator-catalog-service": "0.1.0",
    "plan-validator-api-gateway": "0.1.0",
    "plan-validator-auth-service": "0.1.0",
    "plan-validator-common": "0.1.0",
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

import catalog_service  # noqa: E402,F401

print("[OK] Catalog dependencies are synchronized.")
PY
}

sync_python_dependencies() {
  if check_python_dependencies >/dev/null 2>&1; then
    printf '[OK] Catalog dependencies already synchronized.\n'
    return 0
  fi

  printf '[FIX] Installing/updating root development dependencies...\n'

  python -m pip install -r requirements-dev.txt

  check_python_dependencies
}

prepare_runtime_directories() {
  mkdir -p \
    var/log/catalog-service \
    var/log/api-gateway

  printf '[OK] Catalog runtime log directories prepared.\n'
}

check_catalog_health() {
  docker compose exec -T catalog-service \
    python -c "
import urllib.request
urllib.request.urlopen(
    'http://127.0.0.1:8000/health/ready',
    timeout=5,
).read()
"

  printf '[OK] Catalog Service readiness.\n'
}

check_migration_head() {
  local migration_output

  migration_output="$(
    docker compose exec -T catalog-service \
      alembic \
      -c services/catalog-service/alembic.ini \
      current
  )"

  printf '%s\n' "${migration_output}"

  if ! grep -Fq "(head)" <<<"${migration_output}"; then
    printf 'ERROR: Catalog database is not at Alembic head.\n' >&2
    exit 5
  fi

  printf '[OK] Catalog migration head.\n'
}

check_runtime_user() {
  local container_uid

  container_uid="$(
    docker compose exec -T catalog-service id -u \
      | tr -d '\r'
  )"

  if [[ "${container_uid}" == "0" ]]; then
    printf 'ERROR: Catalog Service is running as root.\n' >&2
    exit 6
  fi

  printf '[OK] Catalog Service non-root UID: %s\n' \
    "${container_uid}"
}

check_catalog_log() {
  local log_file

  log_file="var/log/catalog-service/catalog-service.log"

  if [[ ! -s "${log_file}" ]]; then
    printf 'ERROR: Catalog structured log is missing: %s\n' \
      "${log_file}" >&2
    exit 7
  fi

  python - "${log_file}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])

lines = [
    line
    for line in path.read_text(encoding="utf-8").splitlines()
    if line.strip()
]

if not lines:
    raise SystemExit("Catalog log is empty")

payload = json.loads(lines[-1])

assert payload["service"] == "catalog-service"
assert "timestamp" in payload
assert "level" in payload
assert "message" in payload

print("[OK] Catalog structured file log.")
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

if [[ "${MODE}" == "--fix" ]]; then
  print_step "Catalog dependency synchronization"
  sync_python_dependencies

  print_step "Automatic Ruff/format"
  ./scripts/check-common.sh --fix
else
  print_step "Catalog dependency check"
  check_python_dependencies

  print_step "Immutable Common check"
  ./scripts/check-common.sh --check

  printf '\nINFO: --check mode does not migrate/rebuild Catalog.\n'
fi

print_step "Infrastructure contract"
./scripts/check-infrastructure.sh --check

print_step "Authentication contract"
./scripts/check-auth.sh --check

print_step "Catalog unit tests"
pytest tests/unit/catalog_service

print_step "Gateway transport tests"
pytest tests/transport/api_gateway

print_step "Architecture tests"
pytest tests/architecture

print_step "Compose validation"
docker compose config --quiet

if [[ "${MODE}" == "--fix" ]]; then
  print_step "Runtime directories"
  prepare_runtime_directories

  print_step "Build Catalog and Gateway images"
  docker compose build \
    catalog-service \
    api-gateway

  print_step "Catalog migrations"
  docker compose \
    --profile ops \
    run \
    --rm \
    catalog-migrate

  print_step "Catalog/Gateway startup"
  docker compose up \
    -d \
    --wait \
    catalog-service \
    api-gateway
fi

print_step "Catalog container"
docker compose ps catalog-service

print_step "Catalog readiness"
check_catalog_health

print_step "Catalog migration head"
check_migration_head

print_step "Catalog runtime user"
check_runtime_user

print_step "Catalog structured logging"
check_catalog_log

if [[ "${MODE}" == "--fix" ]]; then
  print_step "Runtime Catalog E2E"
  pytest tests/runtime/catalog_service
else
  printf '\nINFO: mutating Catalog E2E skipped in immutable --check mode.\n'
fi

print_step "Git whitespace"
git diff --check

printf '\nCATALOG CHECKS PASSED\n'