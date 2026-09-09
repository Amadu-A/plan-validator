# tests/architecture/test_common_package_contract.py

"""Architecture tests границ общего Python package Plan Validator."""

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

COMMON_ROOT = PROJECT_ROOT / "packages" / "common" / "src" / "plan_validator_common"


def read_project_file(relative_path: str) -> str:
    """Читает UTF-8 project file для architecture assertions."""
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def test_common_package_files_exist() -> None:
    """Проверяет ожидаемую минимальную структуру reusable common package."""
    required_files = (
        "packages/common/pyproject.toml",
        "packages/common/src/plan_validator_common/__init__.py",
        "packages/common/src/plan_validator_common/exceptions.py",
        "packages/common/src/plan_validator_common/settings.py",
        "packages/common/src/plan_validator_common/observability/__init__.py",
        "packages/common/src/plan_validator_common/observability/correlation.py",
        "packages/common/src/plan_validator_common/observability/logging.py",
        "packages/common/src/plan_validator_common/observability/timing.py",
    )

    missing_files = [
        relative_path
        for relative_path in required_files
        if not (PROJECT_ROOT / relative_path).is_file()
    ]

    assert not missing_files, f"Missing common package files: {missing_files}"


def test_common_package_has_no_framework_coupling() -> None:
    """Запрещает infrastructure/framework imports в reusable common package."""
    forbidden_imports = (
        "fastapi",
        "sqlalchemy",
        "celery",
        "qdrant_client",
        "ollama",
    )

    for python_file in COMMON_ROOT.rglob("*.py"):
        source = python_file.read_text(encoding="utf-8")

        for forbidden_import in forbidden_imports:
            assert f"import {forbidden_import}" not in source
            assert f"from {forbidden_import}" not in source


def test_settings_use_layered_environment_contract() -> None:
    """Проверяет dotenv layering, prefix и nested delimiter."""
    settings_source = read_project_file("packages/common/src/plan_validator_common/settings.py")

    required_markers = (
        'env_prefix="PLAN_VALIDATOR_"',
        'env_nested_delimiter="__"',
        'env_file=(".env.example", ".env")',
        'env_file_encoding="utf-8"',
    )

    for marker in required_markers:
        assert marker in settings_source


def test_logging_has_json_rotation_and_age_cleanup() -> None:
    """Защищает bounded structured file logging contract."""
    logging_source = read_project_file(
        "packages/common/src/plan_validator_common/observability/logging.py"
    )

    required_markers = (
        "RotatingFileHandler",
        "json.dumps",
        "cleanup_expired_log_files",
        "file_backup_count",
        "retention_days",
        "[REDACTED]",
    )

    for marker in required_markers:
        assert marker in logging_source


def test_timing_decorator_uses_perf_counter_and_stable_event() -> None:
    """Проверяет обязательный operation timing contract."""
    timing_source = read_project_file(
        "packages/common/src/plan_validator_common/observability/timing.py"
    )

    required_markers = (
        "time.perf_counter()",
        '"event": "operation_timing"',
        '"duration_ms"',
        '"status": "success"',
        '"status": "error"',
    )

    for marker in required_markers:
        assert marker in timing_source


def test_common_python_sources_are_documented() -> None:
    """Проверяет module/class/function docstrings внутри common package."""
    missing_docstrings: list[str] = []

    for python_file in COMMON_ROOT.rglob("*.py"):
        source = python_file.read_text(encoding="utf-8")
        syntax_tree = ast.parse(
            source,
            filename=str(python_file),
        )

        if ast.get_docstring(syntax_tree) is None:
            missing_docstrings.append(f"{python_file}: module")

        for node in ast.walk(syntax_tree):
            if not isinstance(
                node,
                (
                    ast.ClassDef,
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                ),
            ):
                continue

            if ast.get_docstring(node) is None:
                missing_docstrings.append(f"{python_file}:{node.lineno}:{node.name}")

    assert not missing_docstrings, f"Missing common package docstrings: {missing_docstrings}"


def test_common_package_versions_are_pinned() -> None:
    """Проверяет воспроизводимые Pydantic и build backend versions."""
    package_pyproject = read_project_file("packages/common/pyproject.toml")

    assert "hatchling==1.32.0" in package_pyproject
    assert "pydantic==2.13.5" in package_pyproject
    assert "pydantic-settings==2.15.0" in package_pyproject
