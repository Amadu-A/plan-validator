#!/usr/bin/env bash
# scripts/benchmark-embedding.sh
#
# Реальный Stage 8 E2E benchmark:
# RabbitMQ -> GPU worker -> lease -> admission -> Qwen load/inference/unload -> RPC reply.
# Скрипт не входит в обычный startup, потому что намеренно загружает 8B checkpoint.

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

printf '=== Embedding immutable prerequisite check ===\n'
./scripts/check-embedding.sh --check

printf '\n=== Qwen3-VL-Embedding-8B RabbitMQ/GPU benchmark ===\n'

raw_output="$(
  docker compose \
    --profile ops \
    run \
    --rm \
    --no-deps \
    embedding-benchmark
)"

printf '%s\n' "${raw_output}"

json_line="$(printf '%s\n' "${raw_output}" | awk 'NF {line=$0} END {print line}')"

mkdir -p benchmarks/results
result_file="benchmarks/results/embedding-$(date -u +%Y%m%dT%H%M%SZ).json"

python - "${json_line}" "${result_file}" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(sys.argv[1])

assert payload["status"] == "success"
assert payload["model"] == "Qwen/Qwen3-VL-Embedding-8B"
assert payload["dimension"] == 4096
assert payload["verified_dimension"] == 4096
assert abs(float(payload["vector_norm"]) - 1.0) <= 0.01
assert payload["vector"] == "[omitted]"

telemetry = payload["telemetry"]

for key in (
    "available_ram_bytes",
    "free_vram_before_bytes",
    "total_vram_bytes",
    "model_load_ms",
    "encode_ms",
    "total_ms",
    "peak_allocated_vram_bytes",
):
    assert key in telemetry

path = Path(sys.argv[2])
path.write_text(
    json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)

print(f"[OK] benchmark result: {path}")
PY

printf '\n=== GPU state after mandatory model release ===\n'
nvidia-smi \
  --query-gpu=name,memory.used,memory.free,memory.total \
  --format=csv,noheader,nounits

printf '\nEMBEDDING GPU BENCHMARK PASSED\n'
