#!/usr/bin/env bash
# scripts/check-embedding.sh
#
# Quality/build/runtime gate Stage 8 Embedding Service + GPU worker.
# --fix синхронизирует зависимости, строит images и запускает runtime.
# --check выполняет только immutable проверки уже поднятого Stage 8.

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

MODE="${1:---fix}"
MODEL_CACHE_VOLUME="${PLAN_VALIDATOR_EMBEDDING_MODEL_CACHE_VOLUME:-pdrd-validation-ai_multimodal_model_cache}"

print_step() {
  local step_name="$1"
  printf '\n=== %s ===\n' "${step_name}"
}

require_command() {
  local command_name="$1"

  if ! command -v "${command_name}" >/dev/null 2>&1; then
    printf 'ERROR: required command not found: %s\n' "${command_name}" >&2
    exit 2
  fi
}

validate_mode() {
  case "${MODE}" in
    --fix|--check)
      ;;
    *)
      printf 'ERROR: unsupported mode: %s\n' "${MODE}" >&2
      exit 3
      ;;
  esac
}

load_private_environment() {
  if [[ ! -f .env ]]; then
    printf 'ERROR: private .env is missing.\n' >&2
    exit 4
  fi

  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
}

check_required_files() {
  local required_files=(
    ".env.example"
    "compose.yaml"
    "services/embedding-service/Dockerfile"
    "services/embedding-service/pyproject.toml"
    "services/embedding-service/src/embedding_service/core/settings.py"
    "services/embedding-service/src/embedding_service/infrastructure/gpu_lease.py"
    "services/embedding-service/src/embedding_service/infrastructure/gpu_runtime.py"
    "services/embedding-service/src/embedding_service/infrastructure/model_cache.py"
    "services/embedding-service/src/embedding_service/infrastructure/messaging/worker.py"
    "services/embedding-service/src/embedding_service/transport/app.py"
    "tests/unit/embedding_service/test_settings.py"
    "tests/transport/embedding_service/test_embedding_service.py"
    "tests/architecture/test_embedding_service_contract.py"
    "docs/EMBEDDING_SERVICE.md"
  )

  local relative_path

  for relative_path in "${required_files[@]}"; do
    if [[ ! -f "${relative_path}" ]]; then
      printf 'ERROR: required Embedding file is missing: %s\n' "${relative_path}" >&2
      exit 5
    fi

    printf '[OK] %s\n' "${relative_path}"
  done
}

check_python_dependencies() {
  python - <<'PY'
from importlib.metadata import PackageNotFoundError, version

EXPECTED = {
    "plan-validator-embedding-service": "0.1.0",
    "plan-validator-common": "0.1.0",
    "aio-pika": "10.0.1",
    "fastapi": "0.141.1",
    "uvicorn": "0.52.1",
}

errors = []

for package_name, expected_version in EXPECTED.items():
    try:
        actual_version = version(package_name)
    except PackageNotFoundError:
        errors.append(f"{package_name}: not installed")
        continue

    if actual_version != expected_version:
        errors.append(f"{package_name}: expected {expected_version}, got {actual_version}")

if errors:
    for error in errors:
        print(f"ERROR: {error}")

    raise SystemExit(1)

import embedding_service  # noqa: E402,F401

print("[OK] Embedding development dependencies are synchronized.")
PY
}

sync_python_dependencies() {
  if check_python_dependencies >/dev/null 2>&1; then
    printf '[OK] Embedding development dependencies already synchronized.\n'
    return 0
  fi

  printf '[FIX] Installing/updating root development dependencies...\n'
  python -m pip install -r requirements-dev.txt
  check_python_dependencies
}

prepare_runtime_directories() {
  mkdir -p \
    var/log/embedding-service \
    var/log/embedding-worker \
    var/lock/plan-validator-gpu \
    benchmarks/results

  printf '[OK] Embedding runtime directories prepared.\n'
}

check_model_cache_volume() {
  if ! docker volume inspect "${MODEL_CACHE_VOLUME}" >/dev/null 2>&1; then
    printf 'ERROR: existing embedding model-cache volume not found: %s\n' \
      "${MODEL_CACHE_VOLUME}" >&2
    printf 'Available model/cache-like Docker volumes:\n' >&2
    docker volume ls --format '{{.Name}}' | awk '
      /model|hugging|cache/ {print "  " $0}
    ' >&2
    exit 6
  fi

  printf '[OK] existing model-cache volume: %s\n' "${MODEL_CACHE_VOLUME}"

  local snapshot
  snapshot="$(
    docker run \
      --rm \
      --entrypoint sh \
      -v "${MODEL_CACHE_VOLUME}:/models/huggingface:ro" \
      postgres:16-alpine \
      -ec '
        for root in \
          /models/huggingface/hub/models--Qwen--Qwen3-VL-Embedding-8B/snapshots \
          /models/huggingface/models--Qwen--Qwen3-VL-Embedding-8B/snapshots
        do
          [ -d "$root" ] || continue

          for candidate in "$root"/*; do
            [ -d "$candidate" ] || continue

            if [ -f "$candidate/config.json" ] \
              && [ -f "$candidate/modules.json" ] \
              && { [ -f "$candidate/model.safetensors.index.json" ] \
                || find "$candidate" -maxdepth 1 -name "*.safetensors" -type f -print -quit \
                  | awk "NF {found=1} END {exit !found}"; }
            then
              printf "%s\n" "$candidate"
              exit 0
            fi
          done
        done

        direct=/models/huggingface/Qwen/Qwen3-VL-Embedding-8B
        if [ -f "$direct/config.json" ] \
          && [ -f "$direct/modules.json" ] \
          && { [ -f "$direct/model.safetensors.index.json" ] \
            || find "$direct" -maxdepth 1 -name "*.safetensors" -type f -print -quit \
              | awk "NF {found=1} END {exit !found}"; }
        then
          printf "%s\n" "$direct"
          exit 0
        fi

        exit 1
      '
  )" || {
    printf 'ERROR: Qwen/Qwen3-VL-Embedding-8B snapshot is incomplete in volume %s\n' \
      "${MODEL_CACHE_VOLUME}" >&2
    exit 7
  }

  printf '[OK] cached Qwen snapshot: %s\n' "${snapshot}"
}

check_host_gpu() {
  local gpu_line
  gpu_line="$(
    nvidia-smi \
      --query-gpu=name,memory.total,driver_version \
      --format=csv,noheader,nounits \
      | sed -n '1p'
  )"

  if [[ -z "${gpu_line}" ]]; then
    printf 'ERROR: NVIDIA GPU was not detected.\n' >&2
    exit 8
  fi

  printf '[OK] host NVIDIA GPU: %s\n' "${gpu_line}"
}

check_embedding_http() {
  docker compose exec -T embedding-service \
    python -c "
import json
import urllib.request

for path in ('/health/live', '/health/ready'):
    with urllib.request.urlopen(
        'http://127.0.0.1:8000' + path,
        timeout=5,
    ) as response:
        payload = json.load(response)
        assert response.status == 200
        assert payload['status'] in {'alive', 'ready'}

with urllib.request.urlopen(
    'http://127.0.0.1:8000/internal/v1/embedding/runtime',
    timeout=5,
) as response:
    payload = json.load(response)

assert payload['model'] == 'Qwen/Qwen3-VL-Embedding-8B'
assert payload['dimension'] == 4096
assert payload['queue'] == 'plan-validator.gpu.embedding'
assert payload['cache_ready'] is True
assert payload['gpu_required'] is True
assert payload['offline_only'] is True
"

  printf '[OK] Embedding HTTP operational contract.\n'
}

check_runtime_users() {
  local service_uid
  local worker_uid

  service_uid="$(docker compose exec -T embedding-service id -u | tr -d '\r')"
  worker_uid="$(docker compose exec -T embedding-worker id -u | tr -d '\r')"

  if [[ "${service_uid}" == "0" || "${worker_uid}" == "0" ]]; then
    printf 'ERROR: Embedding service/worker must not run as root.\n' >&2
    exit 9
  fi

  printf '[OK] Embedding Service UID: %s\n' "${service_uid}"
  printf '[OK] Embedding Worker UID: %s\n' "${worker_uid}"
}

check_worker_gpu() {
  docker compose exec -T embedding-worker \
    python -c "
import torch

assert torch.__version__.startswith('2.8.0')
assert torch.cuda.is_available()
free_bytes, total_bytes = torch.cuda.mem_get_info()
name = torch.cuda.get_device_name(0)
print(
    f'[OK] worker CUDA: {name}; '
    f'free_vram={free_bytes}; total_vram={total_bytes}'
)
"
}

check_queue_consumer() {
  local rabbitmq_container
  rabbitmq_container="$(
    docker ps \
      --filter network=ai-shared \
      --filter label=com.docker.compose.service=rabbitmq \
      --format '{{.ID}}' \
      | sed -n '1p'
  )"

  if [[ -z "${rabbitmq_container}" ]]; then
    printf 'ERROR: shared RabbitMQ container was not found.\n' >&2
    exit 10
  fi

  local found="0"
  local queue_name
  local consumers

  while read -r queue_name consumers; do
    if [[ "${queue_name}" != "plan-validator.gpu.embedding" ]]; then
      continue
    fi

    if [[ ! "${consumers}" =~ ^[0-9]+$ || "${consumers}" -lt 1 ]]; then
      printf 'ERROR: embedding queue has no active consumer.\n' >&2
      exit 11
    fi

    found="1"
    printf '[OK] embedding queue consumer count: %s\n' "${consumers}"
    break
  done < <(
    docker exec "${rabbitmq_container}" \
      rabbitmqctl \
      list_queues \
      -p /plan-validator \
      name consumers \
      --silent
  )

  if [[ "${found}" != "1" ]]; then
    printf 'ERROR: embedding queue is missing: plan-validator.gpu.embedding\n' >&2
    exit 12
  fi
}

check_structured_log() {
  local service_name="$1"
  local log_file="var/log/${service_name}/${service_name}.log"

  if [[ ! -s "${log_file}" ]]; then
    printf 'ERROR: structured log is missing: %s\n' "${log_file}" >&2
    exit 13
  fi

  python - "${log_file}" "${service_name}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
expected_service = sys.argv[2]
lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

if not lines:
    raise SystemExit("Embedding log is empty")

payload = json.loads(lines[-1])
assert payload["service"] == expected_service
assert "timestamp" in payload
assert "level" in payload
assert "message" in payload
print(f"[OK] structured file log: {path}")
PY
}

validate_mode
require_command docker
require_command python
require_command pytest
require_command ruff
require_command nvidia-smi

PLAN_VALIDATOR_RUNTIME_UID="${PLAN_VALIDATOR_RUNTIME_UID:-$(id -u)}"
PLAN_VALIDATOR_RUNTIME_GID="${PLAN_VALIDATOR_RUNTIME_GID:-$(id -g)}"
export PLAN_VALIDATOR_RUNTIME_UID
export PLAN_VALIDATOR_RUNTIME_GID

load_private_environment

print_step "Embedding Stage files"
check_required_files

if [[ "${MODE}" == "--fix" ]]; then
  print_step "Embedding dependency synchronization"
  sync_python_dependencies

  print_step "Automatic Ruff/format"
  ./scripts/check-common.sh --fix
else
  print_step "Embedding dependency check"
  check_python_dependencies

  print_step "Immutable Common check"
  ./scripts/check-common.sh --check

  printf '\nINFO: --check mode does not rebuild Embedding runtime.\n'
fi

print_step "Catalog predecessor contract"
./scripts/check-catalog.sh --check

print_step "Embedding unit tests"
pytest tests/unit/embedding_service

print_step "Embedding transport tests"
pytest tests/transport/embedding_service

print_step "Architecture tests"
pytest tests/architecture

print_step "Existing Qwen model cache"
check_model_cache_volume

print_step "Host GPU"
check_host_gpu

print_step "Compose validation"
docker compose config --quiet

if [[ "${MODE}" == "--fix" ]]; then
  print_step "Runtime directories"
  prepare_runtime_directories

  print_step "Embedding images"
  docker compose build \
    embedding-service \
    embedding-worker \
    embedding-benchmark

  print_step "Embedding runtime startup"
  docker compose up \
    -d \
    --wait \
    embedding-service \
    embedding-worker
fi

print_step "Embedding containers"
docker compose ps embedding-service embedding-worker

print_step "Embedding HTTP runtime"
check_embedding_http

print_step "Embedding runtime users"
check_runtime_users

print_step "Embedding worker CUDA"
check_worker_gpu

print_step "Embedding RabbitMQ queue"
check_queue_consumer

print_step "Embedding structured logging"
check_structured_log embedding-service
check_structured_log embedding-worker

print_step "Git whitespace"
git diff --check

printf '\nEMBEDDING STAGE CHECKS PASSED\n'
