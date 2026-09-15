#!/usr/bin/env bash
# scripts/benchmark-context.sh
#
# Explicit heavy Stage 10 E2E. Проверяет public Gateway lifecycle, internal
# normalized-chunk handoff, real Qwen T/PZ retrieval, SIGKILL Context worker,
# stale-lease recovery, следующий user job и automatic physical cleanup.
# В normal startup этот destructive/failure-injection сценарий не запускается.

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

PLAN_VALIDATOR_RUNTIME_UID="${PLAN_VALIDATOR_RUNTIME_UID:-$(id -u)}"
PLAN_VALIDATOR_RUNTIME_GID="${PLAN_VALIDATOR_RUNTIME_GID:-$(id -g)}"

export PLAN_VALIDATOR_RUNTIME_UID
export PLAN_VALIDATOR_RUNTIME_GID

if [[ ! -f .env ]]; then
  printf 'ERROR: private .env is missing.\n' >&2
  exit 2
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

rabbitmq_container=""

find_rabbitmq_container() {
  docker ps \
    --filter network=ai-shared \
    --filter label=com.docker.compose.service=rabbitmq \
    --format '{{.ID}}' \
    | sed -n '1p'
}

print_runtime_diagnostics() {
  local status="$1"

  if (( status == 0 )); then
    return 0
  fi

  printf '\n=== Stage 10 failure diagnostics ===\n' >&2

  docker compose ps \
    context-service \
    context-worker \
    context-maintenance \
    embedding-worker \
    api-gateway \
    >&2 || true

  docker compose logs \
    --tail=120 \
    context-service \
    context-worker \
    context-maintenance \
    embedding-worker \
    >&2 || true

  rabbitmq_container="$(find_rabbitmq_container || true)"

  if [[ -n "${rabbitmq_container}" ]]; then
    docker exec "${rabbitmq_container}" \
      rabbitmqctl \
      list_queues \
      -p /plan-validator \
      name messages_ready messages_unacknowledged consumers \
      --silent \
      >&2 || true
  fi
}

on_exit() {
  local status=$?
  trap - EXIT
  print_runtime_diagnostics "${status}"
  exit "${status}"
}

trap on_exit EXIT

printf '=== Stage 10 immutable prerequisite check ===\n'
./scripts/check-context.sh --check

printf '\n=== Stage 10 runtime topology before fault injection ===\n'
docker compose ps \
  context-service \
  context-worker \
  context-maintenance \
  embedding-worker \
  api-gateway

printf '\n=== RabbitMQ TTL policies before runtime E2E ===\n'
rabbitmq_container="$(find_rabbitmq_container)"

if [[ -z "${rabbitmq_container}" ]]; then
  printf 'ERROR: shared RabbitMQ container was not found.\n' >&2
  exit 3
fi

docker exec "${rabbitmq_container}" \
  rabbitmqctl \
  list_policies \
  -p /plan-validator \
  --silent

printf '\n=== Real Stage 10 Qwen + SIGKILL recovery E2E ===\n'
export PLAN_VALIDATOR_RUN_CONTEXT_RUNTIME_E2E=1

pytest \
  tests/runtime/context_service/test_context_runtime.py \
  -q \
  -s

printf '\n=== RabbitMQ queue state after recovery E2E ===\n'
docker exec "${rabbitmq_container}" \
  rabbitmqctl \
  list_queues \
  -p /plan-validator \
  name messages_ready messages_unacknowledged consumers \
  --silent

printf '\n=== Context temporary Qdrant collections after cleanup ===\n'
docker compose exec -T context-service \
  python - <<'PY'
from qdrant_client import QdrantClient

client = QdrantClient(
    host="qdrant",
    port=6333,
    prefer_grpc=False,
    timeout=10,
)

try:
    names = sorted(
        collection.name
        for collection in client.get_collections().collections
        if collection.name.startswith("plan_validator_t_")
        or collection.name.startswith("plan_validator_pz_")
    )

    print(
        "temporary_context_collections:",
        names,
    )
finally:
    client.close()
PY

printf '\n=== GPU after explicit Stage 10 E2E ===\n'

nvidia-smi \
  --query-gpu=name,memory.used,memory.free,memory.total \
  --format=csv,noheader,nounits

printf '\n=== Final Context immutable check ===\n'
./scripts/check-context.sh --check

printf '\nCONTEXT RUNTIME FAILURE-INJECTION E2E PASSED\n'