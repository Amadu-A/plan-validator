#!/usr/bin/env bash
# scripts/provision-rabbitmq.sh
#
# Идемпотентно создаёт project-specific RabbitMQ resources внутри shared broker.
#
# Bootstrap выполняется host-side через `rabbitmqctl` в shared RabbitMQ
# container. Bootstrap-admin credentials не копируются в plan-validator.
#
# Application получает:
# - отдельный vhost;
# - отдельного user;
# - только project password из private `.env`.

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"
MODE="${1:---fix}"

SHARED_INFRA_DIR="$(
  realpath -m \
    "${PLAN_VALIDATOR_SHARED_INFRA_DIR:-${ROOT_DIR}/../shared_infrasktructure}"
)"

RABBITMQ_USER="${PLAN_VALIDATOR_RABBITMQ_USER:-plan_validator}"
RABBITMQ_VHOST="${PLAN_VALIDATOR_RABBITMQ_VHOST:-/plan-validator}"

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

# Загружает private project environment без вывода secret values.
load_project_environment() {
  if [[ ! -f "${ENV_FILE}" ]]; then
    printf 'ERROR: project .env does not exist. Run bootstrap-env.sh first.\n' >&2
    exit 3
  fi

  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a

  if [[ -z "${PLAN_VALIDATOR_RABBITMQ_PASSWORD:-}" ]]; then
    printf 'ERROR: PLAN_VALIDATOR_RABBITMQ_PASSWORD is not configured.\n' >&2
    exit 4
  fi
}

# Выполняет rabbitmqctl внутри broker, которым владеет shared infrastructure.
rabbitmqctl_shared() {
  (
    cd "${SHARED_INFRA_DIR}"

    docker compose exec -T rabbitmq \
      rabbitmqctl "$@"
  )
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
    exit 5
  fi

  printf '[OK] RabbitMQ vhost: %s\n' "${RABBITMQ_VHOST}"

  if ! rabbitmq_user_exists; then
    printf 'ERROR: RabbitMQ user is missing: %s\n' "${RABBITMQ_USER}" >&2
    exit 6
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
    exit 7
  fi

  printf '[OK] RabbitMQ vhost permissions.\n'
}

validate_mode
load_project_environment

if [[ ! -d "${SHARED_INFRA_DIR}" ]]; then
  printf 'ERROR: shared infrastructure directory not found: %s\n' \
    "${SHARED_INFRA_DIR}" >&2
  exit 8
fi

if [[ "${MODE}" == "--fix" ]]; then
  apply_rabbitmq_fixes
fi

check_rabbitmq_project_resources

printf '\nRABBITMQ PROJECT PROVISIONING PASSED\n'