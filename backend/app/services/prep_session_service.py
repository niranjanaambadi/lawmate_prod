"""
services/prep_session_service.py

Core service for Case Prep AI:
  - Session lifecycle (create, load, switch mode, delete)
  - Document extraction via BDA (with PyMuPDF fallback)
  - Bedrock streaming with prompt caching
  - Message persistence (JSONB messages column)
  - Export to HearingBrief

Streaming protocol (SSE events):
    data: {"type": "text_delta", "text": "…chunk…"}
    data: {"type": "done", "session_id": "…", "full_text": "…"}
    data: {"type": "error", "message": "…"}
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import AsyncGenerator, Optional

import boto3
from botocore.config import Config
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logger import logger
from app.db.models import (
    Case,
    Document,
    HearingBrief,
    PrepSession,
    User,
)
from app.agent.prep_prompts import (
    format_document_context,
    get_prep_system_prompt,
    PREP_MODES,
)
from app.services.bda_service import bda_service


# ---------------------------------------------------------------------------
# Constants — resolved from settings at import time so they reflect .env changes
# ---------------------------------------------------------------------------

def _prep_model_id() -> str:
    model = (settings.CASE_PREP_MODEL_ID or "anthropic.claude-3-haiku-20240307-v1:0").strip()
    logger.info("Case Prep using model: %s (raw setting: %r)", model, settings.CASE_PREP_MODEL_ID)
    return model

def _max_tokens() -> int:
    return settings.CASE_PREP_MAX_TOKENS

def _temperature() -> float:
    return settings.CASE_PREP_TEMPERATURE


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _bedrock_client():
    """Return a boto3 Bedrock Runtime client."""
    return boto3.client(
        "bedrock-runtime",
        region_name=settings.AWS_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        config=Config(read_timeout=300),
    )


def _sse(event: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(event)}\n\n"


def _get_session(db: Session, session_id: str, user_id: str) -> PrepSession:
    """Load and authorise a PrepSession; raises 404/403 on failure."""
    session = db.query(PrepSession).filter(PrepSession.id == session_id).first()
    if session is None:
        raise HTTPException(status_code=404, detail="Prep session not found")
    if str(session.user_id) != str(user_id):
        raise HTTPException(status_code=403, detail="Access denied")
    return session


def _case_to_dict(case: Case) -> dict:
    """Convert a Case ORM object into the dict shape expected by prep_prompts."""
    return {
        "case_id":          str(case.id),
        "case_number":      case.case_number or "Not yet assigned",
        "case_type":        case.case_type or "N/A",
        "petitioner_name":  case.petitioner_name or "N/A",
        "respondent_name":  case.respondent_name or "N/A",
        "status":           case.status.value if case.status else "N/A",
        "next_hearing_date": (
            case.next_hearing_date.strftime("%d %B %Y")
            if case.next_hearing_date else "Not scheduled"
        ),
        "judge_name":       case.judge_name or "Not assigned",
        "court_number":     case.court_number or "N/A",
        "bench_type":       case.bench_type or "N/A",
        "court_status":     case.court_status or "",
    }


# ---------------------------------------------------------------------------
# Precedent Finder helpers
# ---------------------------------------------------------------------------

def _build_precedent_finder_system(case_dict: dict) -> str:
    """
    System prompt for the Precedent Finder mode's independent tool loop.

    Instructs Claude on the tool cascade:
      1. search_judgment_kb first (fast, cached)
      2. search_indiankanoon if KB results < 2 or user wants more
      3. search_web as last resort
      4. search_legal_resources any time for statutes / rules / fees
    """
    from zoneinfo import ZoneInfo
    now_ist = datetime.now(ZoneInfo("Asia/Kolkata"))

    case_lines = []
    if case_dict:
        case_lines = [
            f"Case Number  : {case_dict.get('case_number', 'N/A')}",
            f"Case Type    : {case_dict.get('case_type', 'N/A')}",
            f"Petitioner   : {case_dict.get('petitioner_name', 'N/A')}",
            f"Respondent   : {case_dict.get('respondent_name', 'N/A')}",
            f"Status       : {case_dict.get('status', 'N/A')}",
            f"Next Hearing : {case_dict.get('next_hearing_date', 'Not scheduled')}",
            f"Judge        : {case_dict.get('judge_name', 'Not assigned')}",
        ]
    case_context = "\n".join(case_lines) if case_lines else "No case context provided."

    return f"""You are LawMate Precedent Finder — a dedicated legal research assistant \
for Kerala High Court advocates. Your sole purpose in this session is to find, \
evaluate, and present judicial precedents relevant to this case through iterative \
tool-driven research.

Today: {now_ist.strftime('%A, %d %B %Y')}  |  {now_ist.strftime('%I:%M %p IST')}

CASE CONTEXT:
{case_context}

────────────────────────────────────────────────────
TOOL CASCADE — follow this order strictly:

1. ALWAYS start with search_judgment_kb.
   → Fast, cached, no API cost.
   → If it returns 2 or more relevant judgments, present them and ask what to explore next.
   → If it returns fewer than 2 results OR the user asks for more, proceed to step 2.

2. Use search_indiankanoon when KB is insufficient.
   → Live IndianKanoon search covering all Kerala HC judgments.
   → Use refined queries — include the legal issue, relevant statute/section, year if known.
   → After presenting results, ask if the user wants to refine or explore a related issue.

3. Use search_web only as a last resort.
   → When both KB and IndianKanoon yield insufficient results.
   → Or when the user explicitly requests a web search.
   → Restricted to legal domains.

4. Use search_legal_resources at any time.
   → For statutes, Kerala HC rules, court fees, limitation periods, practice directions.
   → Always cite resource name and section number.

────────────────────────────────────────────────────
PRESENTATION FORMAT for each judgment found:

📋 [Case Name] ([Year])
   Citation  : [citation if available]
   Date      : [date]
   Source    : [IndianKanoon URL]
   Held      : [key holding — 2–3 sentences, specific to this case's issues]
   Relevance : [how it directly supports or challenges the advocate's position]

────────────────────────────────────────────────────
CRITICAL RULES:
- NEVER invent or guess citations. Only cite what the tools return.
- If a search returns no results, say so and immediately try a refined query.
- After each round of searches, ask the lawyer what angle to explore next.
- Cross-reference multiple judgments to identify consistent judicial trends.
- Flag any adverse precedents the opposing side might cite.
- You are a thinking partner — the lawyer makes all final decisions.
""".strip()


def _build_converse_messages(
    history: list[dict],
    new_message: str,
) -> list[dict]:
    """
    Convert session.messages history (role + content strings) to the
    Bedrock converse API format (role + content list of text blocks).
    """
    messages: list[dict] = []

    for item in history:
        role    = item.get("role")
        content = item.get("content", "")
        if role not in {"user", "assistant"}:
            continue
        if isinstance(content, str):
            messages.append({"role": role, "content": [{"text": content}]})
        else:
            # Already formatted (e.g. tool result blocks from a previous turn)
            messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": [{"text": new_message}]})

    # Bedrock requires the first message to be from "user"
    while messages and messages[0].get("role") != "user":
        messages.pop(0)

    return messages


# ---------------------------------------------------------------------------
# Public service
# ---------------------------------------------------------------------------

class PrepSessionService:
    """
    Manages Case Prep AI sessions end-to-end.
    """

    # -----------------------------------------------------------------------
    # Session CRUD
    # -----------------------------------------------------------------------

    def create_session(
        self,
        db: Session,
        user: User,
        case_id: str,
        mode: str,
        document_ids: list[str],
    ) -> PrepSession:
        """
        Create a new PrepSession for *case_id*, owned by *user*.

        Validates:
          - Case exists and belongs to the user
          - Mode is valid
          - All document_ids belong to the case
        """
        if mode not in PREP_MODES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid mode '{mode}'. Choose from: {', '.join(PREP_MODES)}",
            )

        case = db.query(Case).filter(Case.id == case_id).first()
        if case is None:
            raise HTTPException(status_code=404, detail="Case not found")
        if str(case.advocate_id) != str(user.id):
            raise HTTPException(status_code=403, detail="Access denied")

        # Validate documents
        if document_ids:
            docs = (
                db.query(Document)
                .filter(
                    Document.id.in_(document_ids),
                    Document.case_id == case_id,
                )
                .all()
            )
            if len(docs) != len(document_ids):
                raise HTTPException(
                    status_code=400,
                    detail="One or more document IDs are invalid or do not belong to this case",
                )

        session = PrepSession(
            case_id=case_id,
            user_id=str(user.id),
            mode=mode,
            document_ids=[str(d) for d in document_ids],
            messages=[],
        )
        db.add(session)
        db.commit()
        db.refresh(session)

        logger.info(
            "PrepSession %s created — case %s, mode %s, %d docs",
            session.id, case_id, mode, len(document_ids),
        )
        return session

    def list_sessions(
        self,
        db: Session,
        user_id: str,
        case_id: Optional[str] = None,
    ) -> list[PrepSession]:
        q = db.query(PrepSession).filter(PrepSession.user_id == user_id)
        if case_id:
            q = q.filter(PrepSession.case_id == case_id)
        return q.order_by(PrepSession.updated_at.desc()).all()

    def get_session(self, db: Session, session_id: str, user_id: str) -> PrepSession:
        return _get_session(db, session_id, user_id)

    def switch_mode(
        self,
        db: Session,
        session_id: str,
        user_id: str,
        new_mode: str,
    ) -> PrepSession:
        """Change the active mode; does NOT clear messages (history is retained)."""
        if new_mode not in PREP_MODES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid mode '{new_mode}'. Choose from: {', '.join(PREP_MODES)}",
            )
        session = _get_session(db, session_id, user_id)
        session.mode = new_mode
        session.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(session)
        return session

    def update_documents(
        self,
        db: Session,
        session_id: str,
        user_id: str,
        document_ids: list[str],
    ) -> PrepSession:
        """Replace the document scope for the session."""
        session = _get_session(db, session_id, user_id)

        if document_ids:
            docs = (
                db.query(Document)
                .filter(
                    Document.id.in_(document_ids),
                    Document.case_id == str(session.case_id),
                )
                .all()
            )
            if len(docs) != len(document_ids):
                raise HTTPException(
                    status_code=400,
                    detail="One or more document IDs are invalid",
                )

        session.document_ids = [str(d) for d in document_ids]
        session.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(session)
        return session

    def delete_session(self, db: Session, session_id: str, user_id: str) -> None:
        session = _get_session(db, session_id, user_id)
        db.delete(session)
        db.commit()
        logger.info("PrepSession %s deleted by user %s", session_id, user_id)

    # -----------------------------------------------------------------------
    # Document extraction
    # -----------------------------------------------------------------------

    def get_session_documents(
        self,
        db: Session,
        session: PrepSession,
    ) -> list[dict]:
        """
        Return a list of dicts with 'title' and 'extracted_text' for every
        document in scope.  BDA extraction is triggered (and cached) here if
        the document has not yet been extracted.
        """
        if not session.document_ids:
            return []

        docs = (
            db.query(Document)
            .filter(Document.id.in_(session.document_ids))
            .all()
        )

        results: list[dict] = []
        for doc in docs:
            # bda_service populates doc.extracted_text and commits
            bda_service.extract_document(doc, db)
            results.append(
                {
                    "title": doc.title or f"Document {doc.id}",
                    "extracted_text": doc.extracted_text or "",
                }
            )
        return results

    # -----------------------------------------------------------------------
    # Bedrock streaming with prompt caching
    # -----------------------------------------------------------------------

    async def stream_chat(
        self,
        db: Session,
        session_id: str,
        user_id: str,
        user_message: str,
    ) -> AsyncGenerator[str, None]:
        """
        Async generator that:
          1. Loads the session and its documents
          2. Builds the cached system prompt
          3. Builds the cached document-context block (first synthetic message)
          4. Streams the Bedrock response
          5. Persists the exchange to session.messages
          6. Yields SSE-formatted text_delta / done / error events
        """
        session = _get_session(db, session_id, user_id)

        case = db.query(Case).filter(Case.id == str(session.case_id)).first()
        if case is None:
            yield _sse({"type": "error", "message": "Case not found"})
            return

        # ── 1. Build case dict ───────────────────────────────────────────
        case_dict = _case_to_dict(case)

        # ── PRECEDENT FINDER: route through full agent with tool access ──
        # This mode uses search_judgments (IndianKanoon) + search_resources
        # (Bedrock KB) tools via the existing agent loop — no document
        # extraction needed.
        if session.mode == "precedent_finder":
            async for chunk in self._stream_precedent_finder(
                db=db,
                session=session,
                case_dict=case_dict,
                user_message=user_message,
                user_id=user_id,
            ):
                yield chunk
            return

        system_text = get_prep_system_prompt(session.mode, case_dict)

        # ── 2. Extract / retrieve document context ───────────────────────
        try:
            docs = self.get_session_documents(db, session)
        except Exception as exc:
            logger.exception("Document extraction failed for session %s: %s", session_id, exc)
            # Non-fatal — proceed without document context
            docs = []
            yield _sse({
                "type": "warning",
                "message": f"Could not extract document text ({exc}). Proceeding without document context.",
            })

        doc_context_text = format_document_context(docs)

        # Warn if all documents have empty extracted text
        all_empty = docs and all(not (d.get("extracted_text") or "").strip() for d in docs)
        if all_empty:
            yield _sse({
                "type": "warning",
                "message": (
                    "Could not extract text from the selected document(s) — "
                    "they may be scanned images or password-protected PDFs. "
                    "Claude will answer based on general legal knowledge only."
                ),
            })

        # ── 3. Build messages array ──────────────────────────────────────
        #
        # Message layout:
        #   [0]  synthetic "user" turn — document context (prompt-cached)
        #   [1]  synthetic "assistant" ack
        #   [2…] persisted history from session.messages
        #   [-1] current user message (not yet persisted)
        #
        # We use `cacheControl` on the synthetic document turn and the
        # system prompt so Bedrock can cache them across turns.

        persisted: list[dict] = session.messages or []

        messages: list[dict] = []

        # Synthetic document context turn
        # Note: cache_control is NOT allowed in message content blocks on Bedrock;
        # caching is applied only to the system prompt (see request_body below).
        if docs:
            messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Here are the case documents you should use as your "
                            "primary reference throughout this session:\n\n"
                            f"{doc_context_text}"
                        ),
                    }
                ],
            })
            messages.append({
                "role": "assistant",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Understood. I have read all the documents and I am "
                            "ready to assist with your hearing preparation."
                        ),
                    }
                ],
            })

        # Persisted conversation history
        for msg in persisted:
            messages.append({
                "role": msg["role"],
                "content": [{"type": "text", "text": msg["content"]}],
            })

        # Current user turn
        messages.append({
            "role": "user",
            "content": [{"type": "text", "text": user_message}],
        })

        # ── 4. Call Bedrock with streaming ───────────────────────────────
        bedrock = _bedrock_client()

        # Note: prompt caching (anthropic_beta + cache_control) is NOT supported
        # for Haiku on Bedrock ap-south-1 — omit both to avoid ValidationException.
        request_body: dict = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens":        _max_tokens(),
            "temperature":       _temperature(),
            "system":            system_text,
            "messages":          messages,
        }

        full_text = ""

        try:
            response = bedrock.invoke_model_with_response_stream(
                modelId=_prep_model_id(),
                body=json.dumps(request_body),
                contentType="application/json",
                accept="application/json",
            )

            for event in response["body"]:
                chunk_bytes = event.get("chunk", {}).get("bytes", b"")
                if not chunk_bytes:
                    continue
                chunk_data = json.loads(chunk_bytes)

                if chunk_data.get("type") == "content_block_delta":
                    delta = chunk_data.get("delta", {})
                    if delta.get("type") == "text_delta":
                        text_piece = delta.get("text", "")
                        full_text += text_piece
                        yield _sse({"type": "text_delta", "text": text_piece})

        except Exception as exc:
            logger.exception(
                "Bedrock streaming failed for session %s: %s", session_id, exc
            )
            yield _sse({"type": "error", "message": str(exc)})
            return

        # ── 5. Persist exchange ──────────────────────────────────────────
        try:
            updated_messages = list(persisted) + [
                {"role": "user",      "content": user_message},
                {"role": "assistant", "content": full_text},
            ]
            session.messages   = updated_messages
            session.updated_at = datetime.utcnow()
            db.commit()
        except Exception as exc:
            logger.warning(
                "Could not persist messages for session %s: %s", session_id, exc
            )

        # ── 6. Done event ─────────────────────────────────────────────────
        yield _sse({
            "type":       "done",
            "session_id": str(session.id),
            "full_text":  full_text,
        })

    # -----------------------------------------------------------------------
    # Precedent Finder — independent tool loop (no dependency on agent.py)
    # -----------------------------------------------------------------------

    async def _stream_precedent_finder(
        self,
        db: Session,
        session: PrepSession,
        case_dict: dict,
        user_message: str,
        user_id: str,
    ) -> AsyncGenerator[str, None]:
        """
        Self-contained streaming tool loop for Precedent Finder mode.

        Intentionally independent of agent.py so Case Prep AI can be
        deployed as a separate service at scale.

        Tool cascade:
          1. search_judgment_kb     — Bedrock KB (fast, cached)
          2. search_indiankanoon    — IndianKanoon API (live)
          3. search_web             — Tavily web search (last resort)
          4. search_legal_resources — Resources KB (statutes / rules / fees)

        Streams: tool_start, tool_end, text_delta, done, error SSE events.
        """
        from app.agent.prep_tools import (
            PREP_TOOL_SPECS,
            dispatch_prep_tool,
            summarise_prep_tool_result,
        )

        bedrock   = _bedrock_client()        # uses explicit creds from settings
        model_id  = _prep_model_id()
        full_text = ""

        # ── System prompt ────────────────────────────────────────────────
        system_prompt = _build_precedent_finder_system(case_dict)

        # ── Message history ──────────────────────────────────────────────
        messages = _build_converse_messages(session.messages or [], user_message)

        MAX_ITERATIONS = 8

        try:
            for _iteration in range(MAX_ITERATIONS):

                response = bedrock.converse_stream(
                    modelId=model_id,
                    system=[{"text": system_prompt}],
                    messages=messages,
                    toolConfig={
                        "tools": [{"toolSpec": t} for t in PREP_TOOL_SPECS]
                    },
                    inferenceConfig={
                        "maxTokens":   4096,
                        "temperature": 0.3,
                    },
                )

                current_tool:            dict | None = None
                current_tool_input_json: str         = ""
                stop_reason:             str | None  = None
                assistant_content:       list[dict]  = []
                current_text_block:      str         = ""

                for chunk in response["stream"]:
                    event_type = next(iter(chunk), None)

                    # ── text / tool input delta ──────────────────────────
                    if event_type == "contentBlockDelta":
                        delta = chunk["contentBlockDelta"].get("delta", {})

                        if "text" in delta:
                            text       = delta["text"]
                            full_text += text
                            current_text_block += text
                            yield _sse({"type": "text_delta", "text": text})

                        elif "toolUse" in delta:
                            current_tool_input_json += delta["toolUse"].get("input", "")

                    # ── block start ──────────────────────────────────────
                    elif event_type == "contentBlockStart":
                        start = chunk["contentBlockStart"].get("start", {})
                        if "toolUse" in start:
                            # Flush any accumulated text block first
                            if current_text_block:
                                assistant_content.append({"text": current_text_block})
                                current_text_block = ""

                            current_tool = {
                                "id":   start["toolUse"]["toolUseId"],
                                "name": start["toolUse"]["name"],
                            }
                            current_tool_input_json = ""
                            yield _sse({
                                "type":  "tool_start",
                                "tool":  current_tool["name"],
                                "input": {},
                            })

                    # ── block end → dispatch tool ────────────────────────
                    elif event_type == "contentBlockStop":
                        if current_tool:
                            tool_name = current_tool["name"]
                            tool_id   = current_tool["id"]

                            try:
                                tool_inputs = (
                                    json.loads(current_tool_input_json)
                                    if current_tool_input_json
                                    else {}
                                )
                            except json.JSONDecodeError:
                                tool_inputs = {}

                            # Dispatch tool (await is safe inside sync for-loop
                            # of an async generator)
                            tool_result = await dispatch_prep_tool(
                                tool_name=tool_name,
                                tool_inputs=tool_inputs,
                            )

                            yield _sse({
                                "type":    "tool_end",
                                "tool":    tool_name,
                                "success": tool_result.get("success", False),
                                "summary": summarise_prep_tool_result(tool_name, tool_result),
                            })

                            # Append tool use + result to message history
                            assistant_content.append({
                                "toolUse": {
                                    "toolUseId": tool_id,
                                    "name":      tool_name,
                                    "input":     tool_inputs,
                                }
                            })
                            messages.append({
                                "role":    "assistant",
                                "content": assistant_content,
                            })
                            messages.append({
                                "role": "user",
                                "content": [{
                                    "toolResult": {
                                        "toolUseId": tool_id,
                                        "content":   [{"text": json.dumps(tool_result)}],
                                        "status":    "success" if tool_result.get("success") else "error",
                                    }
                                }],
                            })

                            # Reset for next block
                            current_tool            = None
                            current_tool_input_json = ""
                            assistant_content       = []

                        elif current_text_block:
                            assistant_content.append({"text": current_text_block})
                            current_text_block = ""

                    # ── stop reason ──────────────────────────────────────
                    elif event_type == "messageStop":
                        stop_reason = chunk["messageStop"].get("stopReason")

                # ── After stream: handle stop reason ─────────────────────
                if stop_reason == "end_turn":
                    # Flush any remaining text into assistant content
                    if current_text_block:
                        assistant_content.append({"text": current_text_block})
                    if assistant_content:
                        messages.append({
                            "role":    "assistant",
                            "content": assistant_content,
                        })
                    break

                elif stop_reason == "tool_use":
                    # Tool was dispatched mid-stream — outer loop continues
                    continue

                else:
                    logger.warning(
                        "Precedent finder unexpected stop_reason=%s for session %s",
                        stop_reason, session.id,
                    )
                    break

            # ── Persist exchange ─────────────────────────────────────────
            try:
                updated = list(session.messages or []) + [
                    {
                        "role":    "user",
                        "content": user_message,
                        "ts":      datetime.utcnow().isoformat(),
                    },
                    {
                        "role":    "assistant",
                        "content": full_text,
                        "ts":      datetime.utcnow().isoformat(),
                    },
                ]
                session.messages   = updated
                session.updated_at = datetime.utcnow()
                db.commit()
            except Exception as exc:
                logger.warning(
                    "Could not persist precedent finder messages for session %s: %s",
                    session.id, exc,
                )

            yield _sse({
                "type":       "done",
                "session_id": str(session.id),
                "full_text":  full_text,
            })

        except Exception as exc:
            logger.error(
                "Precedent finder stream failed for session %s: %s",
                session.id, exc,
            )
            yield _sse({"type": "error", "message": str(exc)})

    # -----------------------------------------------------------------------
    # Export to HearingBrief
    # -----------------------------------------------------------------------

    def export_to_hearing_brief(
        self,
        db: Session,
        session_id: str,
        user_id: str,
        hearing_date: Optional[datetime] = None,
        focus_areas: Optional[list[str]] = None,
    ) -> HearingBrief:
        """
        Synthesise the session conversation into a HearingBrief record.

        The brief content is generated by asking Claude to summarise the
        session into an actionable one-page prep brief.  If Bedrock is
        unavailable, a structured fallback summary is produced from the
        raw messages.
        """
        session = _get_session(db, session_id, user_id)

        case = db.query(Case).filter(Case.id == str(session.case_id)).first()
        if case is None:
            raise HTTPException(status_code=404, detail="Case not found")

        messages: list[dict] = session.messages or []
        if not messages:
            raise HTTPException(
                status_code=400,
                detail="Session has no messages to export",
            )

        # Build a condensed conversation text for the summarisation call
        conversation_text = "\n\n".join(
            f"[{m['role'].upper()}]\n{m['content']}"
            for m in messages
        )

        brief_content = self._generate_brief_content(
            conversation_text=conversation_text,
            mode=session.mode,
            case_data=_case_to_dict(case),
        )

        # Bundle snapshot — list of doc titles in scope
        docs = (
            db.query(Document)
            .filter(Document.id.in_(session.document_ids or []))
            .all()
        )
        bundle_snapshot = {
            "session_id":    str(session.id),
            "mode":          session.mode,
            "document_count": len(docs),
            "documents": [
                {"id": str(d.id), "title": d.title}
                for d in docs
            ],
            "exported_at": datetime.utcnow().isoformat(),
        }

        brief = HearingBrief(
            case_id=str(session.case_id),
            hearing_date=hearing_date or datetime.utcnow(),
            content=brief_content,
            focus_areas=focus_areas or [session.mode],
            bundle_snapshot=bundle_snapshot,
        )
        db.add(brief)
        db.commit()
        db.refresh(brief)

        logger.info(
            "HearingBrief %s created from PrepSession %s (case %s)",
            brief.id, session_id, session.case_id,
        )
        return brief

    def _generate_brief_content(
        self,
        conversation_text: str,
        mode: str,
        case_data: dict,
    ) -> str:
        """
        Call Bedrock synchronously to generate a one-page prep brief.
        Falls back to a structured plain-text summary on any error.
        """
        summarisation_prompt = f"""
You are preparing a one-page hearing brief for an advocate about to appear \
before the Kerala High Court.

The brief should be in plain English, structured under these headings:
1. Case Summary (2–3 sentences)
2. Key Arguments (bullet points)
3. Anticipated Objections / Questions from the Bench
4. Relief Sought
5. Key Documents Referenced
6. Action Items Before Hearing

Use only the information from the preparation session below.  \
Do not invent any facts.

Mode this session was run in: {mode}
Case: {case_data.get('case_number', 'N/A')} — {case_data.get('case_type', 'N/A')}
Petitioner: {case_data.get('petitioner_name', 'N/A')}
Respondent: {case_data.get('respondent_name', 'N/A')}

PREPARATION SESSION TRANSCRIPT:
{conversation_text[:15000]}
"""

        try:
            bedrock = _bedrock_client()
            response = bedrock.invoke_model(
                modelId=_prep_model_id(),
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 2048,
                    "temperature": 0.2,
                    "messages": [
                        {"role": "user", "content": summarisation_prompt}
                    ],
                }),
                contentType="application/json",
                accept="application/json",
            )
            result = json.loads(response["body"].read())
            content_blocks = result.get("content", [])
            return "".join(
                block.get("text", "")
                for block in content_blocks
                if block.get("type") == "text"
            ).strip() or _fallback_brief(conversation_text, mode)

        except Exception as exc:
            logger.warning("Brief generation via Bedrock failed: %s", exc)
            return _fallback_brief(conversation_text, mode)


def _fallback_brief(conversation_text: str, mode: str) -> str:
    """Plain-text fallback when Bedrock is unavailable."""
    lines = conversation_text.split("\n")
    assistant_lines = [
        l for l in lines
        if l.strip() and not l.startswith("[USER]")
    ]
    excerpt = "\n".join(assistant_lines[:60])
    return (
        f"HEARING BRIEF (auto-generated from {mode} session)\n"
        f"{'=' * 60}\n\n"
        f"{excerpt}\n\n"
        "(Full session transcript available in the Case Prep AI session.)"
    )


# Singleton
prep_session_service = PrepSessionService()
