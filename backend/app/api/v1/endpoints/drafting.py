"""
api/v1/endpoints/drafting.py

REST + SSE endpoints for the Drafting AI feature.

All routes are prefixed with /drafting (registered in api.py).

Endpoints
---------
GET    /drafting/workspaces                             list workspaces
POST   /drafting/workspaces                             create workspace
PATCH  /drafting/workspaces/{id}                        update label / caseContext
DELETE /drafting/workspaces/{id}                        delete workspace + S3 cascade

POST   /drafting/workspaces/{id}/documents              upload document (multipart)
DELETE /drafting/workspaces/{id}/documents/{docId}      delete document

POST   /drafting/workspaces/{id}/extract-context        re-run context extraction

POST   /drafting/workspaces/{id}/chat/stream            SSE streaming chat

POST   /drafting/workspaces/{id}/drafts                 generate draft
GET    /drafting/workspaces/{id}/drafts                 list drafts
GET    /drafting/workspaces/{id}/drafts/{draftId}       get draft
PATCH  /drafting/workspaces/{id}/drafts/{draftId}       save / update draft (bumps version)
DELETE /drafting/workspaces/{id}/drafts/{draftId}       delete draft

SSE event format (same as prep_session):
    data: {"type": "text_delta",    "text": "…"}
    data: {"type": "thinking_delta","text": "…"}
    data: {"type": "cited_docs",    "doc_ids": ["…"]}
    data: {"type": "warning",       "message": "…"}
    data: {"type": "done",          "full_text": "…"}
    data: {"type": "error",         "message": "…"}
"""
from __future__ import annotations

import logging
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.db.database import get_db
from app.db.models import User

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Drafting AI"])


# ============================================================================
# Pydantic request / response schemas
# ============================================================================

class CreateWorkspaceRequest(BaseModel):
    label: str = Field(default="Untitled", max_length=255)


class UpdateWorkspaceRequest(BaseModel):
    label:       Optional[str]  = Field(default=None, max_length=255)
    caseContext: Optional[dict] = None


class ChatRequest(BaseModel):
    message:              str
    history:              list[dict] = Field(default_factory=list)
    skip_shift_detection: bool       = False


class GenerateDraftRequest(BaseModel):
    docType: str
    brief:   str = ""


class SaveDraftRequest(BaseModel):
    content: str
    title:   Optional[str] = None


# ============================================================================
# Helpers
# ============================================================================

def _svc():
    """Lazy import to avoid circular imports at module load time."""
    from app.services import drafting_service
    return drafting_service


def _not_found(exc: LookupError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


def _bad_request(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


def _conflict(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=409, detail=str(exc))


# ============================================================================
# Workspace endpoints
# ============================================================================

@router.get("/workspaces")
def list_workspaces(
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """List all workspaces for the current user."""
    svc = _svc()
    workspaces = svc.list_workspaces(db, user_id=str(current_user.id))
    return [svc._ws_to_dict(ws) for ws in workspaces]


@router.post("/workspaces", status_code=201)
def create_workspace(
    body:         CreateWorkspaceRequest,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """Create a new drafting workspace (max 5 per user)."""
    svc = _svc()
    try:
        ws = svc.create_workspace(db, user_id=str(current_user.id), label=body.label)
    except ValueError as exc:
        raise _conflict(exc)
    return svc._ws_to_dict(ws)


@router.patch("/workspaces/{workspace_id}")
def update_workspace(
    workspace_id: str,
    body:         UpdateWorkspaceRequest,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """Update workspace label and/or case context."""
    svc = _svc()
    try:
        ws = svc.update_workspace(
            db,
            workspace_id=workspace_id,
            user_id=str(current_user.id),
            label=body.label,
            case_context=body.caseContext,
        )
    except LookupError as exc:
        raise _not_found(exc)
    return svc._ws_to_dict(ws)


@router.delete("/workspaces/{workspace_id}", status_code=204)
def delete_workspace(
    workspace_id: str,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """Delete a workspace, all its documents (S3 + DB) and drafts."""
    svc = _svc()
    try:
        svc.delete_workspace(db, workspace_id=workspace_id, user_id=str(current_user.id))
    except LookupError as exc:
        raise _not_found(exc)


# ============================================================================
# Document endpoints
# ============================================================================

@router.post("/workspaces/{workspace_id}/documents", status_code=201)
async def upload_document(
    workspace_id: str,
    file:         UploadFile     = File(...),
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """Upload a PDF or DOCX document to a workspace."""
    svc = _svc()

    # Validate content type
    allowed_types = {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    content_type = file.content_type or "application/octet-stream"
    if content_type not in allowed_types and not file.filename.lower().endswith((".pdf", ".docx")):
        raise HTTPException(
            status_code=415,
            detail="Only PDF and DOCX files are accepted.",
        )

    file_bytes = await file.read()

    try:
        doc = await svc.upload_document(
            db,
            workspace_id=workspace_id,
            user_id=str(current_user.id),
            file_bytes=file_bytes,
            filename=file.filename or "document.pdf",
            content_type=content_type,
        )
    except LookupError as exc:
        raise _not_found(exc)
    except ValueError as exc:
        # Could be 413 (file too large) or 400 (doc cap)
        msg = str(exc)
        status = 413 if "exceeds" in msg.lower() else 400
        raise HTTPException(status_code=status, detail=msg)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return doc


@router.get("/workspaces/{workspace_id}/documents/{doc_id}/url")
def get_document_url(
    workspace_id: str,
    doc_id:       str,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """Return a short-lived presigned S3 URL to view/download a document."""
    svc = _svc()
    try:
        url = svc.get_document_presigned_url(
            db,
            workspace_id=workspace_id,
            doc_id=doc_id,
            user_id=str(current_user.id),
        )
    except LookupError as exc:
        raise _not_found(exc)
    return {"url": url}


@router.delete("/workspaces/{workspace_id}/documents/{doc_id}", status_code=204)
async def delete_document(
    workspace_id: str,
    doc_id:       str,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """Delete a document from a workspace."""
    svc = _svc()
    try:
        await svc.delete_document(
            db,
            workspace_id=workspace_id,
            doc_id=doc_id,
            user_id=str(current_user.id),
        )
    except LookupError as exc:
        raise _not_found(exc)


@router.delete("/workspaces/{workspace_id}/documents", status_code=204)
async def clear_all_documents(
    workspace_id: str,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """
    Delete ALL documents from a workspace, reset case context and conversation
    history.  Used when the user confirms they are starting a fresh case.
    """
    svc = _svc()
    try:
        await svc.clear_workspace_documents(
            db,
            workspace_id=workspace_id,
            user_id=str(current_user.id),
        )
    except LookupError as exc:
        raise _not_found(exc)


# ============================================================================
# Context extraction
# ============================================================================

@router.post("/workspaces/{workspace_id}/extract-context")
async def extract_context(
    workspace_id: str,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """(Re-)run structured context extraction over all workspace documents."""
    svc = _svc()
    try:
        ctx = await svc.extract_case_context(
            db,
            workspace_id=workspace_id,
            user_id=str(current_user.id),
        )
    except LookupError as exc:
        raise _not_found(exc)
    return {"caseContext": ctx}


# ============================================================================
# SSE streaming chat
# ============================================================================

@router.post("/workspaces/{workspace_id}/chat/stream")
async def chat_stream(
    workspace_id: str,
    body:         ChatRequest,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """Stream a chat response via Server-Sent Events."""
    svc = _svc()

    try:
        # Validate workspace ownership before streaming
        svc.get_workspace(db, workspace_id, str(current_user.id))
    except LookupError as exc:
        raise _not_found(exc)

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            async for chunk in svc.stream_chat(
                db,
                workspace_id=workspace_id,
                user_id=str(current_user.id),
                message=body.message,
                history=body.history,
                skip_shift_detection=body.skip_shift_detection,
            ):
                yield chunk
        except Exception as exc:
            import json
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":        "keep-alive",
        },
    )


# ============================================================================
# Draft endpoints
# ============================================================================

@router.post("/workspaces/{workspace_id}/drafts", status_code=201)
async def generate_draft(
    workspace_id: str,
    body:         GenerateDraftRequest,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """Generate a new draft document using AI with extended thinking."""
    svc = _svc()
    try:
        draft = await svc.generate_draft(
            db,
            workspace_id=workspace_id,
            user_id=str(current_user.id),
            doc_type=body.docType,
            brief=body.brief,
        )
    except LookupError as exc:
        raise _not_found(exc)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return draft


@router.get("/workspaces/{workspace_id}/drafts")
def list_drafts(
    workspace_id: str,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """List all drafts in a workspace."""
    svc = _svc()
    try:
        return svc.list_drafts(db, workspace_id=workspace_id, user_id=str(current_user.id))
    except LookupError as exc:
        raise _not_found(exc)


@router.get("/workspaces/{workspace_id}/drafts/{draft_id}")
def get_draft(
    workspace_id: str,
    draft_id:     str,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """Get a single draft."""
    svc = _svc()
    try:
        return svc.get_draft(db, workspace_id=workspace_id, draft_id=draft_id,
                             user_id=str(current_user.id))
    except LookupError as exc:
        raise _not_found(exc)


@router.patch("/workspaces/{workspace_id}/drafts/{draft_id}")
def save_draft(
    workspace_id: str,
    draft_id:     str,
    body:         SaveDraftRequest,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """Save (auto-save) an edited draft. Increments the version counter."""
    svc = _svc()
    try:
        return svc.save_draft(
            db,
            workspace_id=workspace_id,
            draft_id=draft_id,
            user_id=str(current_user.id),
            content=body.content,
            title=body.title,
        )
    except LookupError as exc:
        raise _not_found(exc)


@router.delete("/workspaces/{workspace_id}/drafts/{draft_id}", status_code=204)
def delete_draft(
    workspace_id: str,
    draft_id:     str,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """Delete a draft."""
    svc = _svc()
    try:
        svc.delete_draft(db, workspace_id=workspace_id, draft_id=draft_id,
                         user_id=str(current_user.id))
    except LookupError as exc:
        raise _not_found(exc)
