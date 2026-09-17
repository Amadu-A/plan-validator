# services/document-service/src/document_service/infrastructure/ocr.py

"""Conditional Tesseract OCR adapter без Python OCR framework dependency."""

import asyncio
import csv
import io
import tempfile
from pathlib import Path

from document_service.application.dto import OcrFragment


class TesseractOcrEngine:
    """Выполняет bounded Tesseract TSV extraction для scanned-text fallback."""

    def __init__(self, *, languages: str, timeout_seconds: float) -> None:
        """Сохраняет language и timeout."""
        self._languages = languages
        self._timeout = timeout_seconds

    async def extract(self, png_bytes: bytes) -> tuple[OcrFragment, ...]:
        """Возвращает line-level OCR fragments; пустой OCR допустим."""
        with tempfile.TemporaryDirectory(prefix="plan-validator-ocr-") as directory:
            image_path = Path(directory) / "page.png"
            await asyncio.to_thread(image_path.write_bytes, png_bytes)
            process = await asyncio.create_subprocess_exec(
                "tesseract",
                str(image_path),
                "stdout",
                "-l",
                self._languages,
                "tsv",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, _ = await asyncio.wait_for(process.communicate(), timeout=self._timeout)
            except TimeoutError:
                process.kill()
                await process.communicate()
                raise
            if process.returncode != 0:
                return ()
        return _parse_tsv(stdout.decode("utf-8", errors="replace"))


def _parse_tsv(payload: str) -> tuple[OcrFragment, ...]:
    """Группирует Tesseract word rows в line fragments."""
    groups: dict[tuple[str, str, str, str], list[dict[str, str]]] = {}
    reader = csv.DictReader(io.StringIO(payload), delimiter="\t")
    for row in reader:
        text = (row.get("text") or "").strip()
        try:
            confidence = float(row.get("conf") or "-1")
        except ValueError:
            confidence = -1.0
        if not text or confidence < 0:
            continue
        key = (
            row.get("page_num", ""),
            row.get("block_num", ""),
            row.get("par_num", ""),
            row.get("line_num", ""),
        )
        groups.setdefault(key, []).append(row)

    result: list[OcrFragment] = []
    for rows in groups.values():
        text = " ".join((row.get("text") or "").strip() for row in rows).strip()
        if not text:
            continue
        lefts = [int(row.get("left") or 0) for row in rows]
        tops = [int(row.get("top") or 0) for row in rows]
        rights = [int(row.get("left") or 0) + int(row.get("width") or 0) for row in rows]
        bottoms = [int(row.get("top") or 0) + int(row.get("height") or 0) for row in rows]
        confidences = [max(0.0, float(row.get("conf") or 0.0)) for row in rows]
        result.append(
            OcrFragment(
                text=text,
                left=min(lefts),
                top=min(tops),
                width=max(rights) - min(lefts),
                height=max(bottoms) - min(tops),
                confidence=sum(confidences) / len(confidences),
            )
        )
    return tuple(result)
