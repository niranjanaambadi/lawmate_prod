"""
Document translation service — extracts text from PDF / DOCX / TXT files,
splits into safe chunks, translates each chunk, and returns the assembled result.
"""
from __future__ import annotations

import logging
from io import BytesIO
from typing import List, Literal

logger = logging.getLogger(__name__)

Direction = Literal["en_to_ml", "ml_to_en"]

# Maximum characters per chunk sent to the LLM.
# Paragraph boundaries are preferred; hard split is the fallback.
_MAX_CHUNK_CHARS = 3000
_OVERLAP_CHARS = 100  # slight overlap to keep sentence context at boundaries


# ── Text extraction helpers ────────────────────────────────────────────────


def _extract_pdf_force_ocr(data: bytes, lang: str = "mal+eng") -> str:
    """
    Extract text from a PDF using the same Force-OCR path as the OCR page:
      1. Render each page with PyMuPDF (fitz) at 2× scale → PIL image.
      2. Run Tesseract with *lang* (default "mal+eng") on every page.
      3. If Tesseract yields nothing for a page, fall back to pypdf native
         text for that page only (same merge logic as the OCR page).

    This is the canonical path for scanned / image-based PDFs such as
    court orders and Malayalam legal documents.
    """
    try:
        import fitz  # type: ignore  (PyMuPDF)
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore

        # ── render pages via fitz ──────────────────────────────────────────
        doc = fitz.open(stream=data, filetype="pdf")
        ocr_pages: List[str] = []
        for page in doc:
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            mode = "RGBA" if pix.alpha else "RGB"
            image = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
            try:
                text = pytesseract.image_to_string(image, lang=lang).strip()
            except Exception as ocr_exc:
                logger.debug("_extract_pdf_force_ocr: page OCR failed: %s", ocr_exc)
                text = ""
            ocr_pages.append(text)
        doc.close()

        # ── fallback: for any page where OCR produced nothing, try pypdf ──
        has_blank = any(not t for t in ocr_pages)
        if has_blank:
            try:
                import io as _io
                import pypdf  # type: ignore

                reader = pypdf.PdfReader(_io.BytesIO(data))
                native_pages = [
                    (reader.pages[i].extract_text() or "").strip()
                    for i in range(len(reader.pages))
                ]
                merged = [
                    ocr_pages[i] if ocr_pages[i] else native_pages[i]
                    for i in range(min(len(ocr_pages), len(native_pages)))
                ]
                ocr_pages = merged
            except Exception as native_exc:
                logger.debug(
                    "_extract_pdf_force_ocr: native fallback failed: %s", native_exc
                )

        result = "\n\n".join(ocr_pages).strip()
        logger.info(
            "_extract_pdf_force_ocr: %d pages, lang=%s, %d chars extracted",
            len(ocr_pages), lang, len(result),
        )
        return result

    except Exception as exc:
        logger.error("_extract_pdf_force_ocr failed: %s", exc)
        # Last resort — old threshold-based path
        return _extract_pdf_threshold_fallback(data, ocr_lang=lang)


def _extract_pdf_threshold_fallback(data: bytes, ocr_lang: str = "mal+eng") -> str:
    """
    Legacy threshold-based extraction kept as a last-resort fallback.
    Tries pypdf native; if sparse, falls back to pdf2image + Tesseract.
    """
    import io as _io

    try:
        import pypdf  # type: ignore

        reader = pypdf.PdfReader(_io.BytesIO(data))
        page_count = len(reader.pages)
        pages_text: List[str] = []
        for page in reader.pages:
            try:
                pages_text.append(page.extract_text() or "")
            except Exception:
                pages_text.append("")

        native_text = "\n\n".join(pages_text).strip()
        avg_chars = len(native_text) / max(page_count, 1)

        if avg_chars >= 200:
            return native_text

    except Exception as exc:
        logger.warning("_extract_pdf_threshold_fallback: pypdf failed (%s)", exc)
        page_count = 0
        native_text = ""

    try:
        import pytesseract  # type: ignore
        from pdf2image import convert_from_bytes  # type: ignore
        from PIL import Image  # type: ignore

        images: List[Image.Image] = convert_from_bytes(data, dpi=200, fmt="jpeg")
        ocr_pages: List[str] = []
        for img in images:
            try:
                ocr_pages.append(pytesseract.image_to_string(img, lang=ocr_lang))
            except Exception:
                ocr_pages.append("")
        return "\n\n".join(ocr_pages).strip()

    except Exception as exc:
        logger.error("_extract_pdf_threshold_fallback: OCR also failed: %s", exc)

    return (
        "[Text extraction failed — the PDF appears to be image-only and OCR "
        "could not process it. Please upload a native PDF or a TXT file.]"
    )


def _extract_docx(data: bytes) -> str:
    """Extract plain text from a DOCX byte blob."""
    try:
        import docx  # type: ignore  (python-docx)
    except ImportError:
        raise RuntimeError(
            "python-docx is required for DOCX extraction (pip install python-docx)"
        )

    doc = docx.Document(BytesIO(data))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs)


def _extract_txt(data: bytes) -> str:
    """Decode a plain-text byte blob (UTF-8 with latin-1 fallback)."""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1", errors="replace")


def extract_text(data: bytes, mime_type: str, ocr_lang: str = "mal+eng") -> str:
    """
    Dispatch to the right extractor based on MIME type.

    For PDFs: always uses the Force-OCR path (fitz + Tesseract mal+eng),
    same as ticking "Force OCR" on the OCR page.  This correctly handles
    scanned Malayalam court documents that fool pypdf into returning
    garbled or empty text.

    Supported: application/pdf, application/vnd.openxmlformats-officedocument.wordprocessingml.document,
               text/plain.
    """
    if mime_type == "application/pdf":
        return _extract_pdf_force_ocr(data, lang=ocr_lang)
    if mime_type in (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    ):
        return _extract_docx(data)
    if mime_type.startswith("text/"):
        return _extract_txt(data)
    raise ValueError(f"Unsupported MIME type for translation: {mime_type}")


# ── Chunking ───────────────────────────────────────────────────────────────


def chunk_text(text: str, max_chars: int = _MAX_CHUNK_CHARS) -> List[str]:
    """
    Split *text* into chunks of at most *max_chars* characters, preferring
    paragraph boundaries (double newline) over mid-sentence splits.
    """
    if len(text) <= max_chars:
        return [text]

    # Split on paragraph boundaries first
    paragraphs = text.split("\n\n")
    chunks: List[str] = []
    current = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        # If adding this paragraph would exceed the limit, flush current
        candidate = (current + "\n\n" + para).lstrip() if current else para
        if len(candidate) > max_chars and current:
            chunks.append(current.strip())
            current = para
        else:
            current = candidate

    if current:
        chunks.append(current.strip())

    # Second pass: hard-split any chunk that's still too long
    final_chunks: List[str] = []
    for chunk in chunks:
        if len(chunk) <= max_chars:
            final_chunks.append(chunk)
        else:
            # Hard split preserving whole words where possible
            for i in range(0, len(chunk), max_chars - _OVERLAP_CHARS):
                sub = chunk[i : i + max_chars]
                if sub:
                    final_chunks.append(sub)

    return final_chunks


# ── Orchestrator ───────────────────────────────────────────────────────────


class DocumentTranslateService:
    """
    High-level service that orchestrates full document translation.
    """

    def translate_document_text(
        self,
        text: str,
        direction: Direction,
    ) -> dict:
        """
        Translate a (potentially long) document text.

        Parameters
        ----------
        text      : extracted plain text from document
        direction : "en_to_ml" | "ml_to_en"

        Returns
        -------
        {
          "translated": str,
          "chunks": int,
          "glossary_hits": int,
          "warnings": list[str],
        }
        """
        # Import here to avoid circular imports at module load time
        from .llm_translate_service import llm_translate_service
        from .protect_service import protect_service
        from .glossary_service import glossary_service

        chunks = chunk_text(text)
        logger.info(
            "document_translate: %d chars → %d chunks (direction=%s)",
            len(text), len(chunks), direction,
        )

        translated_parts: List[str] = []
        all_warnings: List[str] = []
        total_glossary_hits = 0

        for idx, chunk in enumerate(chunks):
            protected, pmap = protect_service.protect_text(chunk)
            try:
                translated_protected = llm_translate_service.translate_chunk(
                    protected, direction
                )
            except RuntimeError as exc:
                logger.error("Chunk %d/%d translation failed: %s", idx + 1, len(chunks), exc)
                # Keep original chunk on failure so document is still usable
                translated_parts.append(chunk)
                all_warnings.append(f"Chunk {idx + 1} failed: {exc}")
                continue

            restored = protect_service.restore_text(translated_protected, pmap)
            warnings = protect_service.validate_protection(chunk, restored)
            all_warnings.extend(warnings)

            hits = len(glossary_service.find_matches(chunk, direction))
            total_glossary_hits += hits

            translated_parts.append(restored)
            logger.debug(
                "Chunk %d/%d done — glossary_hits=%d warnings=%d",
                idx + 1, len(chunks), hits, len(warnings),
            )

        return {
            "translated": "\n\n".join(translated_parts),
            "chunks": len(chunks),
            "glossary_hits": total_glossary_hits,
            "warnings": all_warnings,
        }

    def translate_bytes(
        self,
        data: bytes,
        mime_type: str,
        direction: Direction,
    ) -> dict:
        """
        Extract text from raw file bytes, then translate.

        PDFs always go through the Force-OCR path (fitz + Tesseract mal+eng)
        — the same workflow as ticking "Force OCR" on the OCR page.  This
        avoids the garbled-text problem that occurs when pypdf tries to read
        a scanned Malayalam PDF.

        Returns the same dict as translate_document_text, plus "char_count".
        """
        text = extract_text(data, mime_type, ocr_lang="mal+eng")
        if not text.strip():
            logger.warning(
                "translate_bytes: extraction produced empty text for mime=%s", mime_type
            )
        result = self.translate_document_text(text, direction)
        result["char_count"] = len(text)
        return result


# Module-level singleton
document_translate_service = DocumentTranslateService()
