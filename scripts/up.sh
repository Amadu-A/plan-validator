#!/usr/bin/env bash
# scripts/up.sh
#
# Канонический first-run/recovery launcher Plan Validator.
#
# Сначала исправляет infrastructure prerequisites, после чего выполняет обычный
# `docker compose up -d --build --wait` уже для всего project Compose stack.
#
# На следующих этапах новые application services автоматически войдут в этот
# lifecycle без переписывания пользовательской команды запуска.

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

printf '=== Plan Validator automatic infrastructure preparation ===\n'
./scripts/check-infrastructure.sh --fix

printf '\n=== Plan Validator Compose startup ===\n'
docker compose up -d --build --wait

printf '\n=== Final immutable validation ===\n'
./scripts/check-infrastructure.sh --check

printf '\nPLAN VALIDATOR STARTUP PASSED\n'