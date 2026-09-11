# tests/architecture/test_context_service_contract.py

"""Architecture contract Stage 10 Context Service core."""

from pathlib import Path

from context_service.core.settings import ContextQueueSettings

_ROOT = Path(__file__).resolve().parents[2]
_SERVICE = _ROOT / "services" / "context-service" / "src" / "context_service"


def _python_sources(
    directory: Path,
) -> list[Path]:
    """Возвращает Python sources выбранного architecture layer."""
    return sorted(directory.rglob("*.py"))


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
    """Фиксирует bounded execution, deadline, TTL, attempts и lease."""
    settings = ContextQueueSettings()

    assert settings.prefetch_count == 1
    assert settings.message_ttl_ms == 900_000
    assert settings.execution_timeout_seconds <= 600
    assert settings.job_deadline_seconds <= 720
    assert settings.max_attempts <= 3
    assert settings.lease_seconds == 60
    assert settings.heartbeat_seconds == 15
    assert settings.job_deadline_seconds < (settings.message_ttl_ms / 1000)


def test_context_semantics_are_only_t_and_pz() -> None:
    """Не допускает случайного превращения T/PZ в normative N."""
    models_path = _SERVICE / "domain" / "models.py"
    content = models_path.read_text(encoding="utf-8")

    assert 'TECHNICAL_ASSIGNMENT = "T"' in content
    assert 'PROJECT_NOTE = "PZ"' in content
    assert 'NORMATIVE = "N"' not in content
