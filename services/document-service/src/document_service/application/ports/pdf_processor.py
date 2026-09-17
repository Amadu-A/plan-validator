# services/document-service/src/document_service/application/ports/pdf_processor.py

"""PDF inspection/extraction/render port Document Service."""

from typing import Protocol

from document_service.application.dto import PdfInspection, ProcessedPageDraft


class PdfProcessor(Protocol):
    """Абстрагирует PDF library и conditional OCR implementation."""

    def inspect(self, content: bytes) -> PdfInspection:
        """Проверяет PDF и возвращает page metadata."""

    async def process_pages(
        self,
        *,
        content: bytes,
        page_numbers: tuple[int, ...],
    ) -> tuple[ProcessedPageDraft, ...]:
        """Извлекает native/OCR/visual fragments и page renders."""
