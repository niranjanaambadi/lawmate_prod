"""
Case notebook endpoints (private per-lawyer).
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import func, text
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user
from app.db.database import get_db
from app.db.models import Case, CaseNotebook, HearingNote, Note, NoteAttachment, User
from app.db.schemas import (
    CaseNotebookListItem,
    CaseNotebookResponse,
    NoteAttachmentCreate,
    NoteAttachmentResponse,
    NoteCreate,
    NoteResponse,
    NoteUpdate,
    NotebookSearchItem,
)
from app.services.s3_service import S3Service

router = APIRouter()

class SendToHearingDayRequest(BaseModel):
    mode: str = Field(..., pattern="^(chapter|selection)$")
    selected_text: str | None = None


def _append_text_to_doc_json(current_json: dict | None, block_text: str) -> dict:
    base = current_json if isinstance(current_json, dict) else {"type": "doc", "content": []}
    content = base.get("content")
    if not isinstance(content, list):
        base["content"] = []
        content = base["content"]
    for line in [ln.strip() for ln in block_text.splitlines() if ln.strip()]:
        content.append({"type": "paragraph", "content": [{"type": "text", "text": line}]})
    return base


def _ensure_owned_case(case_id: UUID, current_user: User, db: Session) -> Case:
    case = (
        db.query(Case)
        .filter(Case.id == case_id, Case.advocate_id == current_user.id, Case.is_visible == True)
        .first()
    )
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    return case


def _ensure_owned_notebook(notebook_id: UUID, current_user: User, db: Session) -> CaseNotebook:
    notebook = (
        db.query(CaseNotebook)
        .options(joinedload(CaseNotebook.notes).joinedload(Note.attachments))
        .filter(CaseNotebook.id == notebook_id, CaseNotebook.user_id == current_user.id)
        .first()
    )
    if not notebook:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notebook not found")
    return notebook


def _ensure_owned_note(note_id: UUID, current_user: User, db: Session) -> Note:
    note = (
        db.query(Note)
        .join(CaseNotebook, CaseNotebook.id == Note.notebook_id)
        .options(joinedload(Note.attachments))
        .filter(Note.id == note_id, CaseNotebook.user_id == current_user.id)
        .first()
    )
    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    return note


@router.get("/", response_model=List[CaseNotebookListItem])
def list_notebooks(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(
            CaseNotebook.id.label("notebook_id"),
            CaseNotebook.case_id.label("case_id"),
            Case.case_number.label("case_number"),
            Case.efiling_number.label("efiling_number"),
            Case.case_type.label("case_type"),
            Case.petitioner_name.label("petitioner_name"),
            Case.respondent_name.label("respondent_name"),
            func.count(Note.id).label("note_count"),
            CaseNotebook.updated_at.label("updated_at"),
        )
        .join(Case, Case.id == CaseNotebook.case_id)
        .outerjoin(Note, Note.notebook_id == CaseNotebook.id)
        .filter(CaseNotebook.user_id == current_user.id)
        .group_by(
            CaseNotebook.id,
            CaseNotebook.case_id,
            Case.case_number,
            Case.efiling_number,
            Case.case_type,
            Case.petitioner_name,
            Case.respondent_name,
            CaseNotebook.updated_at,
        )
        .order_by(CaseNotebook.updated_at.desc())
        .all()
    )
    return [CaseNotebookListItem(**row._asdict()) for row in rows]


@router.post("/cases/{case_id}/open", response_model=CaseNotebookResponse)
def open_or_create_notebook(
    case_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ensure_owned_case(case_id, current_user, db)

    notebook = (
        db.query(CaseNotebook)
        .options(joinedload(CaseNotebook.notes).joinedload(Note.attachments))
        .filter(CaseNotebook.case_id == case_id, CaseNotebook.user_id == current_user.id)
        .first()
    )
    if notebook:
        notebook.notes.sort(key=lambda n: n.order_index)
        return notebook

    notebook = CaseNotebook(user_id=current_user.id, case_id=case_id)
    db.add(notebook)
    db.flush()

    starter_note = Note(
        notebook_id=notebook.id,
        title="Chapter 1",
        order_index=1,
        content_json={"type": "doc", "content": [{"type": "paragraph"}]},
        content_text="",
    )
    db.add(starter_note)
    db.commit()

    notebook = _ensure_owned_notebook(notebook.id, current_user, db)
    notebook.notes.sort(key=lambda n: n.order_index)
    return notebook


@router.get("/cases/{case_id}", response_model=CaseNotebookResponse)
def get_notebook_for_case(
    case_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ensure_owned_case(case_id, current_user, db)
    notebook = (
        db.query(CaseNotebook)
        .options(joinedload(CaseNotebook.notes).joinedload(Note.attachments))
        .filter(CaseNotebook.case_id == case_id, CaseNotebook.user_id == current_user.id)
        .first()
    )
    if not notebook:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notebook not found")
    notebook.notes.sort(key=lambda n: n.order_index)
    return notebook


@router.post("/{notebook_id}/notes", response_model=NoteResponse)
def create_note(
    notebook_id: UUID,
    payload: NoteCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    notebook = _ensure_owned_notebook(notebook_id, current_user, db)

    max_order = db.query(func.max(Note.order_index)).filter(Note.notebook_id == notebook.id).scalar() or 0
    order_index = payload.order_index if payload.order_index is not None else int(max_order) + 1

    note = Note(
        notebook_id=notebook.id,
        title=payload.title,
        order_index=order_index,
        content_json=payload.content_json,
        content_text=payload.content_text,
    )
    db.add(note)
    notebook.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(note)
    return note


@router.put("/notes/{note_id}", response_model=NoteResponse)
def update_note(
    note_id: UUID,
    payload: NoteUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    note = _ensure_owned_note(note_id, current_user, db)

    # ── Optimistic concurrency lock ────────────────────────────────────────
    # If the client sends a version, verify it matches. This prevents two tabs
    # from silently overwriting each other's edits.
    if payload.version is not None and note.version != payload.version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "This note was updated in another tab. Reload the latest version before saving.",
                "current_version": note.version,
                "current_record": {
                    "id": str(note.id),
                    "title": note.title,
                    "content_text": note.content_text,
                    "content_json": note.content_json,
                    "version": note.version,
                    "updated_at": note.updated_at.isoformat() if note.updated_at else None,
                },
            },
        )

    if payload.title is not None:
        note.title = payload.title
    if payload.order_index is not None:
        note.order_index = payload.order_index
    if payload.content_json is not None:
        note.content_json = payload.content_json
    if payload.content_text is not None:
        note.content_text = payload.content_text

    note.version = (note.version or 1) + 1
    note.updated_at = datetime.utcnow()
    note.notebook.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(note)
    return note


@router.delete("/notes/{note_id}")
def delete_note(
    note_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    note = _ensure_owned_note(note_id, current_user, db)
    note.notebook.updated_at = datetime.utcnow()
    db.delete(note)
    db.commit()
    return {"success": True, "note_id": str(note_id)}


@router.post("/notes/{note_id}/attachments", response_model=NoteAttachmentResponse)
def create_attachment_metadata(
    note_id: UUID,
    payload: NoteAttachmentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    note = _ensure_owned_note(note_id, current_user, db)
    attachment = NoteAttachment(
        note_id=note.id,
        file_url=payload.file_url,
        ocr_text=payload.ocr_text,
        file_name=payload.file_name,
        content_type=payload.content_type,
        file_size=payload.file_size,
        s3_key=payload.s3_key,
        s3_bucket=payload.s3_bucket,
    )
    db.add(attachment)
    note.notebook.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(attachment)
    return attachment


@router.post("/notes/{note_id}/attachments/upload", response_model=NoteAttachmentResponse)
def upload_attachment(
    note_id: UUID,
    file: UploadFile = File(...),
    ocr_text: str = Form(default=""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    note = _ensure_owned_note(note_id, current_user, db)

    body = file.file.read()
    if not body:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")

    safe_name = os.path.basename(file.filename or "attachment.bin")
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    s3_key = f"notebooks/{current_user.id}/{note.notebook.case_id}/{note.id}/{timestamp}_{safe_name}"

    s3 = S3Service()
    s3.s3_client.put_object(
        Bucket=s3.bucket,
        Key=s3_key,
        Body=body,
        ContentType=file.content_type or "application/octet-stream",
    )

    attachment = NoteAttachment(
        note_id=note.id,
        file_url=f"s3://{s3.bucket}/{s3_key}",
        s3_key=s3_key,
        s3_bucket=s3.bucket,
        file_name=safe_name,
        content_type=file.content_type or "application/octet-stream",
        file_size=len(body),
        ocr_text=ocr_text or None,
    )
    db.add(attachment)
    note.notebook.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(attachment)
    return attachment


@router.get("/notes/{note_id}/attachments/{attachment_id}/view-url")
def get_attachment_view_url(
    note_id: UUID,
    attachment_id: UUID,
    expires_in: int = 1800,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    note = _ensure_owned_note(note_id, current_user, db)
    attachment = (
        db.query(NoteAttachment)
        .filter(NoteAttachment.id == attachment_id, NoteAttachment.note_id == note.id)
        .first()
    )
    if not attachment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")

    if not attachment.s3_key or not attachment.s3_bucket:
        return {"url": attachment.file_url, "expires_in": expires_in}

    s3 = S3Service()
    url = s3.generate_download_url(
        s3_key=attachment.s3_key,
        bucket=attachment.s3_bucket,
        expires_in=expires_in,
    )
    return {"url": url, "expires_in": expires_in}


@router.get("/search", response_model=List[NotebookSearchItem])
def search_notes(
    q: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    term = (q or "").strip()
    if not term:
        return []

    rows = (
        db.query(
            Note.id.label("note_id"),
            Note.notebook_id.label("notebook_id"),
            Case.id.label("case_id"),
            Case.case_number.label("case_number"),
            Case.efiling_number.label("efiling_number"),
            Note.title.label("note_title"),
            func.substr(func.coalesce(Note.content_text, ""), 1, 220).label("snippet"),
            Note.updated_at.label("updated_at"),
        )
        .join(CaseNotebook, CaseNotebook.id == Note.notebook_id)
        .join(Case, Case.id == CaseNotebook.case_id)
        .filter(CaseNotebook.user_id == current_user.id)
        .filter(
            text(
                "to_tsvector('simple', coalesce(notes.title, '') || ' ' || coalesce(notes.content_text, '')) "
                "@@ plainto_tsquery('simple', :term)"
            )
        )
        .params(term=term)
        .order_by(Note.updated_at.desc())
        .limit(50)
        .all()
    )

    return [NotebookSearchItem(**row._asdict()) for row in rows]


@router.post("/notes/{note_id}/send-to-hearing-day")
def send_note_to_hearing_day(
    note_id: UUID,
    payload: SendToHearingDayRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    note = _ensure_owned_note(note_id, current_user, db)
    case_id = note.notebook.case_id

    if payload.mode == "selection":
        selected = (payload.selected_text or "").strip()
        if not selected:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No selected text provided")
        appended_body = selected
    else:
        chapter_text = (note.content_text or "").strip()
        if not chapter_text:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Chapter has no text to send")
        appended_body = chapter_text

    now_iso = datetime.utcnow().isoformat(timespec="seconds")
    prefix = f"[Notebook {note.title} • {payload.mode} • {now_iso}]"
    block = f"{prefix}\n{appended_body}\n"

    hearing_note = (
        db.query(HearingNote)
        .filter(HearingNote.case_id == case_id, HearingNote.user_id == current_user.id)
        .first()
    )
    if not hearing_note:
        hearing_note = HearingNote(
            case_id=case_id,
            user_id=current_user.id,
            content_json=_append_text_to_doc_json(None, block),
            content_text=block,
            version=1,
        )
        db.add(hearing_note)
        db.commit()
        db.refresh(hearing_note)
        return {
            "success": True,
            "mode": payload.mode,
            "hearing_note_id": str(hearing_note.id),
            "version": hearing_note.version,
        }

    existing = hearing_note.content_text or ""
    hearing_note.content_text = f"{existing.rstrip()}\n\n{block}".strip() + "\n"
    hearing_note.content_json = _append_text_to_doc_json(hearing_note.content_json, block)
    hearing_note.version += 1
    db.commit()
    db.refresh(hearing_note)
    return {
        "success": True,
        "mode": payload.mode,
        "hearing_note_id": str(hearing_note.id),
        "version": hearing_note.version,
    }
