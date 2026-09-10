#!/usr/bin/env bash
# scripts/preflight-shared.sh
#
# Проверяет shared infrastructure через её фактический Docker runtime.
# Plan Validator не требует локальный checkout shared repository и не управляет
# lifecycle shared stack. В режиме --fix разрешено только подтянуть required
# Ollama model в уже работающий shared Ollama container.

set -Eeuo pipefail

MODE="${1:---fix}"
SHARED_NETWORK_NAME="${PLAN_VALIDATOR_SHARED_NETWORK_NAME:-ai-shared}"
OLLAMA_MODEL="${PLAN_VALIDATOR_OLLAMA_MODEL:-qwen3-vl:8b-instruct}"

RABBITMQ_CONTAINER_ID=""
OLLAMA_CONTAINER_ID=""
N8N_CONTAINER_ID=""

# Проверяет допустимый режим работы preflight.
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

# Находит ровно один running shared container по Compose service label.
find_shared_container() {
  local service_name="$1"
  local -a container_ids=()

  mapfile -t container_ids < <(
    docker ps \
      --filter "network=${SHARED_NETWORK_NAME}" \
      --filter "label=com.docker.compose.service=${service_name}" \
      --format '{{.ID}}'
  )

  if (( ${#container_ids[@]} == 0 )); then
    printf 'ERROR: shared service is not running: %s\n' "${service_name}" >&2
    return 1
  fi

  if (( ${#container_ids[@]} > 1 )); then
    printf 'ERROR: multiple shared containers found for service: %s\n' \
      "${service_name}" >&2
    return 1
  fi

  printf '%s\n' "${container_ids[0]}"
}

# Проверяет running/health state конкретного shared container.
check_container_runtime() {
  local service_name="$1"
  local container_id="$2"
  local running_state
  local health_state
  local container_name

  running_state="$(
    docker inspect \
      --format '{{.State.Running}}' \
      "${container_id}"
  )"

  if [[ "${running_state}" != "true" ]]; then
    printf 'ERROR: shared service is not running: %s\n' "${service_name}" >&2
    return 1
  fi

  health_state="$(
    docker inspect \
      --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' \
      "${container_id}"
  )"

  if [[ "${health_state}" != "none" && "${health_state}" != "healthy" ]]; then
    printf 'ERROR: shared service is not healthy: %s (%s)\n' \
      "${service_name}" \
      "${health_state}" >&2
    return 1
  fi

  container_name="$(
    docker inspect \
      --format '{{.Name}}' \
      "${container_id}" \
      | sed 's#^/##'
  )"

  printf '[OK] shared service: %s (%s)\n' \
    "${service_name}" \
    "${container_name}"
}

# Находит и валидирует mandatory shared services внутри external network.
discover_shared_runtime() {
  printf '\n=== Shared infrastructure runtime ===\n'

  if ! docker network inspect "${SHARED_NETWORK_NAME}" >/dev/null 2>&1; then
    printf 'ERROR: shared Docker network is missing: %s\n' \
      "${SHARED_NETWORK_NAME}" >&2
    printf 'Start shared infrastructure before Plan Validator.\n' >&2
    exit 4
  fi

  printf '[OK] shared Docker network: %s\n' "${SHARED_NETWORK_NAME}"

  RABBITMQ_CONTAINER_ID="$(find_shared_container rabbitmq)"
  OLLAMA_CONTAINER_ID="$(find_shared_container ollama)"
  N8N_CONTAINER_ID="$(find_shared_container n8n)"

  check_container_runtime rabbitmq "${RABBITMQ_CONTAINER_ID}"
  check_container_runtime ollama "${OLLAMA_CONTAINER_ID}"
  check_container_runtime n8n "${N8N_CONTAINER_ID}"
}

# Проверяет наличие required Ollama model в shared Ollama runtime.
ollama_model_exists() {
  local installed_models

  installed_models="$(
    docker exec "${OLLAMA_CONTAINER_ID}" ollama list \
      | awk 'NR > 1 {print $1}'
  )"

  grep -Fxq "${OLLAMA_MODEL}" <<<"${installed_models}"
}

# В --fix подтягивает missing model, а в --check только валидирует наличие.
ensure_ollama_model() {
  printf '\n=== Shared Ollama model ===\n'

  if ollama_model_exists; then
    printf '[OK] Ollama model: %s\n' "${OLLAMA_MODEL}"
    return 0
  fi

  if [[ "${MODE}" == "--check" ]]; then
    printf 'ERROR: required Ollama model is missing: %s\n' \
      "${OLLAMA_MODEL}" >&2
    exit 5
  fi

  printf '[FIX] Pulling required Ollama model: %s\n' "${OLLAMA_MODEL}"
  docker exec "${OLLAMA_CONTAINER_ID}" ollama pull "${OLLAMA_MODEL}"

  if ! ollama_model_exists; then
    printf 'ERROR: Ollama model is still missing after pull: %s\n' \
      "${OLLAMA_MODEL}" >&2
    exit 6
  fi

  printf '[OK] Ollama model: %s\n' "${OLLAMA_MODEL}"
}

validate_mode

require_command awk
require_command docker
require_command grep
require_command sed

discover_shared_runtime
ensure_ollama_model

printf '\nSHARED INFRASTRUCTURE CHECK PASSED\n'