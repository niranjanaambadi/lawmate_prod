"""
Translation endpoint — English ↔ Malayalam legal text translation.

Routes
------
POST /api/v1/translate/text
    Translate a plain-text payload.

POST /api/v1/translate/document
    Translate an uploaded file (PDF / DOCX / TXT).

POST /api/v1/translate/export
    Export translated text as PDF or DOCX file download.
"""
from __future__ import annotations

import io
import logging
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.v1.deps import get_current_user
from app.db.models import User
from app.services.translation.llm_translate_service import llm_translate_service
from app.services.translation.document_translate_service import document_translate_service

logger = logging.getLogger(__name__)

router = APIRouter()

Direction = Literal["en_to_ml", "ml_to_en"]

_ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "text/plain",
}

_MAX_TEXT_CHARS = 15_000   # ~3 000 words — comfortable single-request ceiling
_MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB


# ── Request / response schemas ─────────────────────────────────────────────


class TranslateTextRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=_MAX_TEXT_CHARS)
    direction: Direction = "en_to_ml"


class TranslateTextResponse(BaseModel):
    translated: str
    direction: str
    glossary_hits: int
    warnings: List[str]
    char_count: int


class TranslateDocumentResponse(BaseModel):
    translated: str
    direction: str
    filename: str
    mime_type: str
    chunks: int
    glossary_hits: int
    warnings: List[str]
    char_count: int


# ── Endpoints ──────────────────────────────────────────────────────────────


@router.post(
    "/text",
    response_model=TranslateTextResponse,
    summary="Translate legal text",
    description=(
        "Translate a plain-text legal document between English and Malayalam. "
        "Protected entities (case numbers, acts, dates, Latin phrases) are preserved verbatim."
    ),
)
def translate_text(
    payload: TranslateTextRequest,
    current_user: User = Depends(get_current_user),
) -> TranslateTextResponse:
    """Translate a plain-text payload."""
    try:
        result = llm_translate_service.translate_text(payload.text, payload.direction)
    except RuntimeError as exc:
        logger.error("translate/text failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Translation service error: {exc}",
        )

    return TranslateTextResponse(
        translated=result["translated"],
        direction=payload.direction,
        glossary_hits=result["glossary_hits"],
        warnings=result["warnings"],
        char_count=len(payload.text),
    )


@router.post(
    "/document",
    response_model=TranslateDocumentResponse,
    summary="Translate uploaded legal document",
    description=(
        "Upload a PDF, DOCX, or TXT file to translate its full text. "
        "Large documents are split into chunks automatically."
    ),
)
async def translate_document(
    file: UploadFile = File(...),
    direction: Direction = Form("en_to_ml"),
    current_user: User = Depends(get_current_user),
) -> TranslateDocumentResponse:
    """Translate an uploaded document."""

    # Validate MIME type
    content_type = (file.content_type or "").split(";")[0].strip()
    if content_type not in _ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Unsupported file type '{content_type}'. "
                "Allowed: PDF, DOCX, TXT."
            ),
        )

    # Read and validate size
    data = await file.read()
    if len(data) > _MAX_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large ({len(data) // 1024} KB). Maximum is 10 MB.",
        )

    try:
        result = document_translate_service.translate_bytes(data, content_type, direction)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except RuntimeError as exc:
        logger.error("translate/document failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Translation service error: {exc}",
        )

    return TranslateDocumentResponse(
        translated=result["translated"],
        direction=direction,
        filename=file.filename or "document",
        mime_type=content_type,
        chunks=result["chunks"],
        glossary_hits=result["glossary_hits"],
        warnings=result["warnings"],
        char_count=result.get("char_count", 0),
    )


# ── Export ─────────────────────────────────────────────────────────────────

ExportFormat = Literal["pdf", "docx"]


class ExportRequest(BaseModel):
    text: str = Field(..., min_length=1)
    title: str = Field(default="Translation", max_length=200)
    direction: Direction = "en_to_ml"
    format: ExportFormat = "pdf"


def _build_pdf(text: str, title: str, direction: str) -> bytes:
    """Generate a PDF using reportlab."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    from reportlab.lib.enums import TA_LEFT
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import os

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2.5 * cm,
        rightMargin=2.5 * cm,
        topMargin=2.5 * cm,
        bottomMargin=2.5 * cm,
    )

    styles = getSampleStyleSheet()

    # Try to register a Unicode font for Malayalam; fall back gracefully
    font_name = "Helvetica"
    font_candidates = [
        "/System/Library/Fonts/Supplemental/NotoSansMalayalam.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansMalayalam-Regular.ttf",
        "/usr/share/fonts/NotoSansMalayalam-Regular.ttf",
    ]
    for candidate in font_candidates:
        if os.path.exists(candidate):
            try:
                pdfmetrics.registerFont(TTFont("NotoMal", candidate))
                font_name = "NotoMal"
            except Exception:
                pass
            break

    title_style = ParagraphStyle(
        "TransTitle",
        parent=styles["Heading1"],
        fontName=font_name,
        fontSize=14,
        spaceAfter=12,
    )
    body_style = ParagraphStyle(
        "TransBody",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=11,
        leading=18,
        spaceAfter=8,
    )
    meta_style = ParagraphStyle(
        "TransMeta",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=9,
        textColor=(0.5, 0.5, 0.5),
        spaceAfter=20,
    )

    dir_label = "English → Malayalam" if direction == "en_to_ml" else "Malayalam → English"
    story = [
        Paragraph(title, title_style),
        Paragraph(f"Legal Translation  ·  {dir_label}", meta_style),
    ]

    for para in text.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        # Escape XML special chars for reportlab Paragraph
        safe = para.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        story.append(Paragraph(safe, body_style))
        story.append(Spacer(1, 4))

    doc.build(story)
    return buf.getvalue()


def _build_docx(text: str, title: str, direction: str) -> bytes:
    """Generate a DOCX using python-docx."""
    import docx  # python-docx

    document = docx.Document()

    # Title
    document.add_heading(title, level=1)

    # Metadata paragraph
    dir_label = "English → Malayalam" if direction == "en_to_ml" else "Malayalam → English"
    meta = document.add_paragraph()
    run = meta.add_run(f"Legal Translation  ·  {dir_label}")
    run.italic = True
    run.font.color.rgb = docx.shared.RGBColor(0x88, 0x88, 0x88)

    document.add_paragraph()  # spacer

    # Body paragraphs
    for para in text.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        p = document.add_paragraph(para)
        p.style = document.styles["Normal"]

    buf = io.BytesIO()
    document.save(buf)
    return buf.getvalue()


@router.post(
    "/export",
    summary="Export translated text as PDF or DOCX",
    response_class=StreamingResponse,
)
def export_translation(
    payload: ExportRequest,
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """
    Generate a formatted PDF or DOCX from translated text and return it
    as a file download.
    """
    try:
        if payload.format == "pdf":
            file_bytes = _build_pdf(payload.text, payload.title, payload.direction)
            media_type = "application/pdf"
            ext = "pdf"
        else:
            file_bytes = _build_docx(payload.text, payload.title, payload.direction)
            media_type = (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
            ext = "docx"
    except Exception as exc:
        logger.error("translate/export failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Export failed: {exc}",
        )

    safe_title = "".join(c if c.isalnum() or c in "-_ " else "_" for c in payload.title)
    filename = f"{safe_title}_{payload.direction}.{ext}"

    return StreamingResponse(
        io.BytesIO(file_bytes),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
