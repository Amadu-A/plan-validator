#!/usr/bin/env bash
# scripts/check-infrastructure.sh
#
# Автоматически исправляет и затем проверяет инфраструктуру Plan Validator.
#
# Режим по умолчанию --fix:
# - запускает Foundation auto-fix;
# - создаёт/восстанавливает sparse `.env`;
# - поднимает/проверяет shared infrastructure;
# - provision'ит RabbitMQ project resources;
# - валидирует Compose;
# - подтягивает и запускает PostgreSQL/Qdrant;
# - проверяет runtime.
#
# Режим --check не должен намеренно изменять configuration/resources.

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

MODE="${1:---fix}"

REQUIRED_FILES=(
  ".env.example"
  "compose.yaml"
  "docs/INFRASTRUCTURE.md"
  "scripts/bootstrap-env.sh"
  "scripts/check-foundation.sh"
  "scripts/preflight-shared.sh"
  "scripts/provision-rabbitmq.sh"
  "scripts/up.sh"
  "tests/architecture/test_infrastructure_contract.py"
)

# Печатает единообразный заголовок validation step.
print_step() {
  local step_name="$1"
  printf '\n=== %s ===\n' "${step_name}"
}

# Проверяет наличие command dependency.
require_command() {
  local command_name="$1"

  if ! command -v "${command_name}" >/dev/null 2>&1; then
    printf 'ERROR: required command not found: %s\n' "${command_name}" >&2
    exit 2
  fi
}

# Проверяет допустимый режим запуска.
validate_mode() {
  case "${MODE}" in
    --fix|--check)
      ;;
    *)
      printf 'ERROR: unsupported mode: %s\n' "${MODE}" >&2
      printf 'Usage: %s [--fix|--check]\n' "$0" >&2
      exit 3
      ;;
  esac
}

# Проверяет файлы, обязательные для infrastructure stage.
check_required_files() {
  local required_file

  for required_file in "${REQUIRED_FILES[@]}"; do
    if [[ ! -f "${required_file}" ]]; then
      printf 'ERROR: required infrastructure file is missing: %s\n' \
        "${required_file}" >&2
      exit 4
    fi

    printf '[OK] %s\n' "${required_file}"
  done
}

# Загружает sparse project environment после его bootstrap/validation.
load_project_environment() {
  if [[ ! -f ".env" ]]; then
    printf 'ERROR: .env is missing.\n' >&2
    exit 5
  fi

  set -a
  # shellcheck disable=SC1091
  source .env
  set +a

  if [[ -z "${PLAN_VALIDATOR_POSTGRES_PASSWORD:-}" ]]; then
    printf 'ERROR: PLAN_VALIDATOR_POSTGRES_PASSWORD is missing.\n' >&2
    exit 6
  fi

  if [[ -z "${PLAN_VALIDATOR_RABBITMQ_PASSWORD:-}" ]]; then
    printf 'ERROR: PLAN_VALIDATOR_RABBITMQ_PASSWORD is missing.\n' >&2
    exit 7
  fi
}

# Проверяет синтаксис всех project shell scripts штатным Bash parser.
check_shell_syntax() {
  local shell_script

  while IFS= read -r -d '' shell_script; do
    bash -n "${shell_script}"
    printf '[OK] bash syntax: %s\n' "${shell_script}"
  done < <(find scripts -type f -name '*.sh' -print0 | sort -z)
}

# Запускает project-specific infrastructure и ждёт container health.
start_project_infrastructure() {
  print_step "Project infrastructure images"

  docker compose pull postgres qdrant

  print_step "Project infrastructure startup"

  docker compose up -d --wait postgres qdrant
}

# Проверяет PostgreSQL не только по container state, но и через pg_isready.
check_postgres_runtime() {
  docker compose exec -T postgres \
    pg_isready \
    -U "${PLAN_VALIDATOR_POSTGRES_USER:-plan_validator}" \
    -d "${PLAN_VALIDATOR_POSTGRES_DB:-plan_validator}"

  printf '[OK] PostgreSQL runtime.\n'
}

# Проверяет реальный Qdrant readiness endpoint через localhost host binding.
check_qdrant_runtime() {
  local qdrant_host_port

  qdrant_host_port="${PLAN_VALIDATOR_QDRANT_HTTP_HOST_PORT:-6335}"

  curl \
    --fail \
    --silent \
    --show-error \
    --max-time 5 \
    "http://127.0.0.1:${qdrant_host_port}/readyz" \
    >/dev/null

  printf '[OK] Qdrant readiness: http://127.0.0.1:%s/readyz\n' \
    "${qdrant_host_port}"
}

validate_mode

print_step "Infrastructure files"
check_required_files

print_step "Required tooling"

require_command bash
require_command curl
require_command docker
require_command openssl

docker version --format 'Docker {{.Server.Version}}'
docker compose version

if [[ "${MODE}" == "--fix" ]]; then
  print_step "Foundation automatic fixes"
  ./scripts/check-foundation.sh

  print_step "Sparse environment automatic bootstrap"
  ./scripts/bootstrap-env.sh
else
  print_step "Foundation check"
  ./scripts/check-foundation.sh --check

  printf '\nINFO: --check mode: infrastructure resources will not be repaired.\n'
fi

load_project_environment

print_step "Shell syntax"
check_shell_syntax

if [[ "${MODE}" == "--fix" ]]; then
  ./scripts/preflight-shared.sh --fix
  ./scripts/provision-rabbitmq.sh --fix
else
  ./scripts/preflight-shared.sh --check
  ./scripts/provision-rabbitmq.sh --check
fi

print_step "Docker Compose configuration"
docker compose config --quiet
printf '[OK] docker compose config.\n'

if [[ "${MODE}" == "--fix" ]]; then
  start_project_infrastructure
fi

print_step "Project containers"
docker compose ps

print_step "PostgreSQL runtime"
check_postgres_runtime

print_step "Qdrant runtime"
check_qdrant_runtime

print_step "Architecture tests"
pytest tests/architecture

print_step "Git whitespace"
git diff --check

printf '\nINFRASTRUCTURE CHECKS PASSED\n'