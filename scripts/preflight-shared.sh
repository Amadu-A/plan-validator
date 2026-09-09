#!/usr/bin/env bash
# scripts/preflight-shared.sh
#
# Проверяет shared infrastructure, которой владеет repository
# `shared_infrasktructure`.
#
# В режиме --fix скрипт разрешено:
# - выполнить shared bootstrap;
# - поднять shared Compose stack;
# - скачать отсутствующую required Ollama model.
#
# В режиме --check никакие shared resources намеренно не изменяются.

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:---fix}"

SHARED_INFRA_DIR="$(
  realpath -m \
    "${PLAN_VALIDATOR_SHARED_INFRA_DIR:-${ROOT_DIR}/../shared_infrasktructure}"
)"

OLLAMA_MODEL="${PLAN_VALIDATOR_OLLAMA_MODEL:-qwen3-vl:8b-instruct}"

# Проверяет допустимый режим работы bootstrap/preflight.
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

# Проверяет наличие необходимых файлов shared infrastructure repository.
validate_shared_repository() {
  local required_files=(
    "compose.yaml"
    "scripts/bootstrap.sh"
    "scripts/check.sh"
    "scripts/pull-ollama-model.sh"
  )

  if [[ ! -d "${SHARED_INFRA_DIR}" ]]; then
    printf 'ERROR: shared infrastructure directory not found: %s\n' \
      "${SHARED_INFRA_DIR}" >&2
    exit 3
  fi

  for relative_path in "${required_files[@]}"; do
    if [[ ! -f "${SHARED_INFRA_DIR}/${relative_path}" ]]; then
      printf 'ERROR: missing shared infrastructure file: %s\n' \
        "${SHARED_INFRA_DIR}/${relative_path}" >&2
      exit 4
    fi
  done
}

# Запускает shared stack через его собственный lifecycle и проверяет Ollama model.
apply_shared_fixes() {
  printf '\n=== Shared infrastructure automatic bootstrap ===\n'

  (
    cd "${SHARED_INFRA_DIR}"

    ./scripts/bootstrap.sh

    docker compose up -d --wait

    ./scripts/pull-ollama-model.sh "${OLLAMA_MODEL}"
  )
}

# Выполняет штатную diagnostic-проверку shared infrastructure.
check_shared_stack() {
  printf '\n=== Shared infrastructure validation ===\n'

  (
    cd "${SHARED_INFRA_DIR}"
    ./scripts/check.sh
  )
}

# Проверяет, что required Ollama model действительно видна runtime.
check_ollama_model() {
  local installed_models

  installed_models="$(
    cd "${SHARED_INFRA_DIR}"

    docker compose exec -T ollama ollama list 2>/dev/null \
      | awk 'NR > 1 {print $1}'
  )"

  if ! grep -Fxq "${OLLAMA_MODEL}" <<<"${installed_models}"; then
    printf 'ERROR: required Ollama model is missing: %s\n' \
      "${OLLAMA_MODEL}" >&2
    exit 5
  fi

  printf '[OK] Ollama model: %s\n' "${OLLAMA_MODEL}"
}

validate_mode
validate_shared_repository

if [[ "${MODE}" == "--fix" ]]; then
  apply_shared_fixes
fi

check_shared_stack
check_ollama_model

printf '\nSHARED INFRASTRUCTURE CHECK PASSED\n'