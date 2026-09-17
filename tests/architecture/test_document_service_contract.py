# tests/architecture/test_document_service_contract.py

"""Architecture guards Stage 11 Document Service."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "services/document-service"


def test_document_service_has_no_premature_broker_dependency() -> None:
    """CPU page processing не вводит Rabbit/Celery до benchmark."""
    pyproject = (SERVICE / "pyproject.toml").read_text(encoding="utf-8").lower()
    source = "\n".join(
        path.read_text(encoding="utf-8").lower() for path in (SERVICE / "src").rglob("*.py")
    )
    assert "celery" not in pyproject
    assert "aio-pika" not in pyproject
    assert "rabbitmq" not in source


def test_multimodal_audit_contract_exists() -> None:
    """Fragment contract различает modality и text origin."""
    models = (SERVICE / "src/document_service/domain/models.py").read_text(encoding="utf-8")
    for token in (
        'TEXT = "text"',
        'IMAGE = "image"',
        'MIXED = "mixed"',
        'OCR = "ocr"',
        'GENERATED = "generated"',
    ):
        assert token in models
