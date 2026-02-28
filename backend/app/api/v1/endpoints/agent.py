"""
api/v1/endpoints/agent.py

FastAPI endpoint for the LawMate agent chat.

Two endpoints:
  POST /api/v1/agent/chat/stream  — SSE streaming (primary, for chat UI)
  POST /api/v1/agent/chat         — non-streaming (for testing / background)

Request body:
    {
        "message":         str,           # lawyer's message
        "page":            str,           # "global" | "case_detail" | "hearing_day" | "cause_list"
        "case_id":         str | null,    # from URL param on case pages
        "conversation_id": str | null,    # frontend session UUID
        "history":         list[dict]     # previous messages in this session
    }

SSE stream events (from agent.py):
    data: {"type": "tool_start",  "tool": "search_judgments", "input": {...}}
    data: {"type": "tool_end",    "tool": "search_judgments", "success": true, "summary": "5 judgments found"}
    data: {"type": "text_delta",  "text": "Based on the Kerala HC..."}
    data: {"type": "done",        "full_text": "...complete response..."}
    data: {"type": "error",       "message": "..."}
"""

from __future__ import annotations

import json
import logging
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agent.agent import run_agent, stream_agent_response
from app.agent.context import build_agent_context
from app.api.v1.deps import get_current_user
from app.db.database import get_db
from app.db.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])


# ============================================================================
# Request / Response schemas
# ============================================================================

class ChatMessage(BaseModel):
    role:    str   # "user" | "assistant"
    content: str


class AgentChatRequest(BaseModel):
    message:         str
    page:            str              = Field(default="global")
    case_id:         Optional[str]   = None
    conversation_id: Optional[str]   = None
    history:         list[ChatMessage] = Field(default_factory=list)


class AgentChatResponse(BaseModel):
    response:   str
    tools_used: list[str]
    success:    bool


# ============================================================================
# SSE Streaming endpoint — primary path for chat UI
# ============================================================================

@router.post("/chat/stream")
async def agent_chat_stream(
    request:      AgentChatRequest,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """
    Streams agent response via Server-Sent Events.

    The frontend connects with:
        const es = new EventSource('/api/v1/agent/chat/stream')
        — or —
        fetch('/api/v1/agent/chat/stream', { method: 'POST', body: ... })
        then read the stream with a ReadableStream reader.

    Each SSE event is a JSON-encoded dict.
    Stream ends with a "done" event.
    """
    try:
        context = await build_agent_context(
            page=request.page,
            lawyer_id=str(current_user.id),
            db=db,
            case_id=request.case_id,
            conversation_id=request.conversation_id,
        )
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    history = [m.model_dump() for m in request.history]

    return StreamingResponse(
        _sse_generator(
            message=request.message,
            history=history,
            context=context,
            db=db,
        ),
        media_type="text/event-stream",
        headers={
            # Prevent buffering — critical for SSE to work correctly
            "Cache-Control":           "no-cache",
            "X-Accel-Buffering":       "no",   # nginx
            "Transfer-Encoding":       "chunked",
            "Connection":              "keep-alive",
        },
    )


async def _sse_generator(
    message: str,
    history: list[dict],
    context,
    db:      Session,
) -> AsyncGenerator[str, None]:
    """
    Wraps stream_agent_response() into SSE format.
    Each event: "data: {json}\n\n"
    """
    try:
        async for event in stream_agent_response(
            message=message,
            history=history,
            context=context,
            db=db,
        ):
            yield f"data: {json.dumps(event)}\n\n"

    except Exception as e:
        logger.exception("SSE generator error: %s", e)
        error_event = {"type": "error", "message": str(e)}
        yield f"data: {json.dumps(error_event)}\n\n"

    finally:
        # Always send a done event so frontend knows stream ended
        yield "data: [DONE]\n\n"


# ============================================================================
# Non-streaming endpoint — for testing and background tasks
# ============================================================================

@router.post("/chat", response_model=AgentChatResponse)
async def agent_chat(
    request:      AgentChatRequest,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """
    Non-streaming agent chat. Returns full response when complete.
    Use for testing or server-side agent invocations.
    """
    try:
        context = await build_agent_context(
            page=request.page,
            lawyer_id=str(current_user.id),
            db=db,
            case_id=request.case_id,
            conversation_id=request.conversation_id,
        )
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    history = [m.model_dump() for m in request.history]

    result = await run_agent(
        message=request.message,
        history=history,
        context=context,
        db=db,
    )

    return AgentChatResponse(**result)
