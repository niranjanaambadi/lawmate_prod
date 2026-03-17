"""
app/utils/pdf_extractor.py

PDF text extraction for the Drafting AI feature.

Strategy:
  1. Try pypdf native text extraction.
  2. If the extracted text is sparse (<100 avg chars/page) and pytesseract is
     available, fall back to pdf2image → PIL → Tesseract OCR.
  3. Returns (text, page_count, was_ocr_used).

Never raises — returns a descriptive placeholder on unrecoverable failure so
the rest of the pipeline can proceed with partial data.
"""
from __future__ import annotations

import io
import logging

logger = logging.getLogger(__name__)

_MIN_CHARS_PER_PAGE = 100   # below this → assume scanned / image PDF


def extract_text_from_pdf(file_bytes: bytes) -> tuple[str, int, bool]:
    """
    Extract plain text from a PDF supplied as raw bytes.

    Returns
    -------
    (text, page_count, was_ocr_used)
        text         — extracted plain text (may be empty string on hard failure)
        page_count   — number of pages detected (0 on failure)
        was_ocr_used — True if OCR was applied
    """
    # ── 1. pypdf native ───────────────────────────────────────────────────────
    try:
        import pypdf

        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        page_count = len(reader.pages)

        pages_text: list[str] = []
        for page in reader.pages:
            try:
                pages_text.append(page.extract_text() or "")
            except Exception:
                pages_text.append("")

        native_text = "\n".join(pages_text).strip()

        avg_chars = len(native_text) / max(page_count, 1)
        if avg_chars >= _MIN_CHARS_PER_PAGE:
            logger.debug(
                "pdf_extractor: pypdf native OK, %d pages, %.0f avg chars/page",
                page_count, avg_chars,
            )
            return native_text, page_count, False

        logger.info(
            "pdf_extractor: sparse native text (%.0f avg chars/page) → trying OCR",
            avg_chars,
        )

    except Exception as exc:
        logger.warning("pdf_extractor: pypdf failed (%s) → trying OCR", exc)
        page_count = 0
        native_text = ""

    # ── 2. OCR fallback ───────────────────────────────────────────────────────
    try:
        import pytesseract
        from pdf2image import convert_from_bytes
        from PIL import Image

        images: list[Image.Image] = convert_from_bytes(
            file_bytes,
            dpi=200,
            fmt="jpeg",
        )
        if page_count == 0:
            page_count = len(images)

        ocr_pages: list[str] = []
        for img in images:
            try:
                text = pytesseract.image_to_string(img, lang="eng")
                ocr_pages.append(text)
            except Exception as ocr_exc:
                logger.debug("pdf_extractor: OCR page failed: %s", ocr_exc)
                ocr_pages.append("")

        ocr_text = "\n".join(ocr_pages).strip()
        logger.info(
            "pdf_extractor: OCR produced %d chars from %d pages",
            len(ocr_text), len(images),
        )
        return ocr_text, page_count, True

    except Exception as exc:
        logger.error("pdf_extractor: OCR fallback failed: %s", exc)

    # ── 3. Hard failure ───────────────────────────────────────────────────────
    placeholder = (
        "[OCR failed — document may be of image quality too low or unsupported format. "
        "Please re-upload a higher-quality scan or a native PDF.]"
    )
    return placeholder, max(page_count, 0), True
