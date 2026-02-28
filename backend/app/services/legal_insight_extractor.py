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

    def assess_quality(self, chunks: list[dict]) -> float:
        """
        Return the ratio of chunks whose text length exceeds 20 characters.
        A value below 0.3 suggests the PDF is likely a scanned image (poor text layer).
        """
        if not chunks:
            return 0.0
        good = sum(1 for c in chunks if len(c.get("text", "")) > 20)
        return good / len(chunks)

    # ------------------------------------------------------------------
    # Extraction with optional OCR fallback
    # ------------------------------------------------------------------

    def extract_text_with_ocr_fallback(
        self,
        pdf_bytes: bytes,
        enable_ocr: bool,
        max_chars: int,
    ) -> tuple[list[dict], bool]:
        """
        Extract text from *pdf_bytes*.  If quality is too low (< 0.3) and
        *enable_ocr* is True, attempt a simple OCR-based fallback using fitz's
        built-in text extraction after page rendering.

        Returns (chunks, ocr_used).
        """
        chunks = self.extract_chunks(pdf_bytes, max_chars)
        quality = self.assess_quality(chunks)

        logger.info(
            "Chunk quality score: %.2f (threshold 0.30), enable_ocr=%s",
            quality,
            enable_ocr,
        )

        if quality >= 0.3 or not enable_ocr:
            return chunks, False

        # ---- OCR fallback ------------------------------------------------
        logger.info("Quality below threshold — running OCR fallback via fitz")
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
        return ocr_chunks, True


# Singleton
legal_insight_extractor = LegalInsightExtractor()
