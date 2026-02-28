"""
app/services/bda_service.py

Extracts plain text from case documents using AWS Bedrock Data Automation (BDA).

Flow:
  1. If Document.extracted_text is already populated → return it immediately (cache hit).
  2. If settings.BDA_PROFILE_ARN is set → invoke BDA async, poll until done,
     download the output JSON from S3, extract plain text.
  3. Fallback (no BDA_PROFILE_ARN) → use PyMuPDF via the existing
     legal_insight_extractor to extract text directly from the PDF bytes.

In all cases the result is persisted to Document.extracted_text so subsequent
sessions never re-extract the same document.
"""

from __future__ import annotations

import json
import time
from typing import Optional

import boto3
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logger import logger
from app.db.models import Document
from app.services.legal_insight_extractor import legal_insight_extractor

# BDA job polling
_POLL_INTERVAL_S = 5
_POLL_MAX_ATTEMPTS = 60  # 5 min max


class BDAService:
    """Extracts document text via BDA (or PyMuPDF fallback)."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract_document(self, doc: Document, db: Session) -> str:
        """
        Return extracted plain text for *doc*, populating
        Document.extracted_text if not already done.

        Never raises — returns empty string on failure (caller logs warning).
        """
        if doc.extracted_text:
            logger.debug("BDA cache hit for document %s", doc.id)
            return doc.extracted_text

        try:
            if settings.BDA_PROFILE_ARN.strip():
                text = self._run_bda(doc)
            else:
                logger.info(
                    "BDA_PROFILE_ARN not set — using PyMuPDF fallback for doc %s", doc.id
                )
                text = self._run_pymupdf(doc)
        except Exception as exc:
            logger.warning("Text extraction failed for doc %s: %s", doc.id, exc)
            return ""

        if text:
            doc.extracted_text = text
            db.commit()
            logger.info(
                "Extracted %d chars for document %s (id=%s)",
                len(text),
                doc.title or doc.id,
                doc.id,
            )

        return text or ""

    # ------------------------------------------------------------------
    # BDA path
    # ------------------------------------------------------------------

    def _run_bda(self, doc: Document) -> str:
        """Invoke BDA, poll for completion, return extracted text."""
        bda_runtime = boto3.client(
            "bedrock-data-automation-runtime",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )

        input_uri  = f"s3://{doc.s3_bucket}/{doc.s3_key}"
        output_uri = (
            f"s3://{settings.S3_BUCKET_NAME}/"
            f"{settings.BDA_OUTPUT_S3_PREFIX}/{doc.id}/"
        )

        logger.info("Invoking BDA for doc %s → %s", doc.id, input_uri)
        resp = bda_runtime.invoke_data_automation_async(
            inputConfiguration={"s3Uri": input_uri},
            outputConfiguration={"s3Uri": output_uri},
            dataAutomationProfileArn=settings.BDA_PROFILE_ARN,
        )
        invocation_arn: str = resp["invocationArn"]

        # Poll until complete
        output_s3_uri = self._poll_bda(bda_runtime, invocation_arn)
        if not output_s3_uri:
            raise RuntimeError(f"BDA job {invocation_arn} did not complete successfully")

        return self._download_bda_text(output_s3_uri)

    def _poll_bda(self, bda_runtime, invocation_arn: str) -> Optional[str]:
        """
        Poll BDA status until Success/ServiceError.
        Returns the output S3 URI on success, None on failure.
        """
        for attempt in range(_POLL_MAX_ATTEMPTS):
            resp = bda_runtime.get_data_automation_status(invocationArn=invocation_arn)
            status = resp.get("status", "")

            if status == "Success":
                # outputConfiguration.s3Uri may be nested differently per SDK version
                output_cfg = resp.get("outputConfiguration", {})
                return output_cfg.get("s3Uri") or resp.get("outputS3Uri")

            if status in ("ServiceError", "ClientError", "Failed"):
                logger.error(
                    "BDA job %s failed with status %s: %s",
                    invocation_arn,
                    status,
                    resp.get("failureMessage", ""),
                )
                return None

            logger.debug(
                "BDA job %s status=%s (attempt %d/%d)",
                invocation_arn,
                status,
                attempt + 1,
                _POLL_MAX_ATTEMPTS,
            )
            time.sleep(_POLL_INTERVAL_S)

        logger.error("BDA job %s timed out after %d polls", invocation_arn, _POLL_MAX_ATTEMPTS)
        return None

    def _download_bda_text(self, output_s3_uri: str) -> str:
        """
        Download the BDA output JSON from S3 and extract all text segments.
        BDA output is a JSON file (or a folder of JSON files).
        """
        s3 = boto3.client(
            "s3",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )

        # output_s3_uri looks like s3://bucket/prefix/  or  s3://bucket/prefix/result.json
        uri = output_s3_uri.removeprefix("s3://")
        bucket, _, prefix = uri.partition("/")

        # List objects under the prefix to find JSON output files
        paginator = s3.get_paginator("list_objects_v2")
        text_parts: list[str] = []

        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if not key.endswith(".json"):
                    continue
                try:
                    body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
                    data = json.loads(body)
                    text_parts.extend(self._walk_bda_json(data))
                except Exception as exc:
                    logger.warning("Could not parse BDA output %s: %s", key, exc)

        return "\n\n".join(text_parts)

    @staticmethod
    def _walk_bda_json(data) -> list[str]:
        """
        Walk the BDA output JSON and collect all text values.
        BDA returns a nested structure; this harvests any string > 10 chars
        that isn't a metadata key.
        """
        texts: list[str] = []

        def _recurse(obj):
            if isinstance(obj, str):
                stripped = obj.strip()
                if len(stripped) > 10:
                    texts.append(stripped)
            elif isinstance(obj, dict):
                # Common BDA keys for text content
                for key in ("text", "content", "value", "extractedText", "pageText"):
                    if key in obj and isinstance(obj[key], str):
                        val = obj[key].strip()
                        if val:
                            texts.append(val)
                for v in obj.values():
                    if isinstance(v, (dict, list)):
                        _recurse(v)
            elif isinstance(obj, list):
                for item in obj:
                    _recurse(item)

        _recurse(data)
        return texts

    # ------------------------------------------------------------------
    # PyMuPDF fallback
    # ------------------------------------------------------------------

    @staticmethod
    def _run_pymupdf(doc: Document) -> str:
        """Extract text via PyMuPDF (reuses legal_insight_extractor)."""
        pdf_bytes = legal_insight_extractor.download_pdf_bytes(
            doc.s3_bucket, doc.s3_key
        )
        chunks, _ = legal_insight_extractor.extract_text_with_ocr_fallback(
            pdf_bytes,
            enable_ocr=bool(getattr(settings, "LEGAL_INSIGHT_ENABLE_OCR_FALLBACK", True)),
            max_chars=int(getattr(settings, "LEGAL_INSIGHT_MAX_CHARS_PER_CHUNK", 3000)),
        )
        return "\n\n".join(c["text"] for c in chunks if c.get("text"))


# Singleton
bda_service = BDAService()
