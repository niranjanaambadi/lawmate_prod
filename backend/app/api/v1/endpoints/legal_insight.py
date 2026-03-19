"""
Legal Insight (Judgment Summarizer) API endpoints.

POST   /legal-insight/jobs                    → create job from existing document (queued)
POST   /legal-insight/jobs/upload             → create job from uploaded PDF file (queued)
GET    /legal-insight/jobs/{job_id}           → status + progress
GET    /legal-insight/jobs/{job_id}/result    → summary + citation_map
POST   /legal-insight/jobs/{job_id}/chat      → streaming chat about the judgment (SSE)
"""

from __future__ import annotations

import json
import uuid as uuid_lib
from typing import AsyncGenerator, Literal

import boto3
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.logger import logger
from app.db.database import get_db
from app.db.models import LegalInsightChunk, LegalInsightJob, LegalInsightJobStatus, LegalInsightResult, User
from app.services.legal_insight_job_service import legal_insight_job_service
from app.services.legal_insight_llm_service import legal_insight_llm_service

router = APIRouter()


# ============================================================================
# Request / Response schemas
# ============================================================================


class CreateJobRequest(BaseModel):
    document_id: str


class CreateJobResponse(BaseModel):
    job_id: str
    status: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    progress: int
    error: str | None


# ============================================================================
# Endpoints
# ============================================================================


@router.post(
    "/jobs",
    response_model=CreateJobResponse,
    summary="Create a Legal Insight summarization job",
    description=(
        "Queues a background job to extract and summarize the given judgment PDF. "
        "Returns the job_id that can be polled for status."
    ),
    status_code=202,
)
def create_job(
    request: CreateJobRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CreateJobResponse:
    """Create a new Legal Insight job and start the pipeline in the background."""
    job = legal_insight_job_service.create_job(db, current_user, request.document_id)

    background_tasks.add_task(
        legal_insight_job_service.run_job, db, str(job.id)
    )

    return CreateJobResponse(job_id=str(job.id), status=job.status.value)


@router.post(
    "/jobs/upload",
    response_model=CreateJobResponse,
    summary="Create a Legal Insight job from an uploaded PDF",
    description=(
        "Accept a PDF file directly, upload it to S3, then queue a summarization job. "
        "Use this when the judgment is not already stored as a case document."
    ),
    status_code=202,
)
async def create_upload_job(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CreateJobResponse:
    """Upload a PDF and create a Legal Insight job for it."""
    # ── Validate content type ────────────────────────────────────────────────
    if file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are supported. Please upload a .pdf file.",
        )

    pdf_bytes = await file.read()

    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    if b"%PDF" not in pdf_bytes[:1024]:
        raise HTTPException(
            status_code=400,
            detail="The uploaded file does not appear to be a valid PDF.",
        )

    # ── Upload to S3 ─────────────────────────────────────────────────────────
    s3_bucket = settings.S3_BUCKET_NAME
    s3_key = f"legal-insight-uploads/{current_user.id}/{uuid_lib.uuid4().hex}.pdf"

    try:
        s3_client = boto3.client(
            "s3",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )
        s3_client.put_object(
            Bucket=s3_bucket,
            Key=s3_key,
            Body=pdf_bytes,
            ContentType="application/pdf",
        )
        logger.info(
            "Uploaded PDF for legal insight: s3://%s/%s (%d bytes, user=%s)",
            s3_bucket,
            s3_key,
            len(pdf_bytes),
            current_user.id,
        )
    except Exception as exc:
        logger.exception("S3 upload failed for legal insight upload job: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to upload PDF to storage.") from exc

    # ── Create job ───────────────────────────────────────────────────────────
    job = legal_insight_job_service.create_job_from_upload(
        db=db,
        user=current_user,
        upload_s3_bucket=s3_bucket,
        upload_s3_key=s3_key,
    )

    background_tasks.add_task(legal_insight_job_service.run_job, db, str(job.id))

    return CreateJobResponse(job_id=str(job.id), status=job.status.value)


@router.get(
    "/jobs/{job_id}",
    response_model=JobStatusResponse,
    summary="Get Legal Insight job status",
    description="Poll this endpoint to track the progress of a summarization job.",
)
def get_job_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JobStatusResponse:
    """Return the current status and progress of a Legal Insight job."""
    job: LegalInsightJob | None = (
        db.query(LegalInsightJob)
        .filter(LegalInsightJob.id == job_id)
        .first()
    )

    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if str(job.user_id) != str(current_user.id):
        raise HTTPException(
            status_code=403,
            detail="You do not have permission to view this job",
        )

    return JobStatusResponse(
        job_id=str(job.id),
        status=job.status.value,
        progress=job.progress,
        error=job.error,
    )


@router.get(
    "/jobs/{job_id}/result",
    summary="Get Legal Insight job result",
    description=(
        "Retrieve the full summarization result once the job is completed. "
        "Returns HTTP 409 if the job has not yet finished."
    ),
)
def get_job_result(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Return the summarization result for a completed Legal Insight job."""
    job: LegalInsightJob | None = (
        db.query(LegalInsightJob)
        .filter(LegalInsightJob.id == job_id)
        .first()
    )

    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if str(job.user_id) != str(current_user.id):
        raise HTTPException(
            status_code=403,
            detail="You do not have permission to view this job",
        )

    if job.status != LegalInsightJobStatus.completed:
        raise HTTPException(
            status_code=409,
            detail="Job not yet completed",
        )

    result: LegalInsightResult | None = (
        db.query(LegalInsightResult)
        .filter(LegalInsightResult.job_id == str(job.id))
        .first()
    )

    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Result record not found for completed job",
        )

    return result.result_json


# ============================================================================
# Chat endpoint
# ============================================================================


class ChatMessageSchema(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessageSchema]


@router.post(
    "/jobs/{job_id}/chat",
    summary="Chat with the judgment",
    description=(
        "Stream an AI response to a user question about a completed judgment analysis. "
        "Returns SSE (text/event-stream) with JSON delta chunks and a final [DONE] sentinel."
    ),
)
async def chat_with_judgment(
    job_id: str,
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Stream a chat response grounded in the judgment's extracted text and structured summary."""

    # ── Auth + job validation ─────────────────────────────────────────────────
    job: LegalInsightJob | None = (
        db.query(LegalInsightJob).filter(LegalInsightJob.id == job_id).first()
    )
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if str(job.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="You do not have permission to access this job")
    if job.status != LegalInsightJobStatus.completed:
        raise HTTPException(status_code=409, detail="Job not yet completed — analysis must finish before chatting")

    result: LegalInsightResult | None = (
        db.query(LegalInsightResult).filter(LegalInsightResult.job_id == str(job.id)).first()
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Result record not found for this job")

    # ── Fetch and sample chunks ───────────────────────────────────────────────
    db_chunks = (
        db.query(LegalInsightChunk)
        .filter(LegalInsightChunk.job_id == str(job.id))
        .order_by(LegalInsightChunk.page_number)
        .all()
    )
    chunk_dicts = [
        {"chunk_id": c.chunk_id, "page_number": c.page_number, "text": c.text}
        for c in db_chunks
    ]

    # Convert messages for the service
    messages = [{"role": m.role, "content": m.content} for m in body.messages]

    result_json = result.result_json or {}

    # ── SSE generator ─────────────────────────────────────────────────────────
    async def generate() -> AsyncGenerator[str, None]:
        try:
            for text_delta in legal_insight_llm_service.stream_chat(result_json, chunk_dicts, messages):
                yield f"data: {json.dumps({'text': text_delta})}\n\n"
        except Exception as exc:
            logger.exception("chat_with_judgment stream error: %s", exc)
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering
        },
    )
