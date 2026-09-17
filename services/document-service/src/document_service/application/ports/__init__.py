# services/document-service/src/document_service/application/ports/__init__.py

"""Application ports Document Service."""

from document_service.application.ports.clock import Clock
from document_service.application.ports.ocr import OcrEngine
from document_service.application.ports.pdf_processor import PdfProcessor
from document_service.application.ports.processing_limiter import ProcessingLimiter
from document_service.application.ports.repositories import ProjectDocumentRepository
from document_service.application.ports.storage import DocumentStorage
from document_service.application.ports.unit_of_work import DocumentUnitOfWorkFactory

__all__ = [
    "Clock",
    "DocumentStorage",
    "DocumentUnitOfWorkFactory",
    "OcrEngine",
    "PdfProcessor",
    "ProcessingLimiter",
    "ProjectDocumentRepository",
]
