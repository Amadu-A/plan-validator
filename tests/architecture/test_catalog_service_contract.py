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
    """Защищает отдельные repositories sections/prompts/sources/outbox."""
    root = CATALOG_ROOT / "infrastructure" / "database" / "repositories"

    assert (root / "section.py").is_file()

    assert (root / "system_prompt.py").is_file()

    assert (root / "source.py").is_file()

    assert (root / "source_outbox.py").is_file()

    assert not (root / "crud.py").exists()

    assert not (root / "repositories.py").exists()


def test_catalog_source_management_stays_before_indexing_stage() -> None:
    """Разрешает Stage 7 storage/outbox, но запрещает Stage 8/9 coupling."""
    source = "\n".join(path.read_text(encoding="utf-8") for path in CATALOG_ROOT.rglob("*.py"))

    forbidden_markers = (
        "qdrant_client",
        "aio_pika",
        "celery",
        "ollama",
        "nvidia",
    )

    for marker in forbidden_markers:
        assert marker not in source.casefold()


def test_catalog_source_routers_are_split_by_semantic_type() -> None:
    """Фиксирует отдельные internal routers N и U."""
    routers = CATALOG_ROOT / "transport" / "routers"

    assert (routers / "normative_documents.py").is_file()

    assert (routers / "user_documents.py").is_file()

    internal_v1 = (routers / "internal_v1.py").read_text(encoding="utf-8")

    assert "normative_documents_router" in internal_v1

    assert "user_documents_router" in internal_v1


def test_catalog_source_contract_does_not_expose_storage_key() -> None:
    """Не позволяет internal/public source schema раскрывать filesystem key."""
    schema = (CATALOG_ROOT / "transport" / "source_schemas.py").read_text(encoding="utf-8")

    assert "storage_key:" not in schema


def test_catalog_source_outbox_is_transactional_but_not_dispatched() -> None:
    """Фиксирует durable Stage 7 outbox без преждевременного Rabbit worker."""
    domain = (CATALOG_ROOT / "domain" / "source.py").read_text(encoding="utf-8")

    use_case = (CATALOG_ROOT / "application" / "use_cases" / "source_management.py").read_text(
        encoding="utf-8"
    )

    assert "catalog.source.uploaded.v1" in domain

    assert "catalog.source.delete_requested.v1" in domain

    assert "source_outbox.add" in use_case

    assert not (CATALOG_ROOT / "infrastructure" / "messaging" / "dispatcher.py").exists()


def test_catalog_source_storage_uses_host_visible_persistent_directory() -> None:
    """Проверяет bind mount N/U storage и защиту runtime files от Git."""
    compose = (PROJECT_ROOT / "compose.yaml").read_text(encoding="utf-8")

    gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")

    dockerignore = (PROJECT_ROOT / ".dockerignore").read_text(encoding="utf-8")

    start = compose.index("\n  catalog-service:\n")

    end = compose.index("\n  catalog-migrate:\n")

    block = compose[start:end]

    assert "./data/catalog:/app/data/catalog" in block

    assert "catalog-source-data:" not in compose

    assert "\n    environment:" not in block

    assert "\n    env_file:" in block

    assert "data/catalog/*" in gitignore

    assert "!data/catalog/.gitkeep" in gitignore

    assert "data/catalog" in dockerignore

    assert (PROJECT_ROOT / "data" / "catalog" / ".gitkeep").is_file()


def test_public_source_contract_exposes_stable_content_url() -> None:
    """Фиксирует кликабельную source identity независимо от filesystem path."""
    schema = (
        PROJECT_ROOT
        / "services"
        / "api-gateway"
        / "src"
        / "api_gateway"
        / "transport"
        / "catalog_source_schemas.py"
    ).read_text(encoding="utf-8")

    assert "content_url: str" in schema
    assert "/api/v1/catalog/" in schema
    assert "/content" in schema
    assert "normative-documents" in schema
    assert "user-documents" in schema
    assert "storage_key" not in schema


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


def test_catalog_has_nested_section_prompt_and_source_models() -> None:
    """Фиксирует основную функциональность Stages 6-7."""
    section = (CATALOG_ROOT / "domain" / "section.py").read_text(encoding="utf-8")

    prompt = (CATALOG_ROOT / "domain" / "system_prompt.py").read_text(encoding="utf-8")

    source = (CATALOG_ROOT / "domain" / "source.py").read_text(encoding="utf-8")

    assert "parent_id" in section
    assert "sort_order" in section
    assert "SystemPrompt" in prompt
    assert "SourceKind" in source
    assert 'NORMATIVE = "N"' in source
    assert 'USER = "U"' in source


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
