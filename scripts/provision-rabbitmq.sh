#!/usr/bin/env bash
# scripts/provision-rabbitmq.sh
#
# Идемпотентно создаёт project-specific RabbitMQ resources внутри shared broker.
# Все policies ограничены virtual host /plan-validator.
#
# TTL ограничивает только queued/ready messages. Unacked execution ограничивается
# отдельно application deadline, lease/heartbeat, reconciliation и process drain.

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"
MODE="${1:---fix}"

SHARED_NETWORK_NAME="${PLAN_VALIDATOR_SHARED_NETWORK_NAME:-ai-shared}"
RABBITMQ_USER="${PLAN_VALIDATOR_RABBITMQ_USER:-plan_validator}"
RABBITMQ_VHOST="${PLAN_VALIDATOR_RABBITMQ_VHOST:-/plan-validator}"
RABBITMQ_CONTAINER_ID=""

WORK_QUEUE_POLICY_NAME="plan-validator-work-queue-ttl"
WORK_QUEUE_POLICY_PATTERN='^(plan-validator\.gpu\.embedding|plan-validator\.retrieval\.index|plan-validator\.context\.index)$'
WORK_QUEUE_POLICY_PRIORITY="100"
WORK_QUEUE_TTL_MS=""

CATALOG_QUEUE_POLICY_NAME="plan-validator-catalog-event-queue-ttl"
CATALOG_QUEUE_POLICY_PATTERN='^plan-validator\.retrieval\.catalog-events$'
CATALOG_QUEUE_POLICY_PRIORITY="90"
CATALOG_QUEUE_TTL_MS=""

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

require_command() {
  local command_name="$1"

  if ! command -v "${command_name}" >/dev/null 2>&1; then
    printf 'ERROR: required command not found: %s\n' \
      "${command_name}" >&2
    exit 3
  fi
}

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

load_policy_settings() {
  WORK_QUEUE_TTL_MS="${PLAN_VALIDATOR_RABBITMQ_WORK_QUEUE_TTL_MS:-900000}"
  CATALOG_QUEUE_TTL_MS="${PLAN_VALIDATOR_RABBITMQ_CATALOG_EVENT_QUEUE_TTL_MS:-604800000}"

  if [[ ! "${WORK_QUEUE_TTL_MS}" =~ ^[0-9]+$ ]]; then
    printf 'ERROR: invalid work queue TTL: %s\n' \
      "${WORK_QUEUE_TTL_MS}" >&2
    exit 6
  fi

  if [[ ! "${CATALOG_QUEUE_TTL_MS}" =~ ^[0-9]+$ ]]; then
    printf 'ERROR: invalid Catalog event queue TTL: %s\n' \
      "${CATALOG_QUEUE_TTL_MS}" >&2
    exit 7
  fi

  if (( WORK_QUEUE_TTL_MS < 60000 )); then
    printf 'ERROR: work queue TTL must be at least 60000 ms.\n' >&2
    exit 8
  fi

  if (( CATALOG_QUEUE_TTL_MS <= WORK_QUEUE_TTL_MS )); then
    printf 'ERROR: Catalog lifecycle TTL must exceed work queue TTL.\n' >&2
    exit 9
  fi
}

discover_shared_rabbitmq() {
  local -a container_ids=()
  local health_state
  local container_name

  if ! docker network inspect "${SHARED_NETWORK_NAME}" >/dev/null 2>&1; then
    printf 'ERROR: shared Docker network is missing: %s\n' \
      "${SHARED_NETWORK_NAME}" >&2
    exit 10
  fi

  mapfile -t container_ids < <(
    docker ps \
      --filter "network=${SHARED_NETWORK_NAME}" \
      --filter 'label=com.docker.compose.service=rabbitmq' \
      --format '{{.ID}}'
  )

  if (( ${#container_ids[@]} == 0 )); then
    printf 'ERROR: shared RabbitMQ container is not running.\n' >&2
    exit 11
  fi

  if (( ${#container_ids[@]} > 1 )); then
    printf 'ERROR: multiple shared RabbitMQ containers were found.\n' >&2
    exit 12
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
    exit 13
  fi

  container_name="$(
    docker inspect \
      --format '{{.Name}}' \
      "${RABBITMQ_CONTAINER_ID}"
  )"

  container_name="${container_name#/}"

  printf '[OK] shared RabbitMQ container: %s\n' \
    "${container_name}"
}

rabbitmqctl_shared() {
  docker exec \
    "${RABBITMQ_CONTAINER_ID}" \
    rabbitmqctl \
    "$@"
}

rabbitmq_vhost_exists() {
  local output
  local vhost_name

  if output="$(
    rabbitmqctl_shared \
      list_vhosts \
      --silent
  )"; then
    :
  else
    printf 'ERROR: failed to query RabbitMQ virtual hosts.\n' >&2
    return 2
  fi

  while IFS= read -r vhost_name; do
    if [[ "${vhost_name}" == "${RABBITMQ_VHOST}" ]]; then
      return 0
    fi
  done <<<"${output}"

  return 1
}

rabbitmq_user_exists() {
  local output
  local username
  local rest

  if output="$(
    rabbitmqctl_shared \
      list_users \
      --silent
  )"; then
    :
  else
    printf 'ERROR: failed to query RabbitMQ users.\n' >&2
    return 2
  fi

  while read -r username rest; do
    if [[ "${username}" == "${RABBITMQ_USER}" ]]; then
      return 0
    fi
  done <<<"${output}"

  return 1
}

rabbitmq_permissions_exist() {
  local output
  local vhost_name
  local rest

  if output="$(
    rabbitmqctl_shared \
      list_user_permissions \
      "${RABBITMQ_USER}"
  )"; then
    :
  else
    printf 'ERROR: failed to query RabbitMQ user permissions.\n' >&2
    return 2
  fi

  while read -r vhost_name rest; do
    if [[ "${vhost_name}" == "${RABBITMQ_VHOST}" ]]; then
      return 0
    fi
  done <<<"${output}"

  return 1
}

rabbitmq_policy_matches() {
  local expected_name="$1"
  local expected_pattern="$2"
  local expected_ttl="$3"
  local expected_priority="$4"

  local output
  local vhost_name
  local policy_name
  local pattern
  local apply_to
  local definition
  local priority
  local compact_definition

  if output="$(
    rabbitmqctl_shared \
      list_policies \
      -p "${RABBITMQ_VHOST}" \
      --silent
  )"; then
    :
  else
    printf 'ERROR: failed to query RabbitMQ policies.\n' >&2
    return 2
  fi

  while IFS=$'\t' read -r \
    vhost_name \
    policy_name \
    pattern \
    apply_to \
    definition \
    priority
  do
    if [[ "${vhost_name}" != "${RABBITMQ_VHOST}" ]]; then
      continue
    fi

    if [[ "${policy_name}" != "${expected_name}" ]]; then
      continue
    fi

    compact_definition="$(
      printf '%s' "${definition}" \
        | tr -d '[:space:]'
    )"

    if [[ \
      "${pattern}" == "${expected_pattern}" \
      && "${apply_to}" == "queues" \
      && "${priority}" == "${expected_priority}" \
      && "${compact_definition}" == *"\"message-ttl\":${expected_ttl}"* \
    ]]; then
      return 0
    fi

    return 1
  done <<<"${output}"

  return 1
}

apply_queue_policy() {
  local policy_name="$1"
  local pattern="$2"
  local ttl_ms="$3"
  local priority="$4"

  rabbitmqctl_shared \
    set_policy \
    -p "${RABBITMQ_VHOST}" \
    --priority "${priority}" \
    --apply-to queues \
    "${policy_name}" \
    "${pattern}" \
    "{\"message-ttl\":${ttl_ms}}"

  printf '[FIX] RabbitMQ policy synchronized: %s ttl=%sms\n' \
    "${policy_name}" \
    "${ttl_ms}"
}

apply_rabbitmq_fixes() {
  local resource_status

  printf '\n=== RabbitMQ project provisioning ===\n'

  if rabbitmq_vhost_exists; then
    printf '[OK] RabbitMQ vhost exists: %s\n' \
      "${RABBITMQ_VHOST}"
  else
    resource_status=$?

    if (( resource_status != 1 )); then
      printf 'ERROR: unable to determine RabbitMQ vhost state.\n' >&2
      exit 14
    fi

    rabbitmqctl_shared \
      add_vhost \
      "${RABBITMQ_VHOST}"

    printf '[FIX] RabbitMQ vhost created: %s\n' \
      "${RABBITMQ_VHOST}"
  fi

  if rabbitmq_user_exists; then
    rabbitmqctl_shared \
      change_password \
      "${RABBITMQ_USER}" \
      "${PLAN_VALIDATOR_RABBITMQ_PASSWORD}"

    printf '[FIX] RabbitMQ application password synchronized: %s\n' \
      "${RABBITMQ_USER}"
  else
    resource_status=$?

    if (( resource_status != 1 )); then
      printf 'ERROR: unable to determine RabbitMQ user state.\n' >&2
      exit 15
    fi

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

  apply_queue_policy \
    "${WORK_QUEUE_POLICY_NAME}" \
    "${WORK_QUEUE_POLICY_PATTERN}" \
    "${WORK_QUEUE_TTL_MS}" \
    "${WORK_QUEUE_POLICY_PRIORITY}"

  apply_queue_policy \
    "${CATALOG_QUEUE_POLICY_NAME}" \
    "${CATALOG_QUEUE_POLICY_PATTERN}" \
    "${CATALOG_QUEUE_TTL_MS}" \
    "${CATALOG_QUEUE_POLICY_PRIORITY}"
}

check_rabbitmq_project_resources() {
  local resource_status

  printf '\n=== RabbitMQ project validation ===\n'

  if rabbitmq_vhost_exists; then
    printf '[OK] RabbitMQ vhost: %s\n' \
      "${RABBITMQ_VHOST}"
  else
    resource_status=$?

    if (( resource_status == 1 )); then
      printf 'ERROR: RabbitMQ vhost is missing: %s\n' \
        "${RABBITMQ_VHOST}" >&2
      exit 16
    fi

    printf 'ERROR: RabbitMQ vhost state could not be validated.\n' >&2
    exit 17
  fi

  if rabbitmq_user_exists; then
    printf '[OK] RabbitMQ user: %s\n' \
      "${RABBITMQ_USER}"
  else
    resource_status=$?

    if (( resource_status == 1 )); then
      printf 'ERROR: RabbitMQ user is missing: %s\n' \
        "${RABBITMQ_USER}" >&2
      exit 18
    fi

    printf 'ERROR: RabbitMQ user state could not be validated.\n' >&2
    exit 19
  fi

  rabbitmqctl_shared \
    authenticate_user \
    "${RABBITMQ_USER}" \
    "${PLAN_VALIDATOR_RABBITMQ_PASSWORD}" \
    >/dev/null

  printf '[OK] RabbitMQ authentication.\n'

  if rabbitmq_permissions_exist; then
    printf '[OK] RabbitMQ vhost permissions.\n'
  else
    resource_status=$?

    if (( resource_status == 1 )); then
      printf 'ERROR: RabbitMQ permissions are missing for vhost: %s\n' \
        "${RABBITMQ_VHOST}" >&2
      exit 20
    fi

    printf 'ERROR: RabbitMQ permissions state could not be validated.\n' >&2
    exit 21
  fi
}

check_queue_policies() {
  local policy_status

  printf '\n=== RabbitMQ queue TTL policies ===\n'

  if rabbitmq_policy_matches \
    "${WORK_QUEUE_POLICY_NAME}" \
    "${WORK_QUEUE_POLICY_PATTERN}" \
    "${WORK_QUEUE_TTL_MS}" \
    "${WORK_QUEUE_POLICY_PRIORITY}"
  then
    printf '[OK] work queue TTL policy: %sms\n' \
      "${WORK_QUEUE_TTL_MS}"
  else
    policy_status=$?

    if (( policy_status == 2 )); then
      exit 22
    fi

    printf 'ERROR: work queue TTL policy is missing or invalid.\n' >&2
    exit 23
  fi

  if rabbitmq_policy_matches \
    "${CATALOG_QUEUE_POLICY_NAME}" \
    "${CATALOG_QUEUE_POLICY_PATTERN}" \
    "${CATALOG_QUEUE_TTL_MS}" \
    "${CATALOG_QUEUE_POLICY_PRIORITY}"
  then
    printf '[OK] Catalog lifecycle queue TTL policy: %sms\n' \
      "${CATALOG_QUEUE_TTL_MS}"
  else
    policy_status=$?

    if (( policy_status == 2 )); then
      exit 24
    fi

    printf 'ERROR: Catalog lifecycle queue TTL policy is missing or invalid.\n' >&2
    exit 25
  fi
}

validate_mode

require_command docker
require_command tr

load_project_environment
load_policy_settings
discover_shared_rabbitmq

if [[ "${MODE}" == "--fix" ]]; then
  apply_rabbitmq_fixes
fi

check_rabbitmq_project_resources
check_queue_policies

printf '\nRABBITMQ PROJECT PROVISIONING PASSED\n'