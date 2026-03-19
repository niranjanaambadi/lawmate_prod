"""
PDF text extractor for Legal Insight jobs.
Uses PyMuPDF (fitz) to extract text blocks with coordinates.
BBox is stored as percentage of page dimensions so the frontend PdfViewer
(which expects 0-100 % values) can use them directly.
"""

from __future__ import annotations

import hashlib
from typing import Optional

import boto3
import fitz  # PyMuPDF

from app.core.config import settings
from app.core.logger import logger

# Hard cap: never send more than this many chunks to the LLM regardless of
# document length.  For a 1500-page judgment this prevents 50+ sequential
# Bedrock calls.  Chunks are sampled evenly across the document so coverage
# stays representative.
_DEFAULT_MAX_CHUNKS = 300

# OCR fallback threshold: if the average extractable characters per page falls
# below this value, the PDF is likely a scanned image rather than a text PDF.
_OCR_AVG_CHARS_THRESHOLD = 200


class LegalInsightExtractor:
    """Handles PDF download from S3, text extraction, and optional OCR fallback."""

    # ------------------------------------------------------------------
    # S3 download
    # ------------------------------------------------------------------

    def download_pdf_bytes(self, s3_bucket: str, s3_key: str) -> bytes:
        """Download the PDF from S3 and return its raw bytes."""
        s3_client = boto3.client(
            "s3",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )
        logger.info("Downloading PDF from s3://%s/%s", s3_bucket, s3_key)
        response = s3_client.get_object(Bucket=s3_bucket, Key=s3_key)
        pdf_bytes: bytes = response["Body"].read()
        logger.info(
            "Downloaded %d bytes from s3://%s/%s", len(pdf_bytes), s3_bucket, s3_key
        )
        return pdf_bytes

    # ------------------------------------------------------------------
    # SHA-256 fingerprint
    # ------------------------------------------------------------------

    def compute_sha256(self, data: bytes) -> str:
        """Return the hex-encoded SHA-256 digest of *data*."""
        return hashlib.sha256(data).hexdigest()

    # ------------------------------------------------------------------
    # Chunk extraction
    # ------------------------------------------------------------------

    def extract_chunks(
        self, pdf_bytes: bytes, max_chars: int = 3000
    ) -> list[dict]:
        """
        Extract text blocks from a PDF, normalise bbox to 0-100 % coordinates,
        and merge adjacent small blocks (same page) up to *max_chars*.

        Returns a list of chunk dicts with keys:
            chunk_id, page_number, bbox, text, char_start, char_end
        """
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        raw_chunks: list[dict] = []
        chunk_idx: int = 0
        char_offset: int = 0

        for page_num, page in enumerate(doc, start=1):
            page_width: float = page.rect.width
            page_height: float = page.rect.height

            block_dict = page.get_text("dict")
            for block in block_dict.get("blocks", []):
                if block.get("type") != 0:
                    # Skip non-text blocks (images, etc.)
                    continue

                # Assemble all span text for this block
                lines = block.get("lines", [])
                text_parts: list[str] = []
                for line in lines:
                    for span in line.get("spans", []):
                        text_parts.append(span.get("text", ""))
                text: str = "".join(text_parts).strip()

                if not text:
                    continue

                # Compute bbox as percentage of page dimensions
                b = block["bbox"]  # (x0, y0, x1, y1)
                x: float = (b[0] / page_width) * 100.0
                y: float = (b[1] / page_height) * 100.0
                width: float = ((b[2] - b[0]) / page_width) * 100.0
                height: float = ((b[3] - b[1]) / page_height) * 100.0

                chunk: dict = {
                    "chunk_id": f"chunk_{chunk_idx:06d}",
                    "page_number": page_num,
                    "bbox": {
                        "x": x,
                        "y": y,
                        "width": width,
                        "height": height,
                    },
                    "text": text,
                    "char_start": char_offset,
                    "char_end": char_offset + len(text),
                }

                char_offset += len(text)
                chunk_idx += 1
                raw_chunks.append(chunk)

        doc.close()

        # ------------------------------------------------------------------
        # Merge small adjacent chunks on the same page up to max_chars
        # ------------------------------------------------------------------
        merged: list[dict] = []
        i = 0
        while i < len(raw_chunks):
            current = dict(raw_chunks[i])  # shallow copy
            # Try to absorb subsequent chunks from the same page
            j = i + 1
            while j < len(raw_chunks):
                nxt = raw_chunks[j]
                if nxt["page_number"] != current["page_number"]:
                    break
                combined_len = len(current["text"]) + 1 + len(nxt["text"])
                if combined_len > max_chars:
                    break
                # Merge: keep first chunk's bbox/page, append text, update char_end
                current["text"] = current["text"] + " " + nxt["text"]
                current["char_end"] = nxt["char_end"]
                j += 1

            merged.append(current)
            i = j

        logger.info(
            "Extracted %d raw chunks, merged to %d chunks",
            len(raw_chunks),
            len(merged),
        )
        return merged

    # ------------------------------------------------------------------
    # Quality assessment
    # ------------------------------------------------------------------

    def assess_quality_avg_chars(self, pdf_bytes: bytes) -> float:
        """
        Return the average number of extractable characters per page.

        A value below _OCR_AVG_CHARS_THRESHOLD (200) indicates a scanned PDF
        (poor or absent text layer) and should trigger OCR fallback.
        Using per-page average is far more reliable than the old chunk-ratio
        heuristic, which almost never triggered OCR even on scanned documents.
        """
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        n_pages = len(doc)
        if n_pages == 0:
            doc.close()
            return 0.0
        total_chars = sum(len(page.get_text("text")) for page in doc)
        doc.close()
        avg = total_chars / n_pages
        logger.info(
            "PDF quality: %.1f avg chars/page over %d pages (threshold %d)",
            avg,
            n_pages,
            _OCR_AVG_CHARS_THRESHOLD,
        )
        return avg

    # ------------------------------------------------------------------
    # Chunk sampling
    # ------------------------------------------------------------------

    @staticmethod
    def _sample_chunks(chunks: list[dict], max_chunks: int) -> list[dict]:
        """
        Evenly sample *max_chunks* from *chunks*, preserving document order.
        The first and last chunks are always kept so the opening paragraph
        (case title, bench) and final order are never dropped.
        """
        if len(chunks) <= max_chunks:
            return chunks

        step = len(chunks) / max_chunks
        sampled = []
        seen: set[int] = set()
        for i in range(max_chunks):
            idx = min(int(i * step), len(chunks) - 1)
            if idx not in seen:
                sampled.append(chunks[idx])
                seen.add(idx)

        # Always keep last chunk (final order section)
        last_idx = len(chunks) - 1
        if last_idx not in seen:
            sampled.append(chunks[last_idx])

        logger.info(
            "_sample_chunks: reduced %d → %d chunks", len(chunks), len(sampled)
        )
        return sampled

    # ------------------------------------------------------------------
    # Extraction with optional OCR fallback
    # ------------------------------------------------------------------

    def extract_text_with_ocr_fallback(
        self,
        pdf_bytes: bytes,
        enable_ocr: bool,
        max_chars: int,
        max_chunks: int = _DEFAULT_MAX_CHUNKS,
    ) -> tuple[list[dict], bool]:
        """
        Extract text from *pdf_bytes*.

        OCR fallback is triggered when avg chars/page < _OCR_AVG_CHARS_THRESHOLD
        (200), which reliably detects scanned-image PDFs.

        After extraction and merging, chunks are evenly sampled down to
        *max_chunks* (default 300) to prevent extremely large documents from
        generating hundreds of sequential LLM calls.

        Returns (chunks, ocr_used).
        """
        # Quality check on raw bytes — cheaper than extracting all chunks first.
        avg_chars = self.assess_quality_avg_chars(pdf_bytes)
        needs_ocr = enable_ocr and (avg_chars < _OCR_AVG_CHARS_THRESHOLD)

        if not needs_ocr:
            chunks = self.extract_chunks(pdf_bytes, max_chars)
            chunks = self._sample_chunks(chunks, max_chunks)
            return chunks, False

        # ---- OCR fallback ------------------------------------------------
        logger.info(
            "Avg chars/page %.1f < threshold %d — running OCR fallback via fitz",
            avg_chars,
            _OCR_AVG_CHARS_THRESHOLD,
        )
        ocr_chunks: list[dict] = []
        chunk_idx = 0
        char_offset = 0

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page_num, page in enumerate(doc, start=1):
            try:
                # Use fitz's built-in OCR (requires Tesseract installed)
                tp = page.get_textpage_ocr(flags=0, full=True)
                text = tp.extractText().strip()
            except Exception:
                # Fallback: plain text extraction without OCR
                text = page.get_text("text").strip()

            if not text:
                continue

            # Split long OCR text into chunks of max_chars
            start = 0
            while start < len(text):
                chunk_text = text[start : start + max_chars].strip()
                if not chunk_text:
                    start += max_chars
                    continue

                ocr_chunks.append(
                    {
                        "chunk_id": f"chunk_{chunk_idx:06d}",
                        "page_number": page_num,
                        "bbox": None,  # No reliable bbox from OCR plain text
                        "text": chunk_text,
                        "char_start": char_offset,
                        "char_end": char_offset + len(chunk_text),
                    }
                )
                char_offset += len(chunk_text)
                chunk_idx += 1
                start += max_chars

        doc.close()
        logger.info("OCR fallback produced %d chunks", len(ocr_chunks))
        ocr_chunks = self._sample_chunks(ocr_chunks, max_chunks)
        return ocr_chunks, True


# Singleton
legal_insight_extractor = LegalInsightExtractor()
