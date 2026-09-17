# services/document-service/src/document_service/infrastructure/pdf_processor.py

"""PyMuPDF extraction/render и deterministic modality assessment."""

import asyncio
from contextlib import suppress
from dataclasses import dataclass

import fitz

from document_service.application.dto import DraftFragment, PdfInspection, ProcessedPageDraft
from document_service.application.ports.ocr import OcrEngine
from document_service.domain.models import BoundingBox, ContentModality, TextOrigin


class PyMuPdfProcessor:
    """Извлекает native/OCR text и visual page representation."""

    def __init__(
        self,
        *,
        render_dpi: int,
        native_text_min_chars: int,
        visual_area_threshold: float,
        ocr_enabled: bool,
        ocr_engine: OcrEngine,
    ) -> None:
        """Сохраняет deterministic modality thresholds."""
        self._render_dpi = render_dpi
        self._native_min = native_text_min_chars
        self._visual_threshold = visual_area_threshold
        self._ocr_enabled = ocr_enabled
        self._ocr = ocr_engine

    def inspect(self, content: bytes) -> PdfInspection:
        """Открывает PDF in-memory и возвращает page count."""
        with fitz.open(stream=content, filetype="pdf") as document:
            return PdfInspection(page_count=document.page_count)

    async def process_pages(
        self,
        *,
        content: bytes,
        page_numbers: tuple[int, ...],
    ) -> tuple[ProcessedPageDraft, ...]:
        """Создаёт page renders и parser-neutral fragments без блокировки event loop."""
        prepared_pages = await asyncio.to_thread(
            _prepare_pages,
            content,
            page_numbers,
            self._render_dpi,
        )
        result: list[ProcessedPageDraft] = []

        for prepared in prepared_pages:
            fragments = list(prepared.native_fragments)
            used_ocr = False

            if prepared.native_text_chars >= self._native_min:
                if prepared.visual_area_ratio >= self._visual_threshold:
                    joined = "\n".join(
                        fragment.text or "" for fragment in prepared.native_fragments
                    ).strip()
                    fragments.append(
                        DraftFragment(
                            fragment_id=f"p{prepared.page_number}-mixed",
                            page_number=prepared.page_number,
                            modality=ContentModality.MIXED,
                            text_origin=TextOrigin.NATIVE,
                            text=joined or None,
                            bbox=BoundingBox(0.0, 0.0, 1.0, 1.0),
                        )
                    )
            elif self._ocr_enabled:
                fragments.clear()
                ocr = await self._ocr.extract(prepared.render_png)
                if ocr:
                    used_ocr = True
                    for index, item in enumerate(ocr, start=1):
                        fragments.append(
                            DraftFragment(
                                fragment_id=f"p{prepared.page_number}-ocr-{index}",
                                page_number=prepared.page_number,
                                modality=ContentModality.TEXT,
                                text_origin=TextOrigin.OCR,
                                text=item.text,
                                bbox=_pixel_bbox(
                                    left=item.left,
                                    top=item.top,
                                    width=item.width,
                                    height=item.height,
                                    image_width=prepared.image_width,
                                    image_height=prepared.image_height,
                                ),
                                ocr_confidence=item.confidence,
                            )
                        )
                    if prepared.visual_area_ratio >= self._visual_threshold:
                        fragments.append(
                            DraftFragment(
                                fragment_id=f"p{prepared.page_number}-mixed",
                                page_number=prepared.page_number,
                                modality=ContentModality.MIXED,
                                text_origin=TextOrigin.OCR,
                                text="\n".join(item.text for item in ocr).strip() or None,
                                bbox=BoundingBox(0.0, 0.0, 1.0, 1.0),
                                ocr_confidence=(sum(item.confidence for item in ocr) / len(ocr)),
                            )
                        )

            if not fragments:
                fragments.append(
                    DraftFragment(
                        fragment_id=f"p{prepared.page_number}-image",
                        page_number=prepared.page_number,
                        modality=ContentModality.IMAGE,
                        text_origin=TextOrigin.NONE,
                        text=None,
                        bbox=BoundingBox(0.0, 0.0, 1.0, 1.0),
                    )
                )

            result.append(
                ProcessedPageDraft(
                    page_number=prepared.page_number,
                    render_png=prepared.render_png,
                    fragments=tuple(fragments),
                    native_text_chars=prepared.native_text_chars,
                    visual_area_ratio=prepared.visual_area_ratio,
                    used_ocr=used_ocr,
                )
            )

        return tuple(result)


@dataclass(frozen=True, slots=True)
class _PreparedPage:
    """CPU-heavy PyMuPDF result до optional async OCR."""

    page_number: int
    render_png: bytes
    image_width: int
    image_height: int
    native_fragments: tuple[DraftFragment, ...]
    native_text_chars: int
    visual_area_ratio: float


def _prepare_pages(
    content: bytes,
    page_numbers: tuple[int, ...],
    render_dpi: int,
) -> tuple[_PreparedPage, ...]:
    """Выполняет blocking PyMuPDF extraction/render в worker thread."""
    result: list[_PreparedPage] = []
    with fitz.open(stream=content, filetype="pdf") as document:
        for page_number in page_numbers:
            page = document.load_page(page_number - 1)
            pixmap = page.get_pixmap(dpi=render_dpi, alpha=False)
            native = _native_fragments(page, page_number)
            result.append(
                _PreparedPage(
                    page_number=page_number,
                    render_png=pixmap.tobytes("png"),
                    image_width=pixmap.width,
                    image_height=pixmap.height,
                    native_fragments=native,
                    native_text_chars=sum(len(fragment.text or "") for fragment in native),
                    visual_area_ratio=_visual_area_ratio(page),
                )
            )
    return tuple(result)


def _native_fragments(page: fitz.Page, page_number: int) -> tuple[DraftFragment, ...]:
    """Преобразует native PDF text blocks в normalized fragments."""
    result: list[DraftFragment] = []
    width = page.rect.width
    height = page.rect.height
    for index, block in enumerate(page.get_text("blocks"), start=1):
        x0, y0, x1, y1, text, *_ = block
        cleaned = " ".join(str(text).split())
        if not cleaned:
            continue
        result.append(
            DraftFragment(
                fragment_id=f"p{page_number}-native-{index}",
                page_number=page_number,
                modality=ContentModality.TEXT,
                text_origin=TextOrigin.NATIVE,
                text=cleaned,
                bbox=_pdf_bbox(x0, y0, x1, y1, width, height),
            )
        )
    return tuple(result)


def _visual_area_ratio(page: fitz.Page) -> float:
    """Оценивает долю raster/vector visuals по bbox area без ML classifier."""
    page_area = max(page.rect.width * page.rect.height, 1.0)
    area = 0.0
    with suppress(Exception):
        for item in page.get_image_info():
            bbox = fitz.Rect(item.get("bbox"))
            area += max(0.0, bbox.width * bbox.height)
    with suppress(Exception):
        for drawing in page.get_drawings():
            rect = drawing.get("rect")
            if rect is not None:
                bbox = fitz.Rect(rect)
                area += max(0.0, bbox.width * bbox.height)
    return min(1.0, area / page_area)


def _pdf_bbox(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    width: float,
    height: float,
) -> BoundingBox:
    """Нормализует PDF coordinates."""
    return BoundingBox(
        max(0.0, min(1.0, x0 / width)),
        max(0.0, min(1.0, y0 / height)),
        max(0.0, min(1.0, x1 / width)),
        max(0.0, min(1.0, y1 / height)),
    )


def _pixel_bbox(
    *,
    left: int,
    top: int,
    width: int,
    height: int,
    image_width: int,
    image_height: int,
) -> BoundingBox:
    """Нормализует OCR pixel bbox."""
    x0 = max(0.0, min(1.0, left / image_width))
    y0 = max(0.0, min(1.0, top / image_height))
    x1 = max(x0 + 1e-9, min(1.0, (left + max(width, 1)) / image_width))
    y1 = max(y0 + 1e-9, min(1.0, (top + max(height, 1)) / image_height))
    return BoundingBox(x0, y0, x1, y1)
