#!/usr/bin/env bash
# scripts/check-common.sh
#
# Автоматический quality gate Этапа 3.
#
# По умолчанию --fix:
# - синхронизирует dev/common dependencies;
# - запускает Foundation Ruff auto-fix/format;
# - проверяет package metadata/import;
# - выполняет common unit tests;
# - выполняет architecture tests через Foundation gate.
#
# --check ничего намеренно не устанавливает и не форматирует.

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

MODE="${1:---fix}"

REQUIRED_FILES=(
  "packages/common/pyproject.toml"
  "packages/common/src/plan_validator_common/__init__.py"
  "packages/common/src/plan_validator_common/exceptions.py"
  "packages/common/src/plan_validator_common/settings.py"
  "packages/common/src/plan_validator_common/observability/__init__.py"
  "packages/common/src/plan_validator_common/observability/correlation.py"
  "packages/common/src/plan_validator_common/observability/logging.py"
  "packages/common/src/plan_validator_common/observability/timing.py"
  "tests/architecture/test_common_package_contract.py"
  "tests/unit/common/test_settings.py"
  "tests/unit/common/test_correlation.py"
  "tests/unit/common/test_logging.py"
  "tests/unit/common/test_timing.py"
  "tests/unit/common/test_exceptions.py"
  "docs/COMMON_PACKAGE.md"
)

# Печатает единообразный заголовок validation step.
print_step() {
  local step_name="$1"
  printf '\n=== %s ===\n' "${step_name}"
}

# Проверяет наличие обязательной command dependency.
require_command() {
  local command_name="$1"

  if ! command -v "${command_name}" >/dev/null 2>&1; then
    printf 'ERROR: required command not found: %s\n' \
      "${command_name}" >&2
    exit 2
  fi
}

# Проверяет допустимый режим запуска.
validate_mode() {
  case "${MODE}" in
    --fix|--check)
      ;;
    *)
      printf 'ERROR: unsupported mode: %s\n' \
        "${MODE}" >&2
      printf 'Usage: %s [--fix|--check]\n' \
        "$0" >&2
      exit 3
      ;;
  esac
}

# Проверяет наличие обязательных файлов Common Package stage.
check_required_files() {
  local required_file

  for required_file in "${REQUIRED_FILES[@]}"; do
    if [[ ! -f "${required_file}" ]]; then
      printf 'ERROR: required common file is missing: %s\n' \
        "${required_file}" >&2
      exit 4
    fi

    printf '[OK] %s\n' "${required_file}"
  done
}

# Проверяет точные runtime/dev versions и editable common package.
check_python_dependencies() {
  python - <<'PY'
from importlib.metadata import PackageNotFoundError, version

EXPECTED = {
    "plan-validator-common": "0.1.0",
    "pydantic": "2.13.5",
    "pydantic-settings": "2.15.0",
    "pytest": "9.1.1",
    "ruff": "0.16.6",
}

errors = []

for package_name, expected_version in EXPECTED.items():
    try:
        actual_version = version(package_name)
    except PackageNotFoundError:
        errors.append(
            f"{package_name}: not installed"
        )
        continue

    if actual_version != expected_version:
        errors.append(
            f"{package_name}: "
            f"expected {expected_version}, "
            f"got {actual_version}"
        )

if errors:
    for error in errors:
        print(f"ERROR: {error}")

    raise SystemExit(1)

import plan_validator_common  # noqa: E402,F401

print("[OK] Python dependencies are synchronized.")
PY
}

# Автоматически синхронизирует dependencies только при необходимости.
sync_python_dependencies() {
  if check_python_dependencies >/dev/null 2>&1; then
    printf '[OK] Python dependencies already synchronized.\n'
    return 0
  fi

  printf '[FIX] Installing/updating development dependencies...\n'

  python -m pip install \
    -r requirements-dev.txt

  check_python_dependencies
}

# Выполняет import smoke test публичного common API.
check_common_import() {
  python - <<'PY'
from plan_validator_common import CommonSettings
from plan_validator_common.observability import (
    configure_logging,
    log_execution_time,
    new_correlation_id,
)

settings = CommonSettings(_env_file=None)

assert settings.log_retention_days == 14
assert callable(configure_logging)
assert callable(log_execution_time)
assert new_correlation_id()

print("[OK] Common package import smoke test.")
PY
}

validate_mode

print_step "Common package files"
check_required_files

print_step "Required tooling"

require_command python
require_command pytest
require_command ruff

python --version

if [[ "${MODE}" == "--fix" ]]; then
  print_step "Python dependency automatic synchronization"
  sync_python_dependencies

  print_step "Foundation automatic fixes"
  ./scripts/check-foundation.sh
else
  print_step "Python dependency check"
  check_python_dependencies

  print_step "Foundation check"
  ./scripts/check-foundation.sh --check

  printf '\nINFO: --check mode: source files will not be modified.\n'
fi

print_step "Python dependency integrity"
python -m pip check

print_step "Common package import"
check_common_import

print_step "Common unit tests"
pytest tests/unit/common

print_step "Git whitespace"
git diff --check

printf '\nCOMMON PACKAGE CHECKS PASSED\n'