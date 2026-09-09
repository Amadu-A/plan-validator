#!/usr/bin/env bash
# scripts/check-gateway.sh
#
# Автоматический quality/runtime gate API Gateway.
#
# --fix синхронизирует dependencies, исправляет Ruff/format, проверяет tests,
# build/start Gateway и выполняет runtime smoke.
#
# --check не устанавливает dependencies, не форматирует и не rebuild'ит service.

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

MODE="${1:---fix}"

REQUIRED_FILES=(
  "services/api-gateway/Dockerfile"
  "services/api-gateway/pyproject.toml"
  "services/api-gateway/src/api_gateway/main.py"
  "services/api-gateway/src/api_gateway/application/internal_service.py"
  "services/api-gateway/src/api_gateway/application/auth_service.py"
  "services/api-gateway/src/api_gateway/application/system_info.py"
  "services/api-gateway/src/api_gateway/core/container.py"
  "services/api-gateway/src/api_gateway/core/settings.py"
  "services/api-gateway/src/api_gateway/infrastructure/http_client.py"
  "services/api-gateway/src/api_gateway/infrastructure/http_context.py"
  "services/api-gateway/src/api_gateway/infrastructure/auth_client.py"
  "services/api-gateway/src/api_gateway/transport/app.py"
  "services/api-gateway/src/api_gateway/transport/auth_schemas.py"
  "services/api-gateway/src/api_gateway/transport/session_cookie.py"
  "services/api-gateway/src/api_gateway/transport/errors.py"
  "services/api-gateway/src/api_gateway/transport/middleware.py"
  "services/api-gateway/src/api_gateway/transport/schemas.py"
  "services/api-gateway/src/api_gateway/transport/routers/api_v1.py"
  "services/api-gateway/src/api_gateway/transport/routers/auth.py"
  "services/api-gateway/src/api_gateway/transport/routers/health.py"
  "services/api-gateway/src/api_gateway/transport/routers/system.py"
  "tests/architecture/test_api_gateway_contract.py"
  "tests/unit/api_gateway/test_settings.py"
  "tests/unit/api_gateway/test_system_info.py"
  "tests/unit/api_gateway/test_http_client.py"
  "tests/transport/api_gateway/test_gateway.py"
  "tests/transport/api_gateway/test_auth.py"
  "docs/API_GATEWAY.md"
)

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
      printf 'Usage: %s [--fix|--check]\n' \
        "$0" >&2
      exit 3
      ;;
  esac
}

check_required_files() {
  local required_file

  for required_file in "${REQUIRED_FILES[@]}"; do
    if [[ ! -f "${required_file}" ]]; then
      printf 'ERROR: required Gateway file is missing: %s\n' \
        "${required_file}" >&2
      exit 4
    fi

    printf '[OK] %s\n' "${required_file}"
  done
}

check_python_dependencies() {
  python - <<'PY'
from importlib.metadata import PackageNotFoundError, version

EXPECTED = {
    "plan-validator-api-gateway": "0.1.0",
    "plan-validator-common": "0.1.0",
    "fastapi": "0.141.1",
    "httpx": "0.28.1",
    "httpx2": "2.12.0",
    "uvicorn": "0.52.1",
    "email-validator": "2.3.0",
    "pytest": "9.1.1",
    "ruff": "0.16.6",
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

print("[OK] API Gateway dependencies are synchronized.")
PY
}

sync_python_dependencies() {
  if check_python_dependencies >/dev/null 2>&1; then
    printf '[OK] API Gateway dependencies already synchronized.\n'
    return 0
  fi

  printf '[FIX] Installing/updating root development dependencies...\n'

  python -m pip install \
    -r requirements-dev.txt

  check_python_dependencies
}

prepare_runtime_directories() {
  mkdir -p var/log

  if [[ ! -w var/log ]]; then
    printf 'ERROR: runtime log directory is not writable: %s\n' \
      "${ROOT_DIR}/var/log" >&2
    exit 5
  fi

  printf '[OK] runtime log root: %s\n' \
    "${ROOT_DIR}/var/log"
}

check_gateway_http() {
  local gateway_port

  gateway_port="${PLAN_VALIDATOR_GATEWAY_HOST_PORT:-8000}"

  curl \
    --fail \
    --silent \
    --show-error \
    --max-time 5 \
    "http://127.0.0.1:${gateway_port}/health/live" \
    >/dev/null

  printf '[OK] Gateway liveness.\n'

  curl \
    --fail \
    --silent \
    --show-error \
    --max-time 5 \
    "http://127.0.0.1:${gateway_port}/health/ready" \
    >/dev/null

  printf '[OK] Gateway readiness.\n'

  curl \
    --fail \
    --silent \
    --show-error \
    --max-time 5 \
    "http://127.0.0.1:${gateway_port}/api/v1/system/info" \
    | python -c '
import json
import sys

payload = json.load(sys.stdin)

assert payload["service"] == "api-gateway"
assert payload["service_version"] == "0.1.0"
assert payload["api_version"] == "v1"

print("[OK] Gateway versioned system endpoint.")
'
}

check_gateway_runtime_user() {
  local container_uid

  container_uid="$(
    docker compose exec -T api-gateway id -u \
      | tr -d '\r'
  )"

  if [[ "${container_uid}" == "0" ]]; then
    printf 'ERROR: API Gateway is running as root.\n' >&2
    exit 6
  fi

  if [[ "${container_uid}" != "${PLAN_VALIDATOR_RUNTIME_UID}" ]]; then
    printf 'ERROR: unexpected Gateway UID: %s, expected %s\n' \
      "${container_uid}" \
      "${PLAN_VALIDATOR_RUNTIME_UID}" >&2
    exit 7
  fi

  printf '[OK] Gateway non-root UID: %s\n' \
    "${container_uid}"
}

check_gateway_file_log() {
  local log_file

  log_file="var/log/api-gateway/api-gateway.log"

  if [[ ! -s "${log_file}" ]]; then
    printf 'ERROR: Gateway JSON log is missing or empty: %s\n' \
      "${log_file}" >&2
    exit 8
  fi

  python - "${log_file}" <<'PY'
import json
import sys
from pathlib import Path

log_path = Path(sys.argv[1])

lines = [
    line
    for line in log_path.read_text(encoding="utf-8").splitlines()
    if line.strip()
]

if not lines:
    raise SystemExit("Gateway log does not contain JSON lines")

payload = json.loads(lines[-1])

required_keys = {
    "timestamp",
    "level",
    "logger",
    "service",
    "message",
}

missing = required_keys - payload.keys()

if missing:
    raise SystemExit(
        f"Gateway log is missing required keys: {sorted(missing)}"
    )

if payload["service"] != "api-gateway":
    raise SystemExit("Gateway log contains unexpected service identity")

print("[OK] Gateway structured file log.")
PY
}

validate_mode

print_step "API Gateway files"
check_required_files

print_step "Required tooling"

require_command curl
require_command docker
require_command python
require_command pytest
require_command ruff

PLAN_VALIDATOR_RUNTIME_UID="${PLAN_VALIDATOR_RUNTIME_UID:-$(id -u)}"
PLAN_VALIDATOR_RUNTIME_GID="${PLAN_VALIDATOR_RUNTIME_GID:-$(id -g)}"

export PLAN_VALIDATOR_RUNTIME_UID
export PLAN_VALIDATOR_RUNTIME_GID

python --version
docker version --format 'Docker {{.Server.Version}}'
docker compose version

if [[ "${MODE}" == "--fix" ]]; then
  print_step "Python dependency automatic synchronization"
  sync_python_dependencies

  print_step "Common/Root automatic fixes"
  ./scripts/check-common.sh --fix
else
  print_step "Python dependency check"
  check_python_dependencies

  print_step "Common/Root immutable check"
  ./scripts/check-common.sh --check

  printf '\nINFO: --check mode: Gateway source/runtime will not be repaired.\n'
fi

print_step "Infrastructure immutable validation"
./scripts/check-infrastructure.sh --check

print_step "Python dependency integrity"
python -m pip check

print_step "API Gateway unit tests"
pytest tests/unit/api_gateway

print_step "API Gateway transport tests"
pytest tests/transport/api_gateway

print_step "API Gateway architecture tests"
pytest tests/architecture

print_step "Docker Compose configuration"
docker compose config --quiet
printf '[OK] docker compose config.\n'

if [[ "${MODE}" == "--fix" ]]; then
  print_step "Runtime directories"
  prepare_runtime_directories

  print_step "API Gateway build/start"
  docker compose up \
    -d \
    --build \
    --wait \
    api-gateway
fi

print_step "API Gateway container"
docker compose ps api-gateway

print_step "API Gateway HTTP runtime"
check_gateway_http

print_step "API Gateway runtime user"
check_gateway_runtime_user

print_step "API Gateway file logging"
check_gateway_file_log

print_step "Git whitespace"
git diff --check

printf '\nAPI GATEWAY CHECKS PASSED\n'