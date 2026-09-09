#!/usr/bin/env bash
# scripts/bootstrap-env.sh
#
# Создаёт и восстанавливает sparse `.env` Plan Validator.
#
# Скрипт генерирует только два private project secrets:
# - PostgreSQL password;
# - RabbitMQ application password.
#
# Безопасные configuration defaults остаются в `.env.example` и compose.yaml.
# Существующие корректные секреты не ротируются при каждом запуске.

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"

# Завершает bootstrap с понятной ошибкой, если обязательная command отсутствует.
require_command() {
  local command_name="$1"

  if ! command -v "${command_name}" >/dev/null 2>&1; then
    printf 'ERROR: required command not found: %s\n' "${command_name}" >&2
    exit 2
  fi
}

# Возвращает текущее значение environment variable из sparse `.env`.
read_env_value() {
  local variable_name="$1"

  if [[ ! -f "${ENV_FILE}" ]]; then
    return 0
  fi

  grep -m1 "^${variable_name}=" "${ENV_FILE}" \
    | cut -d= -f2- \
    || true
}

# Определяет, можно ли оставить уже существующий project secret без ротации.
secret_is_valid() {
  local secret_value="$1"

  if [[ -z "${secret_value}" ]]; then
    return 1
  fi

  if [[ "${secret_value}" == CHANGE_ME* ]]; then
    return 1
  fi

  [[ "${#secret_value}" -ge 24 ]]
}

# Создаёт отсутствующий или некорректный secret, не печатая его значение.
ensure_secret() {
  local variable_name="$1"
  local current_value
  local generated_value

  current_value="$(read_env_value "${variable_name}")"

  if secret_is_valid "${current_value}"; then
    printf '[OK] secret exists: %s\n' "${variable_name}"
    return 0
  fi

  generated_value="$(openssl rand -hex 32)"

  if grep -q "^${variable_name}=" "${ENV_FILE}" 2>/dev/null; then
    sed -i \
      "s|^${variable_name}=.*$|${variable_name}=${generated_value}|" \
      "${ENV_FILE}"
  else
    printf '%s=%s\n' "${variable_name}" "${generated_value}" >>"${ENV_FILE}"
  fi

  printf '[FIX] generated secret: %s\n' "${variable_name}"
}

require_command openssl

if [[ ! -f "${ENV_FILE}" ]]; then
  umask 077
  : >"${ENV_FILE}"
  printf '[FIX] created sparse .env\n'
fi

chmod 600 "${ENV_FILE}"

ensure_secret "PLAN_VALIDATOR_POSTGRES_PASSWORD"
ensure_secret "PLAN_VALIDATOR_RABBITMQ_PASSWORD"

chmod 600 "${ENV_FILE}"

printf '\n[OK] sparse environment is ready: %s\n' "${ENV_FILE}"