"""
Document Comparison API Endpoint — LawMate
==========================================
POST /api/v1/doc-compare/compare        → run comparison, return JSON result
GET  /api/v1/doc-compare/memo/{id}      → download comparison memo as PDF
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user, get_db
from app.db.models import User
from app.services.document_comparison_service import (
    compare_documents,
    extract_text_from_bytes,
    generate_comparison_memo_pdf,
    get_stored_comparison,
    store_comparison,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_MAX_FILE_MB = 30
_MAX_FILE_BYTES = _MAX_FILE_MB * 1024 * 1024


# ── POST /compare ─────────────────────────────────────────────────────────────

@router.post("/compare")
async def compare(
    file_a: UploadFile = File(..., description="Original document (PDF / DOCX / image / TXT)"),
    file_b: UploadFile = File(..., description="Amended document (PDF / DOCX / image / TXT)"),
    doc_a_name: Optional[str] = Form(None, description="Label for Document A"),
    doc_b_name: Optional[str] = Form(None, description="Label for Document B"),
    language: str = Form("eng", description="OCR language: eng | mal | mal+eng"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Upload two documents and receive a full comparison result as JSON.
    Supported formats: PDF (native text + OCR fallback), DOCX, PNG/JPG/TIFF, TXT.
    """
    bytes_a = await file_a.read()
    bytes_b = await file_b.read()

    if len(bytes_a) > _MAX_FILE_BYTES:
        raise HTTPException(400, f"Document A exceeds the {_MAX_FILE_MB} MB limit.")
    if len(bytes_b) > _MAX_FILE_BYTES:
        raise HTTPException(400, f"Document B exceeds the {_MAX_FILE_MB} MB limit.")

    name_a = doc_a_name or (file_a.filename or "Document A")
    name_b = doc_b_name or (file_b.filename or "Document B")
    ct_a = file_a.content_type or ""
    ct_b = file_b.content_type or ""

    try:
        text_a = extract_text_from_bytes(bytes_a, ct_a, file_a.filename or "", language)
    except Exception as exc:
        logger.exception("Text extraction failed for document A")
        raise HTTPException(422, f"Could not extract text from Document A: {exc}")

    try:
        text_b = extract_text_from_bytes(bytes_b, ct_b, file_b.filename or "", language)
    except Exception as exc:
        logger.exception("Text extraction failed for document B")
        raise HTTPException(422, f"Could not extract text from Document B: {exc}")

    if not text_a.strip():
        raise HTTPException(422, "Document A appears to have no readable text. Try enabling OCR or uploading a text-based PDF.")
    if not text_b.strip():
        raise HTTPException(422, "Document B appears to have no readable text. Try enabling OCR or uploading a text-based PDF.")

    try:
        result = compare_documents(text_a, text_b, name_a, name_b)
    except Exception as exc:
        logger.exception("Comparison failed")
        raise HTTPException(500, f"Comparison failed: {exc}")

    try:
        store_comparison(result, owner_id=str(current_user.id), db=db)
    except Exception as exc:
        # Non-fatal: result is still returned to the client; memo download
        # will fail but the comparison itself succeeds.
        logger.error("Failed to persist comparison result: %s", exc)

    logger.info(
        "Doc compare complete user=%s id=%s additions=%d deletions=%d changes=%d",
        current_user.id,
        result.comparison_id,
        result.total_additions,
        result.total_deletions,
        result.total_changes,
    )

    return result.to_dict()


# ── GET /memo/{comparison_id} ─────────────────────────────────────────────────

@router.get("/memo/{comparison_id}")
async def download_memo(
    comparison_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Download a Comparison Memo PDF for a previously run comparison.
    Results are scoped to the requesting user and expire after 2 hours.
    """
    result = get_stored_comparison(comparison_id, owner_id=str(current_user.id), db=db)
    if result is None:
        raise HTTPException(
            404,
            "Comparison not found. Results expire after 2 hours — "
            "please re-run the comparison and download the memo immediately.",
        )

    try:
        pdf_bytes = generate_comparison_memo_pdf(result)
    except RuntimeError as exc:
        raise HTTPException(500, str(exc))
    except Exception as exc:
        logger.exception("PDF generation failed")
        raise HTTPException(500, f"PDF generation failed: {exc}")

    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in result.doc_a_name[:30])
    filename = f"LawMate_ComparisonMemo_{safe_name}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
