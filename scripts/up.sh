#!/usr/bin/env bash
# scripts/up.sh
#
# Канонический first-run/recovery launcher Plan Validator.
# Поднимает stages в dependency order и затем выполняет immutable validation.

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

PLAN_VALIDATOR_RUNTIME_UID="${PLAN_VALIDATOR_RUNTIME_UID:-$(id -u)}"
PLAN_VALIDATOR_RUNTIME_GID="${PLAN_VALIDATOR_RUNTIME_GID:-$(id -g)}"

export PLAN_VALIDATOR_RUNTIME_UID
export PLAN_VALIDATOR_RUNTIME_GID

printf '=== Plan Validator Common Package preparation ===\n'
./scripts/check-common.sh --fix

printf '\n=== Plan Validator infrastructure preparation ===\n'
./scripts/check-infrastructure.sh --fix

printf '\n=== Plan Validator API Gateway preparation ===\n'
./scripts/check-gateway.sh --fix

printf '\n=== Plan Validator Authentication preparation ===\n'
./scripts/check-auth.sh --fix

printf '\n=== Plan Validator Catalog preparation ===\n'
./scripts/check-catalog.sh --fix

printf '\n=== Plan Validator Embedding preparation ===\n'
./scripts/check-embedding.sh --fix

printf '\n=== Plan Validator full Compose startup ===\n'
docker compose up -d --build --wait

printf '\n=== Final Common validation ===\n'
./scripts/check-common.sh --check

printf '\n=== Final infrastructure validation ===\n'
./scripts/check-infrastructure.sh --check

printf '\n=== Final Gateway validation ===\n'
./scripts/check-gateway.sh --check

printf '\n=== Final Authentication validation ===\n'
./scripts/check-auth.sh --check

printf '\n=== Final Catalog validation ===\n'
./scripts/check-catalog.sh --check

printf '\n=== Final Embedding validation ===\n'
./scripts/check-embedding.sh --check

printf '\nPLAN VALIDATOR STARTUP PASSED\n'
