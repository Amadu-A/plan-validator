# services/document-service/src/document_service/application/ports/ocr.py

"""Conditional OCR port Document Service."""

from typing import Protocol

from document_service.application.dto import OcrFragment


class OcrEngine(Protocol):
    """Извлекает source text из rendered page без привязки application к Tesseract."""

    async def extract(self, png_bytes: bytes) -> tuple[OcrFragment, ...]:
        """Возвращает bounded OCR fragments; пустой результат допустим."""
