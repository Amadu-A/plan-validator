#!/usr/bin/env bash
# scripts/provision-rabbitmq.sh
#
# Идемпотентно создаёт project-specific RabbitMQ resources внутри уже
# работающего shared broker. Доступ к broker выполняется напрямую через Docker
# runtime, без зависимости от локального checkout shared infrastructure.

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"
MODE="${1:---fix}"

SHARED_NETWORK_NAME="${PLAN_VALIDATOR_SHARED_NETWORK_NAME:-ai-shared}"
RABBITMQ_USER="${PLAN_VALIDATOR_RABBITMQ_USER:-plan_validator}"
RABBITMQ_VHOST="${PLAN_VALIDATOR_RABBITMQ_VHOST:-/plan-validator}"
RABBITMQ_CONTAINER_ID=""

# Проверяет допустимый режим provisioning.
validate_mode() {
  case "${MODE}" in
    --fix|--check)
      ;;
    *)
      printf 'ERROR: unsupported mode: %s\n' "${MODE}" >&2
      printf 'Usage: %s [--fix|--check]\n' "$0" >&2
      exit 2
      ;;
  esac
}

# Проверяет наличие обязательной host command.
require_command() {
  local command_name="$1"

  if ! command -v "${command_name}" >/dev/null 2>&1; then
    printf 'ERROR: required command not found: %s\n' "${command_name}" >&2
    exit 3
  fi
}

# Загружает private project environment без вывода secret values.
load_project_environment() {
  if [[ ! -f "${ENV_FILE}" ]]; then
    printf 'ERROR: project .env does not exist. Run bootstrap-env.sh first.\n' >&2
    exit 4
  fi

  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a

  if [[ -z "${PLAN_VALIDATOR_RABBITMQ_PASSWORD:-}" ]]; then
    printf 'ERROR: PLAN_VALIDATOR_RABBITMQ_PASSWORD is not configured.\n' >&2
    exit 5
  fi
}

# Находит единственный running RabbitMQ container внутри shared network.
discover_shared_rabbitmq() {
  local -a container_ids=()
  local health_state
  local container_name

  if ! docker network inspect "${SHARED_NETWORK_NAME}" >/dev/null 2>&1; then
    printf 'ERROR: shared Docker network is missing: %s\n' \
      "${SHARED_NETWORK_NAME}" >&2
    exit 6
  fi

  mapfile -t container_ids < <(
    docker ps \
      --filter "network=${SHARED_NETWORK_NAME}" \
      --filter 'label=com.docker.compose.service=rabbitmq' \
      --format '{{.ID}}'
  )

  if (( ${#container_ids[@]} == 0 )); then
    printf 'ERROR: shared RabbitMQ container is not running.\n' >&2
    exit 7
  fi

  if (( ${#container_ids[@]} > 1 )); then
    printf 'ERROR: multiple shared RabbitMQ containers were found.\n' >&2
    exit 8
  fi

  RABBITMQ_CONTAINER_ID="${container_ids[0]}"

  health_state="$(
    docker inspect \
      --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' \
      "${RABBITMQ_CONTAINER_ID}"
  )"

  if [[ "${health_state}" != "none" && "${health_state}" != "healthy" ]]; then
    printf 'ERROR: shared RabbitMQ is not healthy: %s\n' \
      "${health_state}" >&2
    exit 9
  fi

  container_name="$(
    docker inspect \
      --format '{{.Name}}' \
      "${RABBITMQ_CONTAINER_ID}" \
      | sed 's#^/##'
  )"

  printf '[OK] shared RabbitMQ container: %s\n' "${container_name}"
}

# Выполняет rabbitmqctl внутри найденного shared RabbitMQ container.
rabbitmqctl_shared() {
  docker exec "${RABBITMQ_CONTAINER_ID}" rabbitmqctl "$@"
}

# Определяет наличие project virtual host.
rabbitmq_vhost_exists() {
  rabbitmqctl_shared list_vhosts --silent \
    | grep -Fxq "${RABBITMQ_VHOST}"
}

# Определяет наличие project application user.
rabbitmq_user_exists() {
  rabbitmqctl_shared list_users --silent \
    | awk '{print $1}' \
    | grep -Fxq "${RABBITMQ_USER}"
}

# Создаёт/синхронизирует vhost, application user и permissions.
apply_rabbitmq_fixes() {
  printf '\n=== RabbitMQ project provisioning ===\n'

  if rabbitmq_vhost_exists; then
    printf '[OK] RabbitMQ vhost exists: %s\n' "${RABBITMQ_VHOST}"
  else
    rabbitmqctl_shared add_vhost "${RABBITMQ_VHOST}"
    printf '[FIX] RabbitMQ vhost created: %s\n' "${RABBITMQ_VHOST}"
  fi

  if rabbitmq_user_exists; then
    rabbitmqctl_shared \
      change_password \
      "${RABBITMQ_USER}" \
      "${PLAN_VALIDATOR_RABBITMQ_PASSWORD}"

    printf '[FIX] RabbitMQ application password synchronized: %s\n' \
      "${RABBITMQ_USER}"
  else
    rabbitmqctl_shared \
      add_user \
      "${RABBITMQ_USER}" \
      "${PLAN_VALIDATOR_RABBITMQ_PASSWORD}"

    printf '[FIX] RabbitMQ application user created: %s\n' \
      "${RABBITMQ_USER}"
  fi

  rabbitmqctl_shared \
    set_permissions \
    -p "${RABBITMQ_VHOST}" \
    "${RABBITMQ_USER}" \
    '.*' \
    '.*' \
    '.*'

  printf '[FIX] RabbitMQ permissions synchronized.\n'
}

# Проверяет существование resources, authentication и vhost permissions.
check_rabbitmq_project_resources() {
  printf '\n=== RabbitMQ project validation ===\n'

  if ! rabbitmq_vhost_exists; then
    printf 'ERROR: RabbitMQ vhost is missing: %s\n' "${RABBITMQ_VHOST}" >&2
    exit 10
  fi

  printf '[OK] RabbitMQ vhost: %s\n' "${RABBITMQ_VHOST}"

  if ! rabbitmq_user_exists; then
    printf 'ERROR: RabbitMQ user is missing: %s\n' "${RABBITMQ_USER}" >&2
    exit 11
  fi

  printf '[OK] RabbitMQ user: %s\n' "${RABBITMQ_USER}"

  rabbitmqctl_shared \
    authenticate_user \
    "${RABBITMQ_USER}" \
    "${PLAN_VALIDATOR_RABBITMQ_PASSWORD}" \
    >/dev/null

  printf '[OK] RabbitMQ authentication.\n'

  if ! rabbitmqctl_shared list_user_permissions "${RABBITMQ_USER}" \
    | grep -Fq "${RABBITMQ_VHOST}"; then
    printf 'ERROR: RabbitMQ permissions are missing for vhost: %s\n' \
      "${RABBITMQ_VHOST}" >&2
    exit 12
  fi

  printf '[OK] RabbitMQ vhost permissions.\n'
}

validate_mode

require_command awk
require_command docker
require_command grep
require_command sed

load_project_environment
discover_shared_rabbitmq

if [[ "${MODE}" == "--fix" ]]; then
  apply_rabbitmq_fixes
fi

check_rabbitmq_project_resources

printf '\nRABBITMQ PROJECT PROVISIONING PASSED\n'