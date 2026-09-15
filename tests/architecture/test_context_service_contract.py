# tests/architecture/test_context_service_contract.py

"""Architecture contract Stage 10 Context Service core/runtime."""

from pathlib import Path

from context_service.core.settings import ContextQueueSettings

_ROOT = Path(__file__).resolve().parents[2]

_SERVICE = _ROOT / "services" / "context-service" / "src" / "context_service"


def _python_sources(
    directory: Path,
) -> list[Path]:
    """Возвращает Python sources выбранного architecture layer."""
    return sorted(directory.rglob("*.py"))


def _read(
    relative_path: str,
) -> str:
    """Читает UTF-8 project file."""
    return (_ROOT / relative_path).read_text(encoding="utf-8")


def test_context_domain_and_application_do_not_import_frameworks() -> None:
    """Сохраняет Transport -> Application -> Domain dependency direction."""
    forbidden = (
        "fastapi",
        "sqlalchemy",
        "qdrant_client",
        "aio_pika",
        "celery",
    )

    files = [
        *_python_sources(_SERVICE / "domain"),
        *_python_sources(_SERVICE / "application"),
    ]

    for path in files:
        content = path.read_text(encoding="utf-8").casefold()

        for package in forbidden:
            assert package not in content, (
                f"{path.relative_to(_ROOT)} imports forbidden framework dependency {package}"
            )


def test_context_service_does_not_take_document_parser_ownership() -> None:
    """Stage 10 принимает normalized chunks и не парсит PDF/DOC/DOCX."""
    forbidden = (
        "pdfplumber",
        "pymupdf",
        "fitz",
        "pdfminer",
        "python-docx",
        "docx2txt",
        "tesseract",
        "ocr",
    )

    for path in _python_sources(_SERVICE):
        content = path.read_text(encoding="utf-8").casefold()

        for dependency in forbidden:
            assert dependency not in content, (
                f"{path.relative_to(_ROOT)} unexpectedly owns "
                f"document parsing dependency {dependency}"
            )


def test_context_queue_contract_prevents_thirty_minute_waits() -> None:
    """Фиксирует bounded execution, deadline, TTL, attempts, lease и drain."""
    settings = ContextQueueSettings()

    assert settings.prefetch_count == 1
    assert settings.message_ttl_ms == 900_000
    assert settings.execution_timeout_seconds <= 600
    assert settings.job_deadline_seconds <= 720
    assert settings.max_attempts <= 3
    assert settings.lease_seconds == 60
    assert settings.heartbeat_seconds == 15
    assert settings.graceful_shutdown_seconds <= 60

    assert settings.job_deadline_seconds < settings.message_ttl_ms / 1000


def test_context_semantics_are_only_t_and_pz() -> None:
    """Не допускает случайного превращения T/PZ в normative N."""
    models = _read("services/context-service/src/context_service/domain/models.py")

    search = _read("services/context-service/src/context_service/domain/search.py")

    qdrant = _read(
        "services/context-service/src/context_service/infrastructure/vector_store/qdrant.py"
    )

    assert 'TECHNICAL_ASSIGNMENT = "T"' in models

    assert 'PROJECT_NOTE = "PZ"' in models

    assert 'NORMATIVE = "N"' not in models

    assert "project_context_non_normative" in search

    assert "project_context_non_normative" in qdrant


def test_context_recovery_does_not_periodically_duplicate_dispatched_jobs() -> None:
    """Reconciler повторяет только undispatched/due/stale/expired DB states."""
    repository = _read(
        "services/context-service/src/context_service/infrastructure/database/context_repository.py"
    )

    use_cases = _read(
        "services/context-service/src/context_service/application/use_cases/index_jobs.py"
    )

    assert "redispatch_before" not in repository

    assert "redispatch_before" not in use_cases

    assert "ContextIndexJobModel.dispatched_at.is_(None)" in repository

    assert "expired_nonterminal" in repository

    assert "stale_running" in repository


def test_context_worker_has_lease_heartbeat_timeout_and_graceful_drain() -> None:
    """Фиксирует recovery semantics вместо одного длинного HTTP/Rabbit wait."""
    worker = _read(
        "services/context-service/src/context_service/infrastructure/messaging/worker.py"
    )

    required_markers = (
        "execution_timeout_seconds",
        "context_index_heartbeat",
        "stale lease recovery required",
        "graceful_shutdown_seconds",
        "queue.cancel(consumer_tag)",
        "runtime.wait_idle()",
    )

    for marker in required_markers:
        assert marker in worker

    assert worker.count("nack(requeue=True)") == 1

    assert "context_index_claim_failed" in worker


def test_context_rabbit_message_contains_only_job_identifier_not_chunks() -> None:
    """Не дублирует source text в work queue и сохраняет DB source of truth."""
    schema = _read(
        "services/context-service/src/context_service/infrastructure/messaging/schemas.py"
    )

    assert "job_id: UUID" in schema

    assert "correlation_id:" in schema

    assert "chunks" not in schema

    assert "text:" not in schema


def test_context_runtime_dependencies_are_pinned() -> None:
    """Проверяет reproducible HTTP/Rabbit/Qdrant adapter dependencies."""
    pyproject = _read("services/context-service/pyproject.toml")

    assert "fastapi==0.141.1" in pyproject

    assert "uvicorn==0.52.1" in pyproject

    assert "aio-pika==10.0.1" in pyproject

    assert "qdrant-client==1.19.0" in pyproject


def test_context_transport_does_not_import_infrastructure_directly() -> None:
    """Transport зависит от composition root/application/domain, но не adapters."""
    transport = _SERVICE / "transport"

    for path in _python_sources(transport):
        content = path.read_text(encoding="utf-8")

        assert "context_service.infrastructure" not in content, (
            f"{path.relative_to(_ROOT)} imports Context infrastructure directly"
        )


def test_context_http_surface_remains_internal_before_gateway_stage() -> None:
    """Не публикует обходной public Context API мимо API Gateway."""
    routers = _SERVICE / "transport" / "routers"

    content = "\n".join(path.read_text(encoding="utf-8") for path in _python_sources(routers))

    assert "/internal/v1/context/" in content

    assert "/api/v1/project-context" not in content
