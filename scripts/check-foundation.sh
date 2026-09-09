#!/usr/bin/env bash
# scripts/check-foundation.sh
#
# Проверяет Foundation stage без Docker и business services. Скрипт гарантирует,
# что обязательные project-contract files существуют, root Python quality gate
# проходит, а Git не содержит whitespace errors.

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

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

print_step "Ruff lint"
ruff check .

print_step "Ruff format"
ruff format --check .

print_step "Architecture tests"
pytest tests/architecture

print_step "Git whitespace"
if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git diff --check
else
  printf 'INFO: Git repository not detected; git diff --check skipped.\n'
fi

printf '\nFOUNDATION CHECKS PASSED\n'