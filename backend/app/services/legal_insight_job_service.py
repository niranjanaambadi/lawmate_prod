"""
Orchestrates the full legal insight pipeline:
  queued → extracting → [ocr] → summarizing → validating → completed | failed
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime
from typing import Any, Optional

import boto3
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logger import logger
from app.db.models import (
    Case,
    Document,
    LegalInsightChunk,
    LegalInsightJob,
    LegalInsightJobStatus,
    LegalInsightResult,
    User,
)
from app.services.legal_insight_extractor import legal_insight_extractor
from app.services.legal_insight_llm_service import legal_insight_llm_service


class LegalInsightJobService:
    """
    Manages the lifecycle of a Legal Insight (Judgment Summarizer) job.

    The pipeline progresses through the following statuses:
        queued → extracting → [ocr] → summarizing → validating → completed
        (or failed at any point on error)
    """

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _set_status(
        self,
        db: Session,
        job: LegalInsightJob,
        status: LegalInsightJobStatus,
        progress: Optional[int] = None,
        error: Optional[str] = None,
    ) -> None:
        """Update job status (and optionally progress/error), then commit."""
        job.status = status
        if progress is not None:
            job.progress = progress
        if error is not None:
            job.error = error
        if status == LegalInsightJobStatus.completed:
            job.completed_at = datetime.utcnow()
        db.commit()
        logger.info(
            "Job %s → status=%s progress=%s",
            job.id,
            status.value,
            job.progress,
        )

    def _delete_upload_from_s3(self, job: LegalInsightJob) -> None:
        """
        Delete the temporary uploaded PDF from S3 once the job is terminal
        (completed or failed).  Silently skips non-upload jobs and swallows
        S3 errors so a failed delete never masks the real job outcome.
        """
        if not job.upload_s3_key or not job.upload_s3_bucket:
            return  # document-linked job — nothing to clean up
        try:
            s3_client = boto3.client(
                "s3",
                region_name=settings.AWS_REGION,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            )
            s3_client.delete_object(
                Bucket=job.upload_s3_bucket,
                Key=job.upload_s3_key,
            )
            logger.info(
                "Deleted upload PDF s3://%s/%s after job %s",
                job.upload_s3_bucket,
                job.upload_s3_key,
                job.id,
            )
        except Exception as exc:
            logger.warning(
                "Could not delete upload PDF s3://%s/%s for job %s: %s",
                job.upload_s3_bucket,
                job.upload_s3_key,
                job.id,
                exc,
            )

    # ------------------------------------------------------------------
    # Job creation
    # ------------------------------------------------------------------

    def create_job(
        self,
        db: Session,
        user: User,
        document_id: str,
    ) -> LegalInsightJob:
        """
        Create a new LegalInsightJob for *document_id*, owned by *user*.

        Raises HTTPException 404 if the document is not found, and 403 if the
        caller does not own the associated case.
        """
        doc = db.query(Document).filter(Document.id == document_id).first()
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found")

        case = db.query(Case).filter(Case.id == doc.case_id).first()
        if case is None:
            raise HTTPException(status_code=404, detail="Associated case not found")

        if str(case.advocate_id) != str(user.id):
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to summarize this document",
            )

        model_id: str = (
            getattr(settings, "LEGAL_INSIGHT_MODEL_ID", "") or settings.BEDROCK_MODEL_ID
        ).strip()
        prompt_version: str = getattr(
            settings, "LEGAL_INSIGHT_PROMPT_VERSION", "v1"
        )

        job = LegalInsightJob(
            user_id=str(user.id),
            document_id=str(document_id),
            model_id=model_id,
            prompt_version=prompt_version,
            status=LegalInsightJobStatus.queued,
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        logger.info(
            "Created LegalInsightJob %s for document %s (user %s)",
            job.id,
            document_id,
            user.id,
        )
        return job

    def create_job_from_upload(
        self,
        db: Session,
        user: User,
        upload_s3_bucket: str,
        upload_s3_key: str,
    ) -> LegalInsightJob:
        """
        Create a LegalInsightJob for a directly-uploaded PDF (no linked Document).
        The PDF has already been written to S3 at *upload_s3_bucket*/*upload_s3_key*.
        """
        model_id: str = (
            getattr(settings, "LEGAL_INSIGHT_MODEL_ID", "") or settings.BEDROCK_MODEL_ID
        ).strip()
        prompt_version: str = getattr(settings, "LEGAL_INSIGHT_PROMPT_VERSION", "v1")

        job = LegalInsightJob(
            user_id=str(user.id),
            document_id=None,
            upload_s3_bucket=upload_s3_bucket,
            upload_s3_key=upload_s3_key,
            model_id=model_id,
            prompt_version=prompt_version,
            status=LegalInsightJobStatus.queued,
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        logger.info(
            "Created upload LegalInsightJob %s (s3://%s/%s, user %s)",
            job.id,
            upload_s3_bucket,
            upload_s3_key,
            user.id,
        )
        return job

    # ------------------------------------------------------------------
    # Cache check
    # ------------------------------------------------------------------

    def check_cache(
        self,
        db: Session,
        pdf_sha256: str,
        model_id: str,
        prompt_version: str,
    ) -> Optional[LegalInsightJob]:
        """
        Return a completed job whose (pdf_sha256, model_id, prompt_version) tuple
        matches, if one exists.  Returns None otherwise.
        """
        cached = (
            db.query(LegalInsightJob)
            .filter(
                LegalInsightJob.pdf_sha256 == pdf_sha256,
                LegalInsightJob.model_id == model_id,
                LegalInsightJob.prompt_version == prompt_version,
                LegalInsightJob.status == LegalInsightJobStatus.completed,
            )
            .first()
        )
        return cached

    # ------------------------------------------------------------------
    # Main pipeline
    # ------------------------------------------------------------------

    def run_job(self, db: Session, job_id: str) -> None:
        """
        Execute the full extraction → summarization → validation pipeline for
        the job identified by *job_id*.

        This method is designed to be called as a FastAPI BackgroundTask.
        All exceptions are caught and recorded on the job record.
        """
        # Load job
        job = db.query(LegalInsightJob).filter(LegalInsightJob.id == job_id).first()
        if job is None:
            logger.error("run_job: job %s not found in DB", job_id)
            return

        try:
            self._pipeline(db, job)
        except Exception as exc:
            logger.exception("run_job: pipeline failed for job %s: %s", job_id, exc)
            try:
                self._set_status(
                    db,
                    job,
                    LegalInsightJobStatus.failed,
                    error=str(exc),
                )
            except Exception:
                pass  # DB write failed — nothing more we can do
        finally:
            # Always delete the temporary uploaded PDF once the job is terminal.
            # This runs whether the pipeline succeeded, failed, or raised unexpectedly.
            self._delete_upload_from_s3(job)

    def _pipeline(self, db: Session, job: LegalInsightJob) -> None:
        """Internal pipeline implementation (raises on error)."""

        # ----------------------------------------------------------------
        # Phase 1 — extracting (download + hash)
        # ----------------------------------------------------------------
        self._set_status(db, job, LegalInsightJobStatus.extracting, progress=5)

        if job.document_id is not None:
            doc = db.query(Document).filter(Document.id == job.document_id).first()
            if doc is None:
                raise ValueError(f"Document {job.document_id} not found")
            s3_bucket = doc.s3_bucket
            s3_key = doc.s3_key
        else:
            # Direct-upload job: use the S3 location stored on the job itself.
            if not job.upload_s3_key or not job.upload_s3_bucket:
                raise ValueError("Upload job is missing S3 location fields")
            s3_bucket = job.upload_s3_bucket
            s3_key = job.upload_s3_key

        pdf_bytes = legal_insight_extractor.download_pdf_bytes(s3_bucket, s3_key)
        sha256 = legal_insight_extractor.compute_sha256(pdf_bytes)

        job.pdf_sha256 = sha256
        db.commit()

        # Check cache — if another completed job has the same PDF+model+prompt,
        # copy its result rather than re-running the LLM.
        cached = self.check_cache(db, sha256, job.model_id, job.prompt_version)
        if cached is not None and str(cached.id) != str(job.id):
            logger.info(
                "Cache hit: reusing result from job %s for job %s",
                cached.id,
                job.id,
            )
            cached_result = (
                db.query(LegalInsightResult)
                .filter(LegalInsightResult.job_id == str(cached.id))
                .first()
            )
            if cached_result is not None:
                db.add(
                    LegalInsightResult(
                        job_id=str(job.id),
                        result_json=cached_result.result_json,
                    )
                )
            self._set_status(
                db, job, LegalInsightJobStatus.completed, progress=100
            )
            return

        # ----------------------------------------------------------------
        # Phase 1b — chunk extraction
        # ----------------------------------------------------------------
        self._set_status(db, job, LegalInsightJobStatus.extracting, progress=15)

        enable_ocr: bool = bool(
            getattr(settings, "LEGAL_INSIGHT_ENABLE_OCR_FALLBACK", True)
        )
        max_chars: int = int(
            getattr(settings, "LEGAL_INSIGHT_MAX_CHARS_PER_CHUNK", 3000)
        )

        chunks, ocr_used = legal_insight_extractor.extract_text_with_ocr_fallback(
            pdf_bytes, enable_ocr, max_chars
        )

        if not chunks:
            raise ValueError("No text could be extracted from the PDF")

        # ----------------------------------------------------------------
        # Phase 2 — OCR (status update only)
        # ----------------------------------------------------------------
        if ocr_used:
            self._set_status(db, job, LegalInsightJobStatus.ocr, progress=30)

        # ----------------------------------------------------------------
        # Phase 3 — persist chunks + begin summarizing
        # ----------------------------------------------------------------
        self._set_status(db, job, LegalInsightJobStatus.summarizing, progress=40)

        for chunk in chunks:
            db.add(
                LegalInsightChunk(
                    job_id=str(job.id),
                    chunk_id=chunk["chunk_id"],
                    page_number=chunk["page_number"],
                    bbox=chunk.get("bbox"),
                    text=chunk["text"],
                    char_start=chunk.get("char_start"),
                    char_end=chunk.get("char_end"),
                )
            )
        db.commit()
        logger.info("Persisted %d chunks for job %s", len(chunks), job.id)

        # ----------------------------------------------------------------
        # Phase 4 — LLM summarization
        # ----------------------------------------------------------------
        def _progress_cb(pct: int) -> None:
            mapped = 40 + int(pct * 0.4)  # 40-80 % range
            self._set_status(
                db, job, LegalInsightJobStatus.summarizing, progress=mapped
            )

        summary = legal_insight_llm_service.summarize(chunks, on_progress=_progress_cb)

        # ----------------------------------------------------------------
        # Phase 5 — validation + result persistence
        # ----------------------------------------------------------------
        self._set_status(db, job, LegalInsightJobStatus.validating, progress=85)

        citation_map: dict[str, Any] = {
            c["chunk_id"]: {
                "page_number": c["page_number"],
                "bbox": c.get("bbox"),
            }
            for c in chunks
        }

        final_result: dict[str, Any] = {
            "summary": summary,
            "citation_map": citation_map,
        }

        db.add(
            LegalInsightResult(
                job_id=str(job.id),
                result_json=final_result,
            )
        )

        self._set_status(db, job, LegalInsightJobStatus.completed, progress=100)
        logger.info("Job %s completed successfully", job.id)


# Singleton
legal_insight_job_service = LegalInsightJobService()
