"""
Hearing Day: case notes and citations.
All endpoints require auth and case ownership.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Any

from app.db.database import get_db
from app.db.models import Case, Document, User, HearingNote, HearingNoteCitation
from app.db.schemas import (
    HearingNoteResponse,
    HearingNotePut,
    HearingNoteCitationCreate,
    HearingNoteCitationResponse,
    HearingNoteEnrichmentResponse,
    HearingNoteEnrichmentRunResponse,
)
from app.api.deps import get_current_user
from app.core.config import settings
from app.core.logger import logger
from app.services.hearing_note_enrichment_service import hearing_note_enrichment_service

router = APIRouter()


def _hearing_day_enabled() -> bool:
    return getattr(settings, "HEARING_DAY_ENABLED", True)


def _ensure_case_owned(case_id: UUID, user: User, db: Session) -> Case:
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    if case.advocate_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to access this case")
    return case


def _extract_citation_nodes(content_json: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(content_json, dict):
        return []
    out: list[dict[str, Any]] = []
    stack: list[Any] = [content_json]
    while stack:
        node = stack.pop()
        if not isinstance(node, dict):
            continue
        node_type = node.get("type")
        attrs = node.get("attrs")
        if node_type == "citation" and isinstance(attrs, dict):
            out.append(
                {
                    "doc_id": attrs.get("docId"),
                    "page_number": attrs.get("pageNumber"),
                    "quote_text": attrs.get("quoteText"),
                    "bbox_json": attrs.get("bbox"),
                    "anchor_id": attrs.get("anchorId"),
                }
            )
        content = node.get("content")
        if isinstance(content, list):
            stack.extend(content)
    return out


def _sync_citations_from_note_json(
    db: Session,
    *,
    hearing_note_id: UUID,
    case_id: UUID,
    content_json: dict[str, Any] | None,
) -> None:
    extracted = _extract_citation_nodes(content_json)
    db.query(HearingNoteCitation).filter(HearingNoteCitation.hearing_note_id == hearing_note_id).delete()
    if not extracted:
        return

    valid_doc_ids = {
        str(d.id)
        for d in db.query(Document.id).filter(Document.case_id == case_id).all()
    }
    for c in extracted:
        doc_id = c.get("doc_id")
        page_number = c.get("page_number")
        if not doc_id or str(doc_id) not in valid_doc_ids:
            continue
        try:
            page_number_int = int(page_number)
        except (TypeError, ValueError):
            continue
        if page_number_int < 1:
            continue
        db.add(
            HearingNoteCitation(
                hearing_note_id=hearing_note_id,
                doc_id=doc_id,
                page_number=page_number_int,
                quote_text=(c.get("quote_text") or None),
                bbox_json=(c.get("bbox_json") if isinstance(c.get("bbox_json"), dict) else None),
                anchor_id=(c.get("anchor_id") or None),
            )
        )


@router.get("/{case_id}/note", response_model=HearingNoteResponse)
def get_hearing_note(
    case_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get hearing note for case for current user. Returns 404 if none."""
    if not _hearing_day_enabled():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feature not available")
    _ensure_case_owned(case_id, current_user, db)
    note = (
        db.query(HearingNote)
        .filter(HearingNote.case_id == case_id, HearingNote.user_id == current_user.id)
        .first()
    )
    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No hearing note found")
    return note


@router.put("/{case_id}/note", response_model=HearingNoteResponse)
def put_hearing_note(
    case_id: UUID,
    payload: HearingNotePut,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create or update hearing note. Optimistic lock: version must match current."""
    if not _hearing_day_enabled():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feature not available")
    case = _ensure_case_owned(case_id, current_user, db)
    note = (
        db.query(HearingNote)
        .filter(HearingNote.case_id == case_id, HearingNote.user_id == current_user.id)
        .first()
    )
    if note:
        if note.version != payload.version:
            logger.warning(
                "Hearing note version conflict case=%s user=%s client_v=%s server_v=%s",
                case_id, current_user.id, payload.version, note.version,
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "This note was updated in another tab. Reload the latest version before saving.",
                    "current_version": note.version,
                    "current_record": {
                        "id": str(note.id),
                        "content_text": note.content_text,
                        "content_json": note.content_json,
                        "version": note.version,
                        "updated_at": note.updated_at.isoformat() if note.updated_at else None,
                    },
                },
            )
        note.content_json = payload.content_json
        note.content_text = payload.content_text
        note.version += 1
        _sync_citations_from_note_json(
            db,
            hearing_note_id=note.id,
            case_id=case.id,
            content_json=payload.content_json,
        )
        db.commit()
        db.refresh(note)
        return note
    note = HearingNote(
        case_id=case_id,
        user_id=current_user.id,
        content_json=payload.content_json,
        content_text=payload.content_text,
        version=payload.version,
    )
    db.add(note)
    db.flush()
    _sync_citations_from_note_json(
        db,
        hearing_note_id=note.id,
        case_id=case.id,
        content_json=payload.content_json,
    )
    db.commit()
    db.refresh(note)
    return note


@router.post("/{case_id}/citations", response_model=HearingNoteCitationResponse)
def create_citation(
    case_id: UUID,
    payload: HearingNoteCitationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Add a citation to the hearing note. Note must belong to this case and user."""
    if not _hearing_day_enabled():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feature not available")
    _ensure_case_owned(case_id, current_user, db)
    note = (
        db.query(HearingNote)
        .filter(HearingNote.id == payload.hearing_note_id, HearingNote.case_id == case_id, HearingNote.user_id == current_user.id)
        .first()
    )
    if not note:
        logger.warning("Citation create failed: note not found", extra={"case_id": str(case_id), "hearing_note_id": str(payload.hearing_note_id)})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hearing note not found")
    doc = db.query(Document).filter(Document.id == payload.doc_id).first()
    if not doc or doc.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Document not found or not in this case")
    citation = HearingNoteCitation(
        hearing_note_id=payload.hearing_note_id,
        doc_id=payload.doc_id,
        page_number=payload.page_number,
        quote_text=payload.quote_text,
        bbox_json=payload.bbox_json,
        anchor_id=payload.anchor_id,
    )
    db.add(citation)
    db.commit()
    db.refresh(citation)
    return citation


@router.get("/{case_id}/citations")
def get_hearing_citations(
    case_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all citations for the hearing note of this case for current user."""
    if not _hearing_day_enabled():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feature not available")
    _ensure_case_owned(case_id, current_user, db)
    note = (
        db.query(HearingNote)
        .filter(HearingNote.case_id == case_id, HearingNote.user_id == current_user.id)
        .first()
    )
    if not note:
        return {"data": [], "items": []}
    citations = db.query(HearingNoteCitation).filter(HearingNoteCitation.hearing_note_id == note.id).all()
    return {"data": citations, "items": citations}


@router.post("/{case_id}/enrich", response_model=HearingNoteEnrichmentRunResponse)
def enrich_hearing_note(
    case_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not _hearing_day_enabled():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feature not available")
    _ensure_case_owned(case_id, current_user, db)
    try:
        enrichment, from_cache, deterministic_only = hearing_note_enrichment_service.enrich_case_note(
            str(case_id), current_user, db
        )
        return {
            "success": True,
            "from_cache": from_cache,
            "deterministic_only": deterministic_only,
            "enrichment": enrichment,
        }
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.exception("Hearing note enrichment failed for case=%s", case_id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Enrichment failed: {exc}")


@router.get("/{case_id}/enrichment", response_model=HearingNoteEnrichmentResponse)
def get_latest_hearing_note_enrichment(
    case_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not _hearing_day_enabled():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feature not available")
    _ensure_case_owned(case_id, current_user, db)
    enrichment = hearing_note_enrichment_service.get_latest_for_case(str(case_id), current_user, db)
    if not enrichment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No enrichment found")
    return enrichment
