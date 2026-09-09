#!/usr/bin/env bash
# scripts/check-foundation.sh
#
# Проверяет Foundation stage без Docker и business services.
#
# По умолчанию скрипт сначала автоматически исправляет безопасно исправляемые
# Ruff lint-проблемы и форматирует Python-код, после чего выполняет повторную
# неизменяющую проверку и architecture tests.
#
# Режим `--check` ничего не изменяет и предназначен для CI/startup validation.

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

MODE="${1:---fix}"

REQUIRED_FILES=(
  ".dockerignore"
  ".gitattributes"
  ".gitignore"
  "README.md"
  "docs/ARCHITECTURE.md"
  "docs/DEVELOPMENT_PROCESS.md"
  "docs/RETENTION_POLICY.md"
  "docs/ROADMAP.md"
  "docs/SHARED_ENGINEERING_STANDARD.md"
  "pyproject.toml"
  "requirements-dev.txt"
  "tests/architecture/test_repository_contract.py"
)

# Печатает единообразный заголовок шага проверки.
print_step() {
  local step_name="$1"
  printf '\n=== %s ===\n' "${step_name}"
}

# Завершает проверку с понятным сообщением об отсутствующей command dependency.
require_command() {
  local command_name="$1"

  if ! command -v "${command_name}" >/dev/null 2>&1; then
    printf 'ERROR: required command not found: %s\n' "${command_name}" >&2
    exit 2
  fi
}

# Проверяет поддерживаемый режим запуска.
validate_mode() {
  case "${MODE}" in
    --fix|--check)
      ;;
    *)
      printf 'ERROR: unsupported mode: %s\n' "${MODE}" >&2
      printf 'Usage: %s [--fix|--check]\n' "$0" >&2
      exit 4
      ;;
  esac
}

# Автоматически исправляет Python lint и formatting issues.
apply_python_fixes() {
  print_step "Ruff automatic fixes"
  ruff check --fix .

  print_step "Ruff automatic formatting"
  ruff format .
}

# Выполняет неизменяющую финальную Python quality validation.
check_python_quality() {
  print_step "Ruff lint check"
  ruff check .

  print_step "Ruff format check"
  ruff format --check .
}

validate_mode

print_step "Foundation files"

for required_file in "${REQUIRED_FILES[@]}"; do
  if [[ ! -f "${required_file}" ]]; then
    printf 'ERROR: required file is missing: %s\n' "${required_file}" >&2
    exit 3
  fi

  printf '[OK] %s\n' "${required_file}"
done

print_step "Tooling"

require_command python
require_command ruff
require_command pytest

python --version
ruff --version
pytest --version

if [[ "${MODE}" == "--fix" ]]; then
  apply_python_fixes
else
  printf '\nINFO: --check mode: source files will not be modified.\n'
fi

check_python_quality

print_step "Architecture tests"
pytest tests/architecture

print_step "Git whitespace"

if command -v git >/dev/null 2>&1 \
  && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git diff --check
else
  printf 'INFO: Git repository not detected; git diff --check skipped.\n'
fi

printf '\nFOUNDATION CHECKS PASSED\n'