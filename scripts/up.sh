#!/usr/bin/env bash
# scripts/up.sh
#
# Канонический first-run/recovery launcher Plan Validator.
#
# Сначала автоматически синхронизирует Common Package и project/shared
# infrastructure prerequisites, затем запускает полный Compose stack.
#
# Финальный этап запуска выполняет только неизменяющие проверки.

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

printf '=== Plan Validator Common Package preparation ===\n'
./scripts/check-common.sh --fix

printf '\n=== Plan Validator infrastructure preparation ===\n'
./scripts/check-infrastructure.sh --fix

printf '\n=== Plan Validator Compose startup ===\n'
docker compose up -d --build --wait

printf '\n=== Final Common Package validation ===\n'
./scripts/check-common.sh --check

printf '\n=== Final infrastructure validation ===\n'
./scripts/check-infrastructure.sh --check

printf '\nPLAN VALIDATOR STARTUP PASSED\n'