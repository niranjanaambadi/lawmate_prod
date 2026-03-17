"""
app/services/drafting_service.py

Core orchestration for the Drafting AI feature:
  - Workspace CRUD (5-workspace cap per user)
  - Document upload → S3 → text extraction → classification → KB ingestion
  - Case context extraction (structured JSON via Claude)
  - SSE streaming chat with full-context or hybrid-RAG strategy
  - Draft generation with extended thinking
  - Draft CRUD

All DB-mutating methods expect a live SQLAlchemy Session (sync) passed by the
FastAPI endpoint.  Streaming helpers are async generators.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import uuid as _uuid
from datetime import datetime
from typing import Any, AsyncGenerator, Optional

import boto3
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Workspace, WorkspaceDocument, WorkspaceDraft
from app.utils.chunker import chunk_text, estimate_tokens
from app.utils.pdf_extractor import extract_text_from_pdf

logger = logging.getLogger(__name__)

# ── Model IDs (resolved at runtime) ──────────────────────────────────────────

def _drafting_model() -> str:
    return (settings.DRAFTING_MODEL_ID or settings.CHAT_AGENT_MODEL_ID).strip()

def _haiku_model() -> str:
    return (settings.DRAFTING_HAIKU_MODEL_ID or settings.BEDROCK_MODEL_ID).strip()

def _bedrock_runtime():
    return boto3.client(
        "bedrock-runtime",
        region_name=settings.AWS_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    )

def _s3_client():
    return boto3.client(
        "s3",
        region_name=settings.AWS_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    )

# ── Keywords that trigger extended thinking ───────────────────────────────────
_THINKING_KEYWORDS = {
    "analyze", "analyse", "recommend", "what should", "gap",
    "missing", "checklist", "strategy", "weakness", "strength",
}


def _needs_thinking(text: str) -> bool:
    t = text.lower()
    return any(kw in t for kw in _THINKING_KEYWORDS)


# ============================================================================
# Workspace CRUD
# ============================================================================

def create_workspace(db: Session, user_id: str, label: str = "Untitled") -> Workspace:
    """Create a new workspace. Raises ValueError at the 5-workspace cap."""
    count = (
        db.query(Workspace)
        .filter(Workspace.user_id == user_id)
        .count()
    )
    if count >= settings.DRAFTING_MAX_WORKSPACES:
        raise ValueError(
            f"Workspace limit reached ({settings.DRAFTING_MAX_WORKSPACES}). "
            "Delete an existing workspace before creating a new one."
        )
    ws = Workspace(
        user_id=user_id,
        label=label.strip() or "Untitled",
    )
    db.add(ws)
    db.commit()
    db.refresh(ws)
    logger.info("Created workspace %s for user %s", ws.id, user_id)
    return ws


def list_workspaces(db: Session, user_id: str) -> list[Workspace]:
    return (
        db.query(Workspace)
        .filter(Workspace.user_id == user_id)
        .order_by(Workspace.created_at.desc())
        .all()
    )


def get_workspace(db: Session, workspace_id: str, user_id: str) -> Workspace:
    ws = (
        db.query(Workspace)
        .filter(Workspace.id == workspace_id, Workspace.user_id == user_id)
        .first()
    )
    if not ws:
        raise LookupError(f"Workspace {workspace_id} not found.")
    return ws


def update_workspace(
    db: Session,
    workspace_id: str,
    user_id: str,
    label: Optional[str] = None,
    case_context: Optional[dict] = None,
    conversation_history: Optional[list] = None,
) -> Workspace:
    ws = get_workspace(db, workspace_id, user_id)
    if label is not None:
        ws.label = label.strip() or "Untitled"
    if case_context is not None:
        ws.case_context = case_context
    if conversation_history is not None:
        ws.conversation_history = conversation_history
    ws.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(ws)
    return ws


def delete_workspace(db: Session, workspace_id: str, user_id: str) -> None:
    """Delete workspace, its S3 objects, and all related DB records."""
    ws = get_workspace(db, workspace_id, user_id)
    docs = list(ws.documents)

    # Delete S3 objects (best-effort — don't block on failure)
    if docs:
        try:
            s3 = _s3_client()
            bucket = settings.S3_BUCKET_NAME
            s3.delete_objects(
                Bucket=bucket,
                Delete={
                    "Objects": [{"Key": d.s3_key} for d in docs if d.s3_key]
                },
            )
        except Exception as exc:
            logger.warning("S3 cleanup for workspace %s partial: %s", workspace_id, exc)

    db.delete(ws)
    db.commit()
    logger.info("Deleted workspace %s", workspace_id)


# ============================================================================
# Document management
# ============================================================================

async def upload_document(
    db: Session,
    workspace_id: str,
    user_id: str,
    file_bytes: bytes,
    filename: str,
    content_type: str = "application/pdf",
) -> dict:
    """
    Upload a document to S3, extract text, classify, ingest into KB.

    Returns a dict representation of the WorkspaceDocument row.
    """
    ws = get_workspace(db, workspace_id, user_id)

    # Enforce per-workspace doc cap
    doc_count = db.query(WorkspaceDocument).filter(
        WorkspaceDocument.workspace_id == workspace_id
    ).count()
    if doc_count >= settings.DRAFTING_MAX_DOCS_PER_WORKSPACE:
        raise ValueError(
            f"Document limit reached ({settings.DRAFTING_MAX_DOCS_PER_WORKSPACE}) "
            "for this workspace."
        )

    # Validate file size
    max_bytes = settings.DRAFTING_MAX_FILE_MB * 1024 * 1024
    if len(file_bytes) > max_bytes:
        raise ValueError(
            f"File exceeds the {settings.DRAFTING_MAX_FILE_MB} MB limit "
            f"({len(file_bytes) // (1024*1024)} MB received)."
        )

    doc_id  = str(_uuid.uuid4())
    s3_key  = f"drafting/{workspace_id}/{doc_id}/{filename}"
    bucket  = settings.S3_BUCKET_NAME

    # ── Upload to S3 ──────────────────────────────────────────────────────────
    try:
        s3 = _s3_client()
        s3.put_object(
            Bucket=bucket,
            Key=s3_key,
            Body=file_bytes,
            ContentType=content_type,
        )
    except Exception as exc:
        raise RuntimeError(f"S3 upload failed: {exc}") from exc

    # ── Extract text ──────────────────────────────────────────────────────────
    extracted_text, page_count, was_ocr = extract_text_from_pdf(file_bytes)
    token_estimate = estimate_tokens(extracted_text)

    # ── Classify document type ────────────────────────────────────────────────
    doc_type = await _classify_doc_type(extracted_text[:2000])

    # ── Decide strategy ───────────────────────────────────────────────────────
    # Will be re-evaluated at chat time across all docs; stored per-doc here.
    strategy = "full_context"

    # ── Save to DB ────────────────────────────────────────────────────────────
    doc = WorkspaceDocument(
        id=_uuid.UUID(doc_id),
        workspace_id=_uuid.UUID(workspace_id),
        filename=filename,
        doc_type=doc_type,
        s3_key=s3_key,
        size_bytes=len(file_bytes),
        page_count=page_count,
        extracted_text=extracted_text,
        token_estimate=token_estimate,
        strategy=strategy,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # ── Fire-and-forget KB ingestion ──────────────────────────────────────────
    asyncio.create_task(
        _ingest_doc_to_kb(extracted_text, str(doc.id), workspace_id, filename)
    )

    # ── Trigger context re-extraction in background ───────────────────────────
    asyncio.create_task(_run_context_extraction(db, workspace_id, user_id))

    return _doc_to_dict(doc)


async def delete_document(
    db: Session,
    workspace_id: str,
    doc_id: str,
    user_id: str,
) -> None:
    """Delete a document from DB and S3, then re-run context extraction."""
    get_workspace(db, workspace_id, user_id)   # ownership check

    doc = db.query(WorkspaceDocument).filter(
        WorkspaceDocument.id == doc_id,
        WorkspaceDocument.workspace_id == workspace_id,
    ).first()
    if not doc:
        raise LookupError(f"Document {doc_id} not found in workspace {workspace_id}.")

    # Delete S3 object (best-effort)
    try:
        s3 = _s3_client()
        s3.delete_object(Bucket=settings.S3_BUCKET_NAME, Key=doc.s3_key)
    except Exception as exc:
        logger.warning("S3 delete for doc %s skipped: %s", doc_id, exc)

    db.delete(doc)
    db.commit()

    # Re-run context extraction
    asyncio.create_task(_run_context_extraction(db, workspace_id, user_id))


# ============================================================================
# Case context extraction
# ============================================================================

async def extract_case_context(
    db: Session,
    workspace_id: str,
    user_id: str,
) -> dict:
    """
    Run Claude Sonnet over all documents in the workspace to extract a
    structured case context JSON. Saves result to workspace.case_context.
    """
    ws = get_workspace(db, workspace_id, user_id)
    docs = list(ws.documents)

    if not docs:
        empty: dict = {}
        ws.case_context = empty
        ws.updated_at = datetime.utcnow()
        db.commit()
        return empty

    # Build document text block (first 20K chars per doc to stay within limits)
    doc_block = "\n\n".join(
        f"[{d.filename}]\n{(d.extracted_text or '')[:20000]}"
        for d in docs
    )

    from app.agent.drafting_prompts import EXTRACTION_PROMPT
    prompt = EXTRACTION_PROMPT.format(documents=doc_block)

    try:
        client = _bedrock_runtime()
        response = client.converse(
            modelId=_drafting_model(),
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 4096, "temperature": 0.1},
        )
        raw = (
            response.get("output", {})
            .get("message", {})
            .get("content", [{}])[0]
            .get("text", "{}")
            .strip()
        )
        # Strip markdown fences if present
        if "```" in raw:
            parts = raw.split("```")
            raw = parts[1] if len(parts) >= 2 else raw
            if raw.lower().startswith("json"):
                raw = raw[4:]
        context_data: dict = json.loads(raw.strip())
    except Exception as exc:
        logger.warning("extract_case_context failed: %s", exc)
        context_data = {}

    ws.case_context = context_data
    ws.updated_at   = datetime.utcnow()
    db.commit()
    return context_data


# ============================================================================
# Topic-shift detection
# ============================================================================

async def detect_topic_shift(workspace: Workspace, new_message: str) -> tuple[bool, str]:
    """
    Use Haiku to detect if new_message is about a completely different legal
    matter than the existing workspace case context.

    Returns (shift_detected: bool, reason: str).
    Conservative: only fires on high/medium confidence to avoid false positives.
    """
    ctx = workspace.case_context
    if not ctx:
        return False, ""

    # Build a brief, grounded summary of the existing context
    parts: list[str] = []
    if ctx.get("caseType"):
        parts.append(f"Case type: {ctx['caseType']}")
    raw_parties = ctx.get("parties") or {}
    if isinstance(raw_parties, dict):
        pet = raw_parties.get("petitioner") or raw_parties.get("plaintiff") or ""
        res = raw_parties.get("respondent") or raw_parties.get("defendant") or ""
        if pet or res:
            parts.append(f"Parties: {pet} vs {res}".strip(" vs"))
    elif isinstance(raw_parties, str) and raw_parties:
        parts.append(f"Parties: {raw_parties}")
    issues = ctx.get("keyIssues") or ctx.get("key_issues") or []
    if isinstance(issues, list) and issues:
        parts.append(f"Key issues: {', '.join(str(i) for i in issues[:3])}")
    if ctx.get("court"):
        parts.append(f"Court: {ctx['court']}")

    if not parts:
        return False, ""

    context_summary = "\n".join(parts)
    prompt = (
        "You are a legal workspace assistant.\n\n"
        "Existing workspace context:\n"
        f"{context_summary}\n\n"
        f'User\'s new message: "{new_message}"\n\n'
        "Task: Is the user asking about a COMPLETELY DIFFERENT legal matter "
        "(different case, unrelated parties, entirely separate legal issue)?\n\n"
        "Be CONSERVATIVE — questions that could plausibly relate to the same case "
        "should return false. Only return shift_detected=true when you are highly "
        "confident this is a brand-new case or unrelated matter.\n\n"
        'Reply with JSON only (no markdown): '
        '{"shift_detected": true/false, "confidence": "high"|"medium"|"low", '
        '"reason": "one sentence"}'
    )

    try:
        client = _bedrock_runtime()
        response = client.converse(
            modelId=_haiku_model(),
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 200, "temperature": 0},
        )
        raw = (
            response.get("output", {})
            .get("message", {})
            .get("content", [{}])[0]
            .get("text", "{}")
            .strip()
        )
        result    = json.loads(raw)
        shift     = bool(result.get("shift_detected", False))
        confidence = result.get("confidence", "low")
        reason    = result.get("reason", "")
        if shift and confidence in ("high", "medium"):
            return True, reason
        return False, ""
    except Exception as exc:
        logger.warning("detect_topic_shift failed (safe-fallback): %s", exc)
        return False, ""   # never block the user on detection errors


# ============================================================================
# Bulk-clear workspace documents
# ============================================================================

async def clear_workspace_documents(
    db: Session,
    workspace_id: str,
    user_id: str,
) -> None:
    """
    Delete every document from the workspace (S3 + DB), reset case_context
    and conversation_history.  Used when the user confirms they are starting
    a new case in the same workspace.
    """
    ws   = get_workspace(db, workspace_id, user_id)
    docs = list(ws.documents)

    s3 = _s3_client()
    for doc in docs:
        try:
            s3.delete_object(Bucket=settings.S3_BUCKET_NAME, Key=doc.s3_key)
        except Exception as exc:
            logger.warning("S3 delete for doc %s skipped: %s", doc.id, exc)
        db.delete(doc)

    ws.case_context          = {}
    ws.conversation_history  = []
    ws.updated_at            = datetime.utcnow()
    db.commit()
    logger.info("Workspace %s cleared (%d docs removed).", workspace_id, len(docs))


# ============================================================================
# SSE streaming chat
# ============================================================================

async def stream_chat(
    db: Session,
    workspace_id: str,
    user_id: str,
    message: str,
    history: list[dict],
    skip_shift_detection: bool = False,
) -> AsyncGenerator[str, None]:
    """
    Stream a chat response as SSE-formatted JSON strings.

    Yields lines like:
        data: {"type": "text_delta",       "text": "…"}
        data: {"type": "thinking_delta",   "text": "…"}
        data: {"type": "cited_docs",       "doc_ids": […]}
        data: {"type": "context_mismatch", "reason": "…"}
        data: {"type": "done",             "full_text": "…"}
        data: {"type": "error",            "message": "…"}

    If a topic-shift is detected (and skip_shift_detection is False) the
    generator yields a single context_mismatch event and returns — the
    frontend must confirm and re-send with skip_shift_detection=True.
    """
    ws   = get_workspace(db, workspace_id, user_id)
    docs = list(ws.documents)

    # ── Topic-shift guard ─────────────────────────────────────────────────────
    if not skip_shift_detection and docs and ws.case_context:
        shift, reason = await detect_topic_shift(ws, message)
        if shift:
            yield _sse({"type": "context_mismatch", "reason": reason})
            return

    # ── Decide RAG strategy ───────────────────────────────────────────────────
    total_tokens = sum(
        d.token_estimate for d in docs if d.extracted_text
    )
    use_full_context = total_tokens <= settings.DRAFTING_FULL_CONTEXT_TOKEN_LIMIT

    if not use_full_context:
        yield _sse({"type": "warning", "message":
                    "Switching to retrieval mode — total document size exceeds "
                    f"{settings.DRAFTING_FULL_CONTEXT_TOKEN_LIMIT:,} tokens."})

    # ── Build document context ────────────────────────────────────────────────
    if use_full_context:
        docs_text = _build_full_context(docs)
    else:
        chunks = await _retrieve_rag_context(message, workspace_id)
        docs_text = _build_rag_context(chunks)

    # ── System prompt ─────────────────────────────────────────────────────────
    from app.agent.drafting_prompts import build_khc_system_prompt
    case_ctx_text = _format_case_context(ws.case_context)
    system_prompt = build_khc_system_prompt(case_ctx_text)

    # ── Build messages ────────────────────────────────────────────────────────
    convo_messages: list[dict] = []
    if docs_text:
        # First turn: inject document context with prompt caching
        convo_messages.append({
            "role": "user",
            "content": [
                {
                    "text": docs_text,
                    "cacheControl": {"type": "ephemeral"},
                },
                {"text": "(Documents loaded. Ready for your question.)"},
            ],
        })
        convo_messages.append({
            "role": "assistant",
            "content": [{"text": "Understood — I have reviewed all the documents. What would you like to work on?"}],
        })

    # Prior conversation history
    for turn in history:
        role    = turn.get("role", "user")
        content = turn.get("content", "")
        if role in ("user", "assistant") and content:
            convo_messages.append({
                "role": role,
                "content": [{"text": str(content)}],
            })

    # Current user message
    convo_messages.append({"role": "user", "content": [{"text": message}]})

    # ── Extended thinking ─────────────────────────────────────────────────────
    extra_fields: dict = {}
    use_thinking = _needs_thinking(message)
    if use_thinking:
        extra_fields = {"thinking": {"type": "enabled", "budgetTokens": 10000}}

    # ── Stream ────────────────────────────────────────────────────────────────
    try:
        client = _bedrock_runtime()
        stream_kwargs: dict[str, Any] = dict(
            modelId=_drafting_model(),
            system=[{"text": system_prompt}],
            messages=convo_messages,
            inferenceConfig={"maxTokens": 8192, "temperature": 0.3},
        )
        if extra_fields:
            stream_kwargs["additionalModelRequestFields"] = extra_fields

        response = client.converse_stream(**stream_kwargs)
        stream   = response.get("stream")
        if not stream:
            yield _sse({"type": "error", "message": "No stream returned from Bedrock."})
            return

        full_text     = []
        cited_doc_ids = set()

        for event in stream:
            # Text delta
            if "contentBlockDelta" in event:
                delta = event["contentBlockDelta"].get("delta", {})
                if "text" in delta:
                    chunk = delta["text"]
                    full_text.append(chunk)
                    yield _sse({"type": "text_delta", "text": chunk})

                    # Collect cited document filenames → match to IDs
                    for doc in docs:
                        if doc.filename.lower() in chunk.lower():
                            cited_doc_ids.add(str(doc.id))

                elif "reasoningContent" in delta:
                    thinking_chunk = delta["reasoningContent"].get("text", "")
                    if thinking_chunk:
                        yield _sse({"type": "thinking_delta", "text": thinking_chunk})

        assembled = "".join(full_text)

        if cited_doc_ids:
            yield _sse({"type": "cited_docs", "doc_ids": list(cited_doc_ids)})

        yield _sse({"type": "done", "full_text": assembled})

    except Exception as exc:
        logger.error("stream_chat error: %s", exc)
        yield _sse({"type": "error", "message": str(exc)})


# ============================================================================
# Draft generation
# ============================================================================

async def generate_draft(
    db: Session,
    workspace_id: str,
    user_id: str,
    doc_type: str,
    brief: str,
) -> dict:
    """
    Generate a complete draft document using Claude with extended thinking.

    Returns a dict representation of the created WorkspaceDraft row.
    """
    ws   = get_workspace(db, workspace_id, user_id)
    docs = list(ws.documents)

    # Retrieve precedents from KB
    from app.utils.embedder import retrieve_from_kb
    prec_chunks = await retrieve_from_kb(
        f"{doc_type} Kerala High Court",
        workspace_id,
        top_k=5,
    )
    precedents_text = "\n\n".join(
        f"[Precedent {i+1}] {c.get('text', '')[:500]}"
        for i, c in enumerate(prec_chunks)
    ) if prec_chunks else ""

    from app.agent.drafting_prompts import get_drafting_prompt
    case_ctx_text = _format_case_context(ws.case_context)
    docs_context  = _build_full_context(docs)

    prompt = get_drafting_prompt(
        doc_type=doc_type,
        case_context=case_ctx_text,
        brief=brief,
        precedents=precedents_text,
    )

    full_prompt = f"{docs_context}\n\n{prompt}" if docs_context else prompt

    try:
        client   = _bedrock_runtime()
        response = client.converse(
            modelId=_drafting_model(),
            messages=[{"role": "user", "content": [{"text": full_prompt}]}],
            inferenceConfig={"maxTokens": 16000, "temperature": 0.2},
            additionalModelRequestFields={
                "thinking": {"type": "enabled", "budgetTokens": 10000}
            },
        )
        content_blocks = (
            response.get("output", {})
            .get("message", {})
            .get("content", [])
        )
        draft_text = " ".join(
            b.get("text", "")
            for b in content_blocks
            if b.get("type") == "text" or "text" in b
        ).strip()

    except Exception as exc:
        raise RuntimeError(f"Draft generation failed: {exc}") from exc

    # ── Save draft ────────────────────────────────────────────────────────────
    title = f"{doc_type} — {datetime.utcnow().strftime('%d %b %Y %H:%M')} UTC"
    draft = WorkspaceDraft(
        workspace_id=_uuid.UUID(workspace_id),
        title=title,
        doc_type=doc_type,
        content=draft_text,
        version=1,
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return _draft_to_dict(draft)


# ============================================================================
# Draft CRUD helpers
# ============================================================================

def list_drafts(db: Session, workspace_id: str, user_id: str) -> list[dict]:
    get_workspace(db, workspace_id, user_id)
    drafts = (
        db.query(WorkspaceDraft)
        .filter(WorkspaceDraft.workspace_id == workspace_id)
        .order_by(WorkspaceDraft.created_at.desc())
        .all()
    )
    return [_draft_to_dict(d) for d in drafts]


def get_draft(db: Session, workspace_id: str, draft_id: str, user_id: str) -> dict:
    get_workspace(db, workspace_id, user_id)
    draft = db.query(WorkspaceDraft).filter(
        WorkspaceDraft.id == draft_id,
        WorkspaceDraft.workspace_id == workspace_id,
    ).first()
    if not draft:
        raise LookupError(f"Draft {draft_id} not found.")
    return _draft_to_dict(draft)


def save_draft(
    db: Session,
    workspace_id: str,
    draft_id: str,
    user_id: str,
    content: str,
    title: Optional[str] = None,
) -> dict:
    get_workspace(db, workspace_id, user_id)
    draft = db.query(WorkspaceDraft).filter(
        WorkspaceDraft.id == draft_id,
        WorkspaceDraft.workspace_id == workspace_id,
    ).first()
    if not draft:
        raise LookupError(f"Draft {draft_id} not found.")
    draft.content    = content
    draft.version   += 1
    draft.updated_at = datetime.utcnow()
    if title:
        draft.title = title.strip()
    db.commit()
    db.refresh(draft)
    return _draft_to_dict(draft)


def delete_draft(
    db: Session,
    workspace_id: str,
    draft_id: str,
    user_id: str,
) -> None:
    get_workspace(db, workspace_id, user_id)
    draft = db.query(WorkspaceDraft).filter(
        WorkspaceDraft.id == draft_id,
        WorkspaceDraft.workspace_id == workspace_id,
    ).first()
    if not draft:
        raise LookupError(f"Draft {draft_id} not found.")
    db.delete(draft)
    db.commit()


# ============================================================================
# Internal helpers
# ============================================================================

def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _build_full_context(docs: list[WorkspaceDocument]) -> str:
    if not docs:
        return ""
    parts = []
    for i, doc in enumerate(docs, 1):
        text = (doc.extracted_text or "").strip()
        if not text:
            text = "(Text extraction pending.)"
        parts.append(f"[DOCUMENT {i}: {doc.filename}]\n{text}")
    return "\n\n".join(parts)


async def _retrieve_rag_context(query: str, workspace_id: str) -> list[dict]:
    from app.utils.embedder import retrieve_from_kb
    return await retrieve_from_kb(query, workspace_id, top_k=8)


def _build_rag_context(chunks: list[dict]) -> str:
    if not chunks:
        return "(No relevant document chunks retrieved.)"
    parts = [
        f"[RETRIEVED CHUNK {i+1} (score={c.get('score', 0):.2f})]\n{c.get('text', '')}"
        for i, c in enumerate(chunks)
    ]
    return "\n\n".join(parts)


def _format_case_context(ctx: Optional[dict]) -> str:
    if not ctx:
        return "No case context extracted yet."
    lines = []
    if p := ctx.get("parties"):
        lines.append(f"Petitioner: {p.get('petitioner', 'N/A')}")
        lines.append(f"Respondent: {p.get('respondent', 'N/A')}")
    for key in ("caseType", "caseNumber", "courtNumber", "judge", "nextHearing",
                "status", "reliefSought"):
        val = ctx.get(key)
        if val:
            lines.append(f"{key}: {val}")
    if secs := ctx.get("sectionsInvoked"):
        lines.append("Sections: " + ", ".join(secs))
    return "\n".join(lines)


async def _classify_doc_type(excerpt: str) -> Optional[str]:
    from app.agent.drafting_prompts import CLASSIFY_PROMPT
    prompt = CLASSIFY_PROMPT.format(excerpt=excerpt)
    try:
        client = _bedrock_runtime()
        response = client.converse(
            modelId=_haiku_model(),
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 20, "temperature": 0.0},
        )
        raw = (
            response.get("output", {})
            .get("message", {})
            .get("content", [{}])[0]
            .get("text", "")
            .strip()
        )
        return raw if raw else None
    except Exception as exc:
        logger.debug("_classify_doc_type failed: %s", exc)
        return None


async def _ingest_doc_to_kb(
    text: str,
    doc_id: str,
    workspace_id: str,
    filename: str,
) -> None:
    from app.utils.chunker import chunk_text
    from app.utils.embedder import ingest_chunk_to_kb

    chunks = chunk_text(text, chunk_size=512, overlap=50)
    tasks  = [
        ingest_chunk_to_kb(chunk, workspace_id, doc_id, filename)
        for chunk in chunks
    ]
    await asyncio.gather(*tasks, return_exceptions=True)


async def _run_context_extraction(
    db: Session, workspace_id: str, user_id: str
) -> None:
    try:
        await extract_case_context(db, workspace_id, user_id)
    except Exception as exc:
        logger.debug("Background context extraction failed: %s", exc)


# ── Serialisation helpers ─────────────────────────────────────────────────────

def _ws_to_dict(ws: Workspace) -> dict:
    return {
        "id":                  str(ws.id),
        "userId":              ws.user_id,
        "label":               ws.label,
        "caseContext":         ws.case_context,
        "conversationHistory": ws.conversation_history or [],
        "createdAt":           ws.created_at.isoformat() if ws.created_at else None,
        "updatedAt":           ws.updated_at.isoformat() if ws.updated_at else None,
        "documents": [_doc_to_dict(d) for d in (ws.documents or [])],
        "drafts":    [_draft_to_dict(d) for d in (ws.drafts or [])],
    }


def _doc_to_dict(doc: WorkspaceDocument) -> dict:
    return {
        "id":            str(doc.id),
        "workspaceId":   str(doc.workspace_id),
        "filename":      doc.filename,
        "docType":       doc.doc_type,
        "s3Key":         doc.s3_key,
        "sizeBytes":     doc.size_bytes,
        "pageCount":     doc.page_count,
        "tokenEstimate": doc.token_estimate,
        "strategy":      doc.strategy,
        "uploadedAt":    doc.uploaded_at.isoformat() if doc.uploaded_at else None,
    }


def _draft_to_dict(draft: WorkspaceDraft) -> dict:
    return {
        "id":          str(draft.id),
        "workspaceId": str(draft.workspace_id),
        "title":       draft.title,
        "docType":     draft.doc_type,
        "content":     draft.content,
        "version":     draft.version,
        "createdAt":   draft.created_at.isoformat() if draft.created_at else None,
        "updatedAt":   draft.updated_at.isoformat() if draft.updated_at else None,
    }
