# tests/architecture/test_auth_service_contract.py

"""Architecture tests Authentication bounded context."""

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

AUTH_ROOT = PROJECT_ROOT / "services" / "auth-service" / "src" / "auth_service"


def imported_root_modules(
    python_file: Path,
) -> set[str]:
    """Возвращает root modules Python import statements."""
    tree = ast.parse(
        python_file.read_text(encoding="utf-8"),
        filename=str(python_file),
    )

    result: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(
            node,
            ast.Import,
        ):
            result.update(alias.name.split(".")[0] for alias in node.names)

        if (
            isinstance(
                node,
                ast.ImportFrom,
            )
            and node.module
        ):
            result.add(node.module.split(".")[0])

    return result


def test_auth_application_and_domain_have_no_framework_coupling() -> None:
    """Запрещает FastAPI/SQLAlchemy/Psycopg в business layers Auth."""
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

    for layer in (
        "application",
        "domain",
    ):
        for python_file in (AUTH_ROOT / layer).rglob("*.py"):
            imports = imported_root_modules(python_file)

            assert imports.isdisjoint(forbidden), (
                f"{python_file} imports forbidden modules: {imports & forbidden}"
            )


def test_auth_repositories_are_split_by_aggregate() -> None:
    """Защищает отдельные User/Session repository modules."""
    repository_root = AUTH_ROOT / "infrastructure" / "database" / "repositories"

    assert (repository_root / "user.py").is_file()

    assert (repository_root / "session.py").is_file()

    assert not (repository_root / "repositories.py").exists()

    assert not (repository_root / "crud.py").exists()


def test_auth_migration_is_separate_one_shot_service() -> None:
    """Проверяет отсутствие hidden migration внутри normal startup."""
    compose = (PROJECT_ROOT / "compose.yaml").read_text(encoding="utf-8")

    assert "auth-migrate:" in compose
    assert "profiles:" in compose
    assert "- ops" in compose
    assert "upgrade" in compose
    assert "head" in compose


def test_auth_service_is_not_published_to_host() -> None:
    """Проверяет internal-only network boundary Authentication Service."""
    compose = (PROJECT_ROOT / "compose.yaml").read_text(encoding="utf-8")

    start = compose.index("\n  auth-service:\n")
    end = compose.index("\n  auth-migrate:\n")

    auth_block = compose[start:end]

    assert "\n    ports:" not in auth_block
    assert '\n      - "8000"\n' in auth_block


def test_gateway_and_auth_do_not_duplicate_application_environment() -> None:
    """Фиксирует новый Pydantic-first configuration contract."""
    compose = (PROJECT_ROOT / "compose.yaml").read_text(encoding="utf-8")

    auth_start = compose.index("\n  auth-service:\n")
    auth_end = compose.index("\n  auth-migrate:\n")

    gateway_start = compose.index("\n  api-gateway:\n")
    gateway_end = compose.index("\nnetworks:\n")

    auth_block = compose[auth_start:auth_end]
    gateway_block = compose[gateway_start:gateway_end]

    assert "\n    environment:" not in auth_block
    assert "\n    environment:" not in gateway_block

    assert "\n    env_file:" in auth_block
    assert "\n    env_file:" not in gateway_block


def test_auth_dockerfile_does_not_copy_private_env() -> None:
    """Проверяет safe `.env.example` и отсутствие private `.env` в image."""
    dockerfile = (PROJECT_ROOT / "services" / "auth-service" / "Dockerfile").read_text(
        encoding="utf-8"
    )

    assert "COPY .env.example .env.example" in dockerfile

    assert "COPY .env " not in dockerfile


def test_auth_sources_have_docstrings() -> None:
    """Проверяет documentation discipline всех Python files Auth."""
    missing: list[str] = []

    for python_file in AUTH_ROOT.rglob("*.py"):
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

    assert not missing, f"Missing Auth docstrings: {missing}"
