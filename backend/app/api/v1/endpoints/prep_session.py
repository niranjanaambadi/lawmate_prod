"""
api/v1/endpoints/prep_session.py

REST + SSE endpoints for Case Prep AI.

Endpoints
---------
POST   /prep-sessions/                          → create session
GET    /prep-sessions/                          → list (optionally filter by case_id)
GET    /prep-sessions/{session_id}              → get session
PATCH  /prep-sessions/{session_id}/mode        → switch mode
PATCH  /prep-sessions/{session_id}/documents   → update document scope
DELETE /prep-sessions/{session_id}             → delete session
POST   /prep-sessions/{session_id}/chat/stream → SSE streaming chat
POST   /prep-sessions/{session_id}/export      → export to HearingBrief

SSE events (stream endpoint):
    data: {"type": "text_delta",  "text": "…"}
    data: {"type": "done",        "session_id": "…", "full_text": "…"}
    data: {"type": "error",       "message": "…"}
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.db.database import get_db
from app.db.models import HearingBrief, PrepSession, User
from app.services.prep_session_service import prep_session_service
from app.agent.prep_prompts import PREP_MODE_LABELS

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Case Prep AI"])


# ============================================================================
# Pydantic schemas
# ============================================================================

class CreateSessionRequest(BaseModel):
    case_id:      str
    mode:         str              = Field(default="argument_builder")
    document_ids: list[str]        = Field(default_factory=list)


class SwitchModeRequest(BaseModel):
    mode: str


class UpdateDocumentsRequest(BaseModel):
    document_ids: list[str]


class ChatRequest(BaseModel):
    message: str


class ExportRequest(BaseModel):
    hearing_date: Optional[datetime] = None
    focus_areas:  Optional[list[str]] = None


class SessionResponse(BaseModel):
    id:           str
    case_id:      str
    user_id:      str
    mode:         str
    mode_label:   str
    document_ids: list[str]
    messages:     list[dict]
    created_at:   datetime
    updated_at:   datetime

    model_config = {"from_attributes": True}


class HearingBriefResponse(BaseModel):
    id:              str
    case_id:         str
    hearing_date:    datetime
    content:         str
    focus_areas:     list[str]
    bundle_snapshot: Optional[dict]
    created_at:      datetime

    model_config = {"from_attributes": True}


# ============================================================================
# Helpers
# ============================================================================

def _session_response(session: PrepSession) -> SessionResponse:
    return SessionResponse(
        id=str(session.id),
        case_id=str(session.case_id),
        user_id=str(session.user_id),
        mode=session.mode,
        mode_label=PREP_MODE_LABELS.get(session.mode, session.mode),
        document_ids=[str(d) for d in (session.document_ids or [])],
        messages=session.messages or [],
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


def _brief_response(brief: HearingBrief) -> HearingBriefResponse:
    return HearingBriefResponse(
        id=str(brief.id),
        case_id=str(brief.case_id),
        hearing_date=brief.hearing_date,
        content=brief.content,
        focus_areas=brief.focus_areas or [],
        bundle_snapshot=brief.bundle_snapshot,
        created_at=brief.created_at,
    )


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/", response_model=SessionResponse, status_code=201)
def create_session(
    body:         CreateSessionRequest,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """Create a new Case Prep AI session."""
    session = prep_session_service.create_session(
        db=db,
        user=current_user,
        case_id=body.case_id,
        mode=body.mode,
        document_ids=body.document_ids,
    )
    return _session_response(session)


@router.get("/", response_model=list[SessionResponse])
def list_sessions(
    case_id:      Optional[str] = Query(default=None),
    current_user: User          = Depends(get_current_user),
    db:           Session       = Depends(get_db),
):
    """List prep sessions for the current user, optionally filtered by case."""
    sessions = prep_session_service.list_sessions(
        db=db,
        user_id=str(current_user.id),
        case_id=case_id,
    )
    return [_session_response(s) for s in sessions]


@router.get("/{session_id}", response_model=SessionResponse)
def get_session(
    session_id:   str,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """Fetch a single prep session."""
    session = prep_session_service.get_session(
        db=db,
        session_id=session_id,
        user_id=str(current_user.id),
    )
    return _session_response(session)


@router.patch("/{session_id}/mode", response_model=SessionResponse)
def switch_mode(
    session_id:   str,
    body:         SwitchModeRequest,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """Switch the active preparation mode for a session."""
    session = prep_session_service.switch_mode(
        db=db,
        session_id=session_id,
        user_id=str(current_user.id),
        new_mode=body.mode,
    )
    return _session_response(session)


@router.patch("/{session_id}/documents", response_model=SessionResponse)
def update_documents(
    session_id:   str,
    body:         UpdateDocumentsRequest,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """Update the set of documents in scope for a session."""
    session = prep_session_service.update_documents(
        db=db,
        session_id=session_id,
        user_id=str(current_user.id),
        document_ids=body.document_ids,
    )
    return _session_response(session)


@router.delete("/{session_id}", status_code=204)
def delete_session(
    session_id:   str,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """Delete a prep session and all its messages."""
    prep_session_service.delete_session(
        db=db,
        session_id=session_id,
        user_id=str(current_user.id),
    )


@router.post("/{session_id}/chat/stream")
async def stream_chat(
    session_id:   str,
    body:         ChatRequest,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """
    SSE streaming chat for a prep session.

    The response is a Server-Sent Events stream.  Each event is a JSON object:
        {"type": "text_delta",  "text": "…"}
        {"type": "done",        "session_id": "…", "full_text": "…"}
        {"type": "error",       "message": "…"}
    """
    async def event_generator() -> AsyncGenerator[str, None]:
        async for chunk in prep_session_service.stream_chat(
            db=db,
            session_id=session_id,
            user_id=str(current_user.id),
            user_message=body.message,
        ):
            yield chunk

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/{session_id}/export", response_model=HearingBriefResponse, status_code=201)
def export_to_brief(
    session_id:   str,
    body:         ExportRequest,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """
    Export the session to a HearingBrief record.

    Claude summarises the session into a structured one-page brief.
    The brief is persisted to the hearing_briefs table and returned.
    """
    brief = prep_session_service.export_to_hearing_brief(
        db=db,
        session_id=session_id,
        user_id=str(current_user.id),
        hearing_date=body.hearing_date,
        focus_areas=body.focus_areas,
    )
    return _brief_response(brief)
