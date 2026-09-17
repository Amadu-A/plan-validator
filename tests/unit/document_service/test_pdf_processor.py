# tests/unit/document_service/test_pdf_processor.py

"""Unit tests real PyMuPDF native/image modality behavior."""

import asyncio

import fitz
from document_service.application.dto import OcrFragment
from document_service.domain.models import ContentModality, TextOrigin
from document_service.infrastructure.pdf_processor import PyMuPdfProcessor


class EmptyOcr:
    """OCR double, возвращающий пустой результат."""

    async def extract(self, _: bytes) -> tuple[OcrFragment, ...]:
        """Не извлекает text."""
        return ()


class TextOcr:
    """OCR double для scanned-text fallback."""

    async def extract(self, _: bytes) -> tuple[OcrFragment, ...]:
        """Возвращает один source OCR fragment."""
        return (
            OcrFragment(
                text="Scanned requirement",
                left=10,
                top=10,
                width=100,
                height=20,
                confidence=93.0,
            ),
        )


def _pdf_with_text() -> bytes:
    """Создаёт in-memory native text PDF."""
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Native project requirement text " * 4)
    payload = document.tobytes()
    document.close()
    return payload


def _blank_pdf() -> bytes:
    """Создаёт in-memory page без source text."""
    document = fitz.open()
    document.new_page()
    payload = document.tobytes()
    document.close()
    return payload


def _processor() -> PyMuPdfProcessor:
    """Создаёт processor с deterministic thresholds."""
    return PyMuPdfProcessor(
        render_dpi=96,
        native_text_min_chars=10,
        visual_area_threshold=0.3,
        ocr_enabled=True,
        ocr_engine=EmptyOcr(),
    )


def test_native_text_page_uses_native_text_without_ocr() -> None:
    """Digital PDF не должен проходить OCR fallback."""
    pages = asyncio.run(_processor().process_pages(content=_pdf_with_text(), page_numbers=(1,)))
    assert pages[0].used_ocr is False
    assert any(fragment.text_origin is TextOrigin.NATIVE for fragment in pages[0].fragments)


def test_page_without_text_falls_back_to_image() -> None:
    """Pure visual page не получает fabricated caption."""
    pages = asyncio.run(_processor().process_pages(content=_blank_pdf(), page_numbers=(1,)))
    fragment = pages[0].fragments[0]
    assert fragment.modality is ContentModality.IMAGE
    assert fragment.text_origin is TextOrigin.NONE
    assert fragment.text is None


def test_scanned_text_uses_ocr_origin() -> None:
    """Страница без native text использует OCR source text, если OCR успешен."""
    processor = PyMuPdfProcessor(
        render_dpi=96,
        native_text_min_chars=10,
        visual_area_threshold=0.3,
        ocr_enabled=True,
        ocr_engine=TextOcr(),
    )
    pages = asyncio.run(processor.process_pages(content=_blank_pdf(), page_numbers=(1,)))
    fragment = pages[0].fragments[0]
    assert pages[0].used_ocr is True
    assert fragment.modality is ContentModality.TEXT
    assert fragment.text_origin is TextOrigin.OCR
    assert fragment.text == "Scanned requirement"
