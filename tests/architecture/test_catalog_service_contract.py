# tests/architecture/test_catalog_service_contract.py

"""Architecture tests Catalog bounded context."""

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

CATALOG_ROOT = PROJECT_ROOT / "services" / "catalog-service" / "src" / "catalog_service"


def imported_root_modules(python_file: Path) -> set[str]:
    """Возвращает root modules Python imports."""
    tree = ast.parse(
        python_file.read_text(encoding="utf-8"),
        filename=str(python_file),
    )

    result: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name.split(".")[0] for alias in node.names)

        if isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module.split(".")[0])

    return result


def test_catalog_application_domain_have_no_framework_coupling() -> None:
    """Запрещает infrastructure/framework dependencies в business layers."""
    forbidden = {
        "fastapi",
        "starlette",
        "sqlalchemy",
        "psycopg",
        "alembic",
        "httpx",
        "celery",
        "qdrant_client",
    }

    for layer in ("application", "domain"):
        for python_file in (CATALOG_ROOT / layer).rglob("*.py"):
            imports = imported_root_modules(python_file)

            assert imports.isdisjoint(forbidden), (
                f"{python_file} imports forbidden modules: {imports & forbidden}"
            )


def test_catalog_repositories_are_split_by_resource() -> None:
    """Защищает отдельные repositories sections/prompts."""
    root = CATALOG_ROOT / "infrastructure" / "database" / "repositories"

    assert (root / "section.py").is_file()
    assert (root / "system_prompt.py").is_file()

    assert not (root / "crud.py").exists()
    assert not (root / "repositories.py").exists()


def test_catalog_does_not_implement_source_management() -> None:
    """Не позволяет преждевременно забрать ответственность Stage 7."""
    source = "\n".join(path.read_text(encoding="utf-8") for path in CATALOG_ROOT.rglob("*.py"))

    forbidden_markers = (
        "qdrant_client",
        "RabbitMQ",
        "aio_pika",
        "UploadFile",
    )

    for marker in forbidden_markers:
        assert marker not in source


def test_catalog_migration_is_one_shot_ops_service() -> None:
    """Проверяет explicit migration lifecycle."""
    compose = (PROJECT_ROOT / "compose.yaml").read_text(encoding="utf-8")

    assert "catalog-migrate:" in compose
    assert "services/catalog-service/alembic.ini" in compose
    assert "- ops" in compose


def test_catalog_service_is_internal_only() -> None:
    """Catalog Service не должен публиковать host port."""
    compose = (PROJECT_ROOT / "compose.yaml").read_text(encoding="utf-8")

    start = compose.index("\n  catalog-service:\n")
    end = compose.index("\n  catalog-migrate:\n")

    block = compose[start:end]

    assert "\n    ports:" not in block
    assert "\n    expose:" in block
    assert "\n    environment:" not in block
    assert "\n    env_file:" in block


def test_catalog_has_nested_section_and_prompt_models() -> None:
    """Фиксирует основную функциональность Stage 6."""
    section = (CATALOG_ROOT / "domain" / "section.py").read_text(encoding="utf-8")

    prompt = (CATALOG_ROOT / "domain" / "system_prompt.py").read_text(encoding="utf-8")

    assert "parent_id" in section
    assert "sort_order" in section
    assert "SystemPrompt" in prompt


def test_catalog_sources_have_docstrings() -> None:
    """Проверяет documentation discipline Catalog source."""
    missing: list[str] = []

    for python_file in CATALOG_ROOT.rglob("*.py"):
        tree = ast.parse(
            python_file.read_text(encoding="utf-8"),
            filename=str(python_file),
        )

        if ast.get_docstring(tree) is None:
            missing.append(f"{python_file}:module")

        for node in ast.walk(tree):
            if (
                isinstance(
                    node,
                    (
                        ast.ClassDef,
                        ast.FunctionDef,
                        ast.AsyncFunctionDef,
                    ),
                )
                and ast.get_docstring(node) is None
            ):
                missing.append(f"{python_file}:{node.lineno}:{node.name}")

    assert not missing, f"Missing Catalog docstrings: {missing}"
