# tests/architecture/test_api_gateway_contract.py

"""Architecture tests boundaries и deployment contract API Gateway."""

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

GATEWAY_ROOT = PROJECT_ROOT / "services" / "api-gateway" / "src" / "api_gateway"


def read_project_file(
    relative_path: str,
) -> str:
    """Читает UTF-8 project file для architecture assertions."""
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def imported_root_modules(
    python_file: Path,
) -> set[str]:
    """Возвращает root package names всех import statements Python-файла."""
    tree = ast.parse(
        python_file.read_text(encoding="utf-8"),
        filename=str(python_file),
    )

    modules: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(
            node,
            ast.Import,
        ):
            for alias in node.names:
                modules.add(alias.name.split(".")[0])

        if (
            isinstance(
                node,
                ast.ImportFrom,
            )
            and node.module
        ):
            modules.add(node.module.split(".")[0])

    return modules


def test_gateway_required_files_exist() -> None:
    """Проверяет минимальную структуру API Gateway stage."""
    required_files = (
        "services/api-gateway/Dockerfile",
        "services/api-gateway/pyproject.toml",
        "services/api-gateway/src/api_gateway/main.py",
        "services/api-gateway/src/api_gateway/core/container.py",
        "services/api-gateway/src/api_gateway/core/settings.py",
        "services/api-gateway/src/api_gateway/application/internal_service.py",
        "services/api-gateway/src/api_gateway/application/system_info.py",
        "services/api-gateway/src/api_gateway/infrastructure/http_client.py",
        "services/api-gateway/src/api_gateway/transport/app.py",
        "services/api-gateway/src/api_gateway/transport/errors.py",
        "services/api-gateway/src/api_gateway/transport/middleware.py",
        "services/api-gateway/src/api_gateway/transport/routers/health.py",
        "services/api-gateway/src/api_gateway/transport/routers/system.py",
        "services/api-gateway/src/api_gateway/transport/routers/api_v1.py",
    )

    missing_files = [path for path in required_files if not (PROJECT_ROOT / path).is_file()]

    assert not missing_files, f"Missing Gateway files: {missing_files}"


def test_application_layer_has_no_transport_or_infrastructure_frameworks() -> None:
    """Запрещает FastAPI/HTTPX/SQLAlchemy/Celery/Qdrant imports в application."""
    forbidden_modules = {
        "fastapi",
        "starlette",
        "httpx",
        "sqlalchemy",
        "celery",
        "qdrant_client",
        "ollama",
    }

    application_root = GATEWAY_ROOT / "application"

    for python_file in application_root.rglob("*.py"):
        imports = imported_root_modules(python_file)

        assert imports.isdisjoint(forbidden_modules), (
            f"{python_file} imports forbidden modules: {imports & forbidden_modules}"
        )


def test_resource_routers_do_not_import_infrastructure() -> None:
    """Не позволяет HTTP routers обращаться к concrete adapters напрямую."""
    router_root = GATEWAY_ROOT / "transport" / "routers"

    for python_file in router_root.glob("*.py"):
        imports = imported_root_modules(python_file)

        assert "httpx" not in imports
        assert "sqlalchemy" not in imports

        source = python_file.read_text(encoding="utf-8")

        assert "api_gateway.infrastructure" not in source


def test_gateway_package_versions_are_pinned() -> None:
    """Проверяет воспроизводимые Gateway runtime dependencies."""
    pyproject = read_project_file("services/api-gateway/pyproject.toml")

    required_versions = (
        "fastapi==0.141.1",
        "httpx==0.28.1",
        "uvicorn==0.52.1",
        "plan-validator-common==0.1.0",
    )

    for version_marker in required_versions:
        assert version_marker in pyproject


def test_gateway_compose_runtime_is_bounded_and_non_root() -> None:
    """Проверяет healthcheck, log mount и security constraints Gateway container."""
    compose = read_project_file("compose.yaml")

    required_markers = (
        "api-gateway:",
        "services/api-gateway/Dockerfile",
        "./var/log:/var/log/plan-validator",
        "read_only: true",
        "no-new-privileges:true",
        "cap_drop:",
        "PLAN_VALIDATOR_RUNTIME_UID",
        "/health/live",
    )

    for marker in required_markers:
        assert marker in compose


def test_gateway_dockerfile_uses_pinned_python_and_non_root_user() -> None:
    """Проверяет runtime image baseline и запрет root execution."""
    dockerfile = read_project_file("services/api-gateway/Dockerfile")

    assert "FROM python:3.12.14-slim-bookworm" in dockerfile
    assert "USER 1000:1000" in dockerfile


def test_gateway_has_versioned_public_api() -> None:
    """Фиксирует стабильный `/api/v1` prefix отдельно от operational health."""
    api_v1 = read_project_file("services/api-gateway/src/api_gateway/transport/routers/api_v1.py")
    health = read_project_file("services/api-gateway/src/api_gateway/transport/routers/health.py")

    assert 'prefix="/api/v1"' in api_v1
    assert 'prefix="/health"' in health


def test_gateway_sources_have_module_and_callable_docstrings() -> None:
    """Проверяет русскоязычный documentation discipline нового service."""
    missing_docstrings: list[str] = []

    for python_file in GATEWAY_ROOT.rglob("*.py"):
        tree = ast.parse(
            python_file.read_text(encoding="utf-8"),
            filename=str(python_file),
        )

        if ast.get_docstring(tree) is None:
            missing_docstrings.append(f"{python_file}: module")

        for node in ast.walk(tree):
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

    assert not missing_docstrings, f"Missing API Gateway docstrings: {missing_docstrings}"
