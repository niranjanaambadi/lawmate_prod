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


def _extract_pdf(data: bytes) -> str:
    """Extract plain text from a PDF byte blob."""
    try:
        import pypdf  # type: ignore
    except ImportError:
        raise RuntimeError("pypdf is required for PDF extraction (pip install pypdf)")

    reader = pypdf.PdfReader(BytesIO(data))
    pages: List[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        pages.append(text)
    return "\n\n".join(pages)


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


def extract_text(data: bytes, mime_type: str) -> str:
    """
    Dispatch to the right extractor based on MIME type.

    Supported: application/pdf, application/vnd.openxmlformats-officedocument.wordprocessingml.document,
               text/plain.
    """
    if mime_type == "application/pdf":
        return _extract_pdf(data)
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

        Returns the same dict as translate_document_text, plus "char_count".
        """
        text = extract_text(data, mime_type)
        result = self.translate_document_text(text, direction)
        result["char_count"] = len(text)
        return result


# Module-level singleton
document_translate_service = DocumentTranslateService()
