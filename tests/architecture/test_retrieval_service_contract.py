# tests/architecture/test_retrieval_service_contract.py

"""Architecture tests Stage 9 managed N/U indexing and Retrieval Service."""

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RETRIEVAL_ROOT = PROJECT_ROOT / "services" / "retrieval-service" / "src" / "retrieval_service"


def read_project_file(relative_path: str) -> str:
    """Читает UTF-8 project file для architecture assertions."""
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def imported_root_modules(python_file: Path) -> set[str]:
    """Возвращает root modules imports одного Python source file."""
    tree = ast.parse(
        python_file.read_text(encoding="utf-8"),
        filename=str(python_file),
    )
    result: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module.split(".")[0])

    return result


def test_retrieval_application_domain_are_framework_independent() -> None:
    """Запрещает FastAPI/SQLAlchemy/Rabbit/Qdrant/GPU в business layers."""
    forbidden = {
        "aio_pika",
        "fastapi",
        "psycopg",
        "qdrant_client",
        "sentence_transformers",
        "sqlalchemy",
        "starlette",
        "torch",
        "transformers",
    }

    for layer in ("application", "domain"):
        for python_file in (RETRIEVAL_ROOT / layer).rglob("*.py"):
            imports = imported_root_modules(python_file)
            assert imports.isdisjoint(forbidden), (
                f"{python_file} imports forbidden modules: {imports & forbidden}"
            )


def test_retrieval_does_not_parse_managed_source_files() -> None:
    """Фиксирует Stage 11 ownership PDF/DOC/DOCX extraction/rendering."""
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in RETRIEVAL_ROOT.rglob("*.py")
    ).casefold()

    forbidden = (
        "pdfplumber",
        "pymupdf",
        "fitz.open",
        "python-docx",
        "libreoffice",
        "tesseract",
        "storage_key",
    )

    for marker in forbidden:
        assert marker not in source

    assert "normalizedchunk" in source


def test_retrieval_uses_one_shared_qdrant_collection_and_stable_alias() -> None:
    """Защищает payload multitenancy от collection-per-document antipattern."""
    settings = read_project_file(
        "services/retrieval-service/src/retrieval_service/core/settings.py"
    )
    initializer = read_project_file(
        "services/retrieval-service/src/retrieval_service/infrastructure/qdrant_initializer.py"
    )

    assert "plan_validator_managed_sources_v1" in settings
    assert "plan_validator_managed_sources" in settings
    assert "is_tenant=True" in initializer
    assert 'field_name="user_id"' in initializer
    assert "payload_m=16" in initializer
    assert "m=0" in initializer
    assert "source_id" in initializer
    assert "version_key" in initializer


def test_retrieval_search_always_uses_tenant_type_and_active_version_filters() -> None:
    """Фиксирует DB-active generation и N/U isolation перед Qdrant query."""
    use_case = read_project_file(
        "services/retrieval-service/src/retrieval_service/application/use_cases/search_sources.py"
    )
    vector_store = read_project_file(
        "services/retrieval-service/src/retrieval_service/infrastructure/vector_store/qdrant.py"
    )

    assert "list_active_version_keys" in use_case
    assert 'self._match_value("user_id"' in vector_store
    assert 'self._match_value("kind"' in vector_store
    assert 'key="version_key"' in vector_store
    assert "MatchAny" in vector_store


def test_reindex_candidate_is_activated_in_db_before_old_qdrant_cleanup() -> None:
    """Фиксирует crash-safe candidate→DB switch→obsolete cleanup sequence."""
    source = read_project_file(
        "services/retrieval-service/src/retrieval_service/application/use_cases/index_source.py"
    )

    upsert = source.index("upsert_version")
    lock = source.index("get_for_update", upsert)
    commit = source.index("await uow.commit()", lock)
    cleanup = source.index("delete_obsolete_versions", commit)

    assert upsert < lock < commit < cleanup
    assert "delete_version" in source


def test_catalog_delete_excludes_db_source_before_vector_cleanup() -> None:
    """Фиксирует immediate search exclusion перед best-effort physical cleanup."""
    source = read_project_file(
        "services/retrieval-service/src/retrieval_service/application/use_cases/catalog_events.py"
    )

    mark_deleted = source.index("mark_deleted")
    commit = source.index("await uow.commit()", mark_deleted)
    cleanup = source.index("delete_source", commit)

    assert mark_deleted < commit < cleanup


def test_retrieval_embedding_is_batch_rpc_not_local_gpu() -> None:
    """GPU остаётся owned Embedding worker, Retrieval использует batch RPC."""
    gateway = read_project_file(
        "services/retrieval-service/src/retrieval_service/"
        "infrastructure/messaging/embedding_gateway.py"
    )
    embedding_schema = read_project_file(
        "services/embedding-service/src/embedding_service/infrastructure/messaging/schemas.py"
    )
    embedding_runtime = read_project_file(
        "services/embedding-service/src/embedding_service/infrastructure/gpu_runtime.py"
    )

    assert '"texts": list(texts)' in gateway
    assert "EmbeddingBatchJobRequest" in embedding_schema
    assert "EmbeddingBatchJobSuccess" in embedding_schema
    assert "embed_texts" in embedding_runtime

    retrieval_source = "\n".join(
        path.read_text(encoding="utf-8") for path in RETRIEVAL_ROOT.rglob("*.py")
    )
    assert "torch.cuda" not in retrieval_source
    assert "SentenceTransformer" not in retrieval_source


def test_retrieval_routers_keep_normative_and_user_search_separate() -> None:
    """N и U имеют отдельные typed transport endpoints."""
    routers = RETRIEVAL_ROOT / "transport" / "routers"
    normative = (routers / "normative.py").read_text(encoding="utf-8")
    user = (routers / "user.py").read_text(encoding="utf-8")

    assert 'prefix="/internal/v1/retrieval/normative"' in normative
    assert "SourceKind.NORMATIVE" in normative
    assert 'prefix="/internal/v1/retrieval/user"' in user
    assert "SourceKind.USER" in user


def test_search_response_contains_stable_clickable_catalog_source_url() -> None:
    """Retrieval evidence ссылается на Catalog API identity, не filesystem path."""
    schema = read_project_file(
        "services/retrieval-service/src/retrieval_service/transport/schemas.py"
    )

    assert "source_content_url: str" in schema
    assert "/api/v1/catalog/" in schema
    assert "normative-documents" in schema
    assert "user-documents" in schema
    assert "storage_key" not in schema


def test_retrieval_compose_services_are_internal_non_gpu_and_pydantic_first() -> None:
    """Проверяет deployment boundaries service/worker/migrate/init."""
    compose = read_project_file("compose.yaml")

    service_start = compose.index("\n  retrieval-service:\n")
    worker_start = compose.index("\n  retrieval-worker:\n")
    migrate_start = compose.index("\n  retrieval-migrate:\n")
    init_start = compose.index("\n  retrieval-init:\n")
    gateway_start = compose.index("\n  api-gateway:\n")

    service_block = compose[service_start:worker_start]
    worker_block = compose[worker_start:migrate_start]
    migrate_block = compose[migrate_start:init_start]
    init_block = compose[init_start:gateway_start]

    assert "\n    ports:" not in service_block
    assert "\n    expose:" in service_block
    assert "\n    environment:" not in service_block
    assert "\n    env_file:" in service_block
    assert "gpus:" not in service_block
    assert "gpus:" not in worker_block
    assert "- ops" in migrate_block
    assert "- ops" in init_block
    assert "alembic" in migrate_block
    assert "qdrant_initializer" in init_block


def test_retrieval_stage_declares_expected_rabbit_queues() -> None:
    """Фиксирует Catalog lifecycle/index/GPU queue namespaces."""
    env_example = read_project_file(".env.example")
    worker = read_project_file(
        "services/retrieval-service/src/retrieval_service/infrastructure/messaging/worker.py"
    )

    for marker in (
        "plan-validator.catalog.events",
        "plan-validator.retrieval.catalog-events",
        "plan-validator.retrieval.index",
        "plan-validator.gpu.embedding",
    ):
        assert marker in env_example

    assert "catalog.source.uploaded.v1" in worker
    assert "catalog.source.delete_requested.v1" in worker


def test_retrieval_migration_and_qdrant_initializer_are_explicit_one_shots() -> None:
    """Не позволяет спрятать heavy/index bootstrap в normal application startup."""
    compose = read_project_file("compose.yaml")
    app = read_project_file("services/retrieval-service/src/retrieval_service/transport/app.py")

    assert "retrieval-migrate:" in compose
    assert "retrieval-init:" in compose
    assert "create_collection" not in app
    assert "create_payload_index" not in app


def test_retrieval_stage_has_dedicated_check_and_explicit_heavy_e2e() -> None:
    """Startup проверяет runtime, а реальное GPU indexing E2E запускается отдельно."""
    up_script = read_project_file("scripts/up.sh")
    check_script = read_project_file("scripts/check-retrieval.sh")
    benchmark_script = read_project_file("scripts/benchmark-retrieval.sh")

    assert "./scripts/check-retrieval.sh --fix" in up_script
    assert "./scripts/check-retrieval.sh --check" in up_script
    assert "tests/runtime/retrieval_service" not in check_script
    assert "tests/runtime/retrieval_service" in benchmark_script


def test_retrieval_sources_have_docstrings() -> None:
    """Проверяет обязательную documentation discipline нового bounded context."""
    missing: list[str] = []

    for python_file in RETRIEVAL_ROOT.rglob("*.py"):
        tree = ast.parse(
            python_file.read_text(encoding="utf-8"),
            filename=str(python_file),
        )

        if ast.get_docstring(tree) is None:
            missing.append(f"{python_file}:module")

        for node in ast.walk(tree):
            if (
                isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                and ast.get_docstring(node) is None
            ):
                missing.append(f"{python_file}:{node.lineno}:{node.name}")

    assert not missing, f"Missing Retrieval docstrings: {missing}"
