"""
AI Insights endpoints – document extraction and document Q&A via Amazon Bedrock PDF support.
"""
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Depends, status
from pydantic import BaseModel, Field
from typing import List, Optional

from app.api.v1.deps import get_current_user
from app.db.models import User
from app.services.ai_service import ai_service

router = APIRouter()


class DocumentChatRequest(BaseModel):
    extractedText: str = Field(..., description="Current (possibly edited) extracted document text")
    question: str = Field(..., description="User question about the document")
    conversationHistory: Optional[List[dict]] = Field(default_factory=list, description="Prior turns [{role, content}]")


@router.post("/extract-document")
async def extract_document(
    file: UploadFile = File(...),
    use_visual_mode: bool = Form(True),
    current_user: User = Depends(get_current_user),
):
    """
    Extract text from a PDF using Amazon Bedrock's native PDF support (Converse API).
    See: https://platform.claude.com/docs/en/build-with-claude/pdf-support

    use_visual_mode (form, default True):
    - True: Full visual understanding (charts, images, layout). More tokens, better for scanned/complex PDFs.
    - False: Text extraction only. Faster and cheaper (~1k vs ~7k tokens per 3 pages).
    Returns: { "extractedText", "pageCount", "processingMode": "text_only"|"full_visual" }.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are supported",
        )

    contents = await file.read()
    if len(contents) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is empty",
        )

    try:
        result = ai_service.extract_document_bedrock_pdf(
            contents,
            filename=file.filename or "document.pdf",
            use_visual_mode=use_visual_mode,
        )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Extraction failed: {str(e)}",
        )


@router.post("/chat")
async def chat_about_document(
    body: DocumentChatRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Conversational Q&A about the current document. Uses the provided extracted text as context.
    Returns: { "response": "..." }.
    """
    try:
        response_text = ai_service.chat_about_document(
            extracted_text=body.extractedText,
            question=body.question,
            conversation_history=body.conversationHistory,
        )
        return {"response": response_text}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat failed: {str(e)}",
        )
