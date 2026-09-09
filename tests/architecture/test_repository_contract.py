# tests/architecture/test_repository_contract.py

"""Architecture tests для Foundation contract repository.

Тесты не проверяют business functionality. Они защищают несколько решений,
которые должны оставаться стабильными на следующих этапах: pinned shared
engineering standard, обязательную retention policy и защиту secrets/runtime
данных от случайного commit.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SHARED_STANDARD_COMMIT = "b21c285228e722a2721a2622233a33183079bc3b"


def read_project_file(relative_path: str) -> str:
    """Читает UTF-8 project file для architecture assertions."""
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def test_required_foundation_documents_exist() -> None:
    """Проверяет наличие документов, определяющих архитектурный контракт проекта."""
    required_documents = (
        "README.md",
        "docs/ARCHITECTURE.md",
        "docs/DEVELOPMENT_PROCESS.md",
        "docs/RETENTION_POLICY.md",
        "docs/ROADMAP.md",
        "docs/SHARED_ENGINEERING_STANDARD.md",
    )

    missing_documents = [
        relative_path
        for relative_path in required_documents
        if not (PROJECT_ROOT / relative_path).is_file()
    ]

    assert not missing_documents, f"Missing foundation documents: {missing_documents}"


def test_shared_engineering_standard_is_pinned() -> None:
    """Проверяет воспроизводимый pin внешнего shared engineering standard."""
    standard = read_project_file("docs/SHARED_ENGINEERING_STANDARD.md")

    assert SHARED_STANDARD_COMMIT in standard


def test_retention_policy_covers_temporary_t_and_pz_contexts() -> None:
    """Проверяет, что ТЗ и ПЗ явно остаются временными storage/vector contexts."""
    retention_policy = read_project_file("docs/RETENTION_POLICY.md")

    required_markers = (
        "Technical Assignment",
        "plan_validator_t_<context_id>",
        "Пояснительная записка",
        "plan_validator_pz_<context_id>",
        "cleanup_failed",
        "24 hours",
        "14 days",
    )

    for marker in required_markers:
        assert marker in retention_policy, f"Retention marker is missing: {marker}"


def test_gitignore_protects_secrets_and_runtime_data() -> None:
    """Защищает sparse `.env` и runtime directories от случайного commit."""
    gitignore = read_project_file(".gitignore")

    required_patterns = (
        ".env\n",
        ".env.*",
        "!.env.example",
        "var/",
        "data/runtime/",
        "data/tmp/",
    )

    for pattern in required_patterns:
        assert pattern in gitignore, (
            f".gitignore pattern is missing: {pattern}"
        )