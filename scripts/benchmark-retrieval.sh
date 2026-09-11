#!/usr/bin/env bash
# scripts/benchmark-retrieval.sh
#
# Explicit heavy Stage 9 E2E. Создаёт временные Catalog N/U sources, проверяет
# outbox delivery, batch Qwen indexing, Qdrant typed N search, U isolation и
# delete-event cleanup. В normal startup этот сценарий намеренно не запускается.

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

printf '=== Retrieval immutable prerequisite check ===\n'
./scripts/check-retrieval.sh --check

printf '\n=== Real Stage 9 N/U indexing and typed retrieval E2E ===\n'
pytest tests/runtime/retrieval_service -q

printf '\n=== RabbitMQ queue state ===\n'
rabbitmq_container="$(
  docker ps \
    --filter network=ai-shared \
    --filter label=com.docker.compose.service=rabbitmq \
    --format '{{.ID}}' \
    | sed -n '1p'
)"

if [[ -z "${rabbitmq_container}" ]]; then
  printf 'ERROR: shared RabbitMQ container was not found.\n' >&2
  exit 3
fi

docker exec "${rabbitmq_container}" \
  rabbitmqctl \
  list_queues \
  -p /plan-validator \
  name messages_ready messages_unacknowledged consumers \
  --silent

printf '\n=== Qdrant managed-source corpus ===\n'
docker compose exec -T retrieval-service \
  python - <<'PY'
from qdrant_client import QdrantClient

client = QdrantClient(host="qdrant", port=6333, prefer_grpc=False, timeout=10)

try:
    info = client.get_collection("plan_validator_managed_sources")
    print("status:", info.status)
    print("points_count:", info.points_count)
    print("indexed_vectors_count:", info.indexed_vectors_count)
finally:
    client.close()
PY

printf '\n=== GPU after explicit Stage 9 E2E ===\n'
nvidia-smi \
  --query-gpu=name,memory.used,memory.free,memory.total \
  --format=csv,noheader,nounits

printf '\n=== Final Retrieval immutable check ===\n'
./scripts/check-retrieval.sh --check

printf '\nRETRIEVAL RUNTIME E2E PASSED\n'
