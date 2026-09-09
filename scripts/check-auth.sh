#!/usr/bin/env bash
# scripts/check-auth.sh
#
# Автоматический quality/migration/runtime gate Authentication stage.
#
# --fix:
# - синхронизирует dependencies;
# - запускает auto-fix;
# - проверяет предыдущие contracts;
# - build Auth/Gateway;
# - явно выполняет Alembic migration;
# - запускает services;
# - выполняет runtime auth E2E с cleanup test data.
#
# --check не ставит dependencies, не форматирует, не мигрирует и не rebuild'ит.

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

check_python_dependencies() {
  python - <<'PY'
from importlib.metadata import PackageNotFoundError, version

EXPECTED = {
    "plan-validator-auth-service": "0.1.0",
    "plan-validator-api-gateway": "0.1.0",
    "plan-validator-common": "0.1.0",
    "SQLAlchemy": "2.0.52",
    "alembic": "1.19.2",
    "psycopg": "3.3.5",
    "argon2-cffi": "25.1.0",
    "email-validator": "2.3.0",
    "httpx2": "2.12.0",
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

import auth_service  # noqa: E402,F401

print("[OK] Authentication dependencies are synchronized.")
PY
}

sync_python_dependencies() {
  if check_python_dependencies >/dev/null 2>&1; then
    printf '[OK] Authentication dependencies already synchronized.\n'
    return 0
  fi

  printf '[FIX] Installing/updating root development dependencies...\n'

  python -m pip install \
    -r requirements-dev.txt

  check_python_dependencies
}

prepare_runtime_directories() {
  mkdir -p \
    var/log/auth-service \
    var/log/api-gateway

  printf '[OK] runtime log directories prepared.\n'
}

check_auth_health() {
  docker compose exec -T auth-service \
    python -c "
import urllib.request
urllib.request.urlopen(
    'http://127.0.0.1:8000/health/ready',
    timeout=5,
).read()
"

  printf '[OK] Authentication Service readiness.\n'
}

check_migration_head() {
  local migration_output

  migration_output="$(
    docker compose exec -T auth-service \
      alembic \
      -c services/auth-service/alembic.ini \
      current
  )"

  printf '%s\n' "${migration_output}"

  if ! grep -Fq "(head)" <<<"${migration_output}"; then
    printf 'ERROR: Auth database is not at Alembic head.\n' >&2
    exit 5
  fi

  printf '[OK] Authentication migration head.\n'
}

check_auth_runtime_user() {
  local container_uid

  container_uid="$(
    docker compose exec -T auth-service id -u \
      | tr -d '\r'
  )"

  if [[ "${container_uid}" == "0" ]]; then
    printf 'ERROR: Auth Service is running as root.\n' >&2
    exit 6
  fi

  printf '[OK] Auth Service non-root UID: %s\n' \
    "${container_uid}"
}

check_auth_log() {
  local log_file

  log_file="var/log/auth-service/auth-service.log"

  if [[ ! -s "${log_file}" ]]; then
    printf 'ERROR: Auth structured log is missing: %s\n' \
      "${log_file}" >&2
    exit 7
  fi

  python - "${log_file}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])

last_line = [
    line
    for line in path.read_text(encoding="utf-8").splitlines()
    if line.strip()
][-1]

payload = json.loads(last_line)

assert payload["service"] == "auth-service"
assert "timestamp" in payload
assert "level" in payload
assert "message" in payload

print("[OK] Authentication structured file log.")
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
  print_step "Authentication dependency synchronization"
  sync_python_dependencies

  print_step "Automatic Ruff/format"
  ./scripts/check-common.sh --fix
else
  print_step "Authentication dependency check"
  check_python_dependencies

  print_step "Immutable Common check"
  ./scripts/check-common.sh --check

  printf '\nINFO: --check mode does not run migrations or rebuild containers.\n'
fi

print_step "Infrastructure contract"
./scripts/check-infrastructure.sh --check

print_step "Gateway source/runtime contract"
./scripts/check-gateway.sh --check

print_step "Authentication unit tests"
pytest tests/unit/auth_service

print_step "Gateway authentication transport tests"
pytest tests/transport/api_gateway

print_step "Architecture tests"
pytest tests/architecture

print_step "Compose validation"
docker compose config --quiet

if [[ "${MODE}" == "--fix" ]]; then
  print_step "Runtime directories"
  prepare_runtime_directories

  print_step "Build Authentication and Gateway images"
  docker compose build \
    auth-service \
    api-gateway

  print_step "Authentication migrations"
  docker compose \
    --profile ops \
    run \
    --rm \
    auth-migrate

  print_step "Authentication/Gateway startup"
  docker compose up \
    -d \
    --wait \
    auth-service \
    api-gateway
fi

print_step "Authentication container"
docker compose ps auth-service

print_step "Authentication readiness"
check_auth_health

print_step "Authentication migration head"
check_migration_head

print_step "Authentication runtime user"
check_auth_runtime_user

print_step "Authentication file logging"
check_auth_log

if [[ "${MODE}" == "--fix" ]]; then
  print_step "Runtime Auth E2E"
  pytest tests/runtime/auth_service
else
  printf '\nINFO: mutating Auth E2E skipped in immutable --check mode.\n'
fi

print_step "Git whitespace"
git diff --check

printf '\nAUTHENTICATION CHECKS PASSED\n'