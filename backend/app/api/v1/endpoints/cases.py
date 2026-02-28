"""
Case management endpoints
"""
from fastapi import APIRouter, HTTPException, Depends, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, extract
from typing import List, Optional
from datetime import datetime, timedelta
from uuid import UUID
import re

from app.db.database import get_db
from app.db.models import Case, TrackedCase, User, Document, AIAnalysis, CaseHistory, CaseStatus
from app.db.schemas import (
    CaseResponse,
    CaseCreate,
    CaseUpdate,
    PendingCaseStatusResponse,
    TrackedCaseStatusResponse,
    CaseStatusLookupRequest,
    CaseStatusLookupResponse,
    AddCaseToDashboardRequest,
    AddCaseToDashboardResponse,
    CaseDetailResponse,
    DocumentResponse,
    CaseHistoryResponse,
    AIAnalysisResponse
)
from app.api.deps import get_current_user
from app.services.case_sync_service import case_sync_service

router = APIRouter()

# ============================================================================
# List & Filter Endpoints
# ============================================================================

@router.get("/")
def get_cases(
    status: Optional[str] = Query(None, description="Filter by status"),
    case_type: Optional[str] = Query(None, description="Filter by case type"),
    case_year: Optional[int] = Query(None, description="Filter by year"),
    party_role: Optional[str] = Query(None, description="Filter by party role"),
    q: Optional[str] = Query(None, description="Search query (preferred)"),
    search: Optional[str] = Query(None, description="Search query (legacy)"),
    sort_by: str = Query("next_hearing_date", description="Sort field (preferred)"),
    sort_dir: str = Query("asc", description="Sort direction (asc/desc, preferred)"),
    sort: Optional[str] = Query(None, description="Sort field (legacy)"),
    order: Optional[str] = Query(None, description="Sort order (legacy asc/desc)"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all cases for the authenticated user with filters
    """
    # Build base query
    query = db.query(Case).filter(
        Case.advocate_id == current_user.id,
        Case.is_visible == True
    )
    
    # Apply filters
    if status and status != "all":
        query = query.filter(Case.status == status)
    
    if case_type:
        query = query.filter(Case.case_type == case_type)
    
    if case_year:
        query = query.filter(Case.case_year == case_year)

    if party_role and party_role != "all":
        query = query.filter(Case.party_role == party_role)
    
    # Search
    search_value = q if q is not None else search
    if search_value:
        search_term = f"%{search_value}%"
        query = query.filter(
            or_(
                Case.case_number.ilike(search_term),
                Case.efiling_number.ilike(search_term),
                Case.petitioner_name.ilike(search_term),
                Case.respondent_name.ilike(search_term)
            )
        )
    
    # Sorting (preferred params, with legacy fallback)
    effective_sort = sort if sort else sort_by
    effective_order = order if order else sort_dir
    sortable_columns = {
        "updated_at": Case.updated_at,
        "created_at": Case.created_at,
        "next_hearing_date": Case.next_hearing_date,
        "last_synced_at": Case.last_synced_at,
        "case_number": Case.case_number,
        "efiling_number": Case.efiling_number,
        "status": Case.status,
        "case_type": Case.case_type,
    }
    sort_column = sortable_columns.get(effective_sort, Case.next_hearing_date)
    order_dir = (effective_order or "").lower()

    if effective_sort == "next_hearing_date":
        # Default UX: earliest upcoming hearings first, null dates last, then most recently updated.
        if order_dir == "desc":
            query = query.order_by(sort_column.desc().nullslast(), Case.updated_at.desc())
        else:
            query = query.order_by(sort_column.asc().nullslast(), Case.updated_at.desc())
    else:
        if order_dir == "desc":
            query = query.order_by(sort_column.desc(), Case.updated_at.desc())
        else:
            query = query.order_by(sort_column.asc(), Case.updated_at.desc())
    
    # Total count for pagination
    total = query.count()
    total_pages = max(1, (total + per_page - 1) // per_page)
    skip = (page - 1) * per_page
    cases = query.offset(skip).limit(per_page).all()

    # Webapp expects raw body: items or cases, total, page, per_page, total_pages
    return {
        "items": cases,
        "cases": cases,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
    }


@router.get("/search")
def search_cases(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Search cases by case number, e-filing number, party names.
    """
    search_term = f"%{q}%"
    cases = db.query(Case).filter(
        Case.advocate_id == current_user.id,
        Case.is_visible == True,
        or_(
            Case.case_number.ilike(search_term),
            Case.efiling_number.ilike(search_term),
            Case.petitioner_name.ilike(search_term),
            Case.respondent_name.ilike(search_term)
        )
    ).limit(limit).all()
    return {"cases": cases, "items": cases}


# ============================================================================
# Upcoming Hearings & Stats (must be before /{case_id})
# ============================================================================

@router.get("/upcoming-hearings")
def get_upcoming_hearings(
    days: int = Query(7, ge=1, le=90, description="Days to look ahead"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    now = datetime.now()
    future = now + timedelta(days=days)
    cases = db.query(Case).filter(
        Case.advocate_id == current_user.id,
        Case.is_visible == True,
        Case.next_hearing_date.isnot(None),
        Case.next_hearing_date.between(now, future)
    ).order_by(Case.next_hearing_date.asc()).all()
    return {"cases": cases}


@router.get("/stats")
def get_case_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    total_cases = db.query(Case).filter(
        Case.advocate_id == current_user.id,
        Case.is_visible == True
    ).count()
    pending_cases = db.query(Case).filter(
        Case.advocate_id == current_user.id,
        Case.status == CaseStatus.pending,
        Case.is_visible == True
    ).count()
    disposed_cases = db.query(Case).filter(
        Case.advocate_id == current_user.id,
        Case.status == CaseStatus.disposed,
        Case.is_visible == True
    ).count()
    now = datetime.now()
    upcoming = db.query(Case).filter(
        Case.advocate_id == current_user.id,
        Case.next_hearing_date.between(now, now + timedelta(days=7))
    ).count()
    cases_by_status = db.query(
        Case.status,
        func.count(Case.id)
    ).filter(
        Case.advocate_id == current_user.id,
        Case.is_visible == True
    ).group_by(Case.status).all()
    cases_by_type = db.query(
        Case.case_type,
        func.count(Case.id)
    ).filter(
        Case.advocate_id == current_user.id,
        Case.is_visible == True
    ).group_by(Case.case_type).all()
    six_months_ago = now - timedelta(days=180)
    monthly = db.query(
        extract("year", Case.created_at).label("year"),
        extract("month", Case.created_at).label("month"),
        func.count(Case.id).label("count")
    ).filter(
        Case.advocate_id == current_user.id,
        Case.created_at >= six_months_ago
    ).group_by("year", "month").order_by("year", "month").all()
    monthly_trend = [{"month": datetime(int(y), int(m), 1).strftime("%b"), "count": c} for y, m, c in monthly]
    return {
        "total_cases": total_cases,
        "pending_cases": pending_cases,
        "disposed_cases": disposed_cases,
        "upcoming_hearings": upcoming,
        "cases_by_status": {getattr(s, "value", s): c for s, c in cases_by_status},
        "cases_by_type": {t: c for t, c in cases_by_type},
        "monthly_trend": monthly_trend,
    }



def _first_val(row: dict, keys: list):
    """Return the first non-empty value found among the given keys in a dict."""
    for k in keys:
        v = row.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return None


@router.get("/pending-status", response_model=List[PendingCaseStatusResponse])
def get_pending_status_rows(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(Case)
        .filter(
            Case.advocate_id == current_user.id,
            Case.is_visible == True,
            Case.status == CaseStatus.pending,
            Case.case_number.isnot(None),
            Case.case_number != "",
        )
        .order_by(Case.next_hearing_date.asc().nullslast(), Case.updated_at.desc())
        .all()
    )

    result = []
    for c in rows:
        # Extract latest hearing history row from raw_court_data
        raw = c.raw_court_data if isinstance(c.raw_court_data, dict) else {}
        history = raw.get("hearing_history") or []
        last_row = history[-1] if history else {}

        result.append({
            "id": c.id,
            "case_number": c.case_number or "",
            "status_text": c.court_status or getattr(c.status, "value", c.status),
            "stage": c.bench_type or "",
            "last_order_date": c.last_synced_at,
            "next_hearing_date": c.next_hearing_date,
            "source_url": c.khc_source_url,
            "fetched_at": c.last_synced_at or c.updated_at,
            "updated_at": c.updated_at,
            # Latest hearing row fields
            "business_date": _first_val(last_row, ["business_date", "posting_date", "listed_on", "date"]),
            "tentative_date": _first_val(last_row, ["next_date", "tentative_date", "next_hearing_date"]),
            "purpose_of_hearing": _first_val(last_row, ["purpose_of_hearing", "purpose", "stage"]),
            "order_text": _first_val(last_row, ["order", "order_text", "remarks"]),
            "judge_name": _first_val(last_row, ["hon_judge_name", "judge_name", "judge", "bench", "coram"]),
        })
    return result


@router.get("/tracked-status", response_model=List[TrackedCaseStatusResponse])
def get_tracked_status_rows(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(TrackedCase)
        .filter(
            TrackedCase.user_id == current_user.id,
            TrackedCase.is_visible == True,
        )
        .order_by(TrackedCase.updated_at.desc())
        .all()
    )
    return [
        {
            "id": r.id,
            "case_number": r.case_number or "",
            "status_text": r.status_text,
            "stage": r.stage,
            "last_order_date": r.last_order_date,
            "next_hearing_date": r.next_hearing_date,
            "source_url": r.source_url,
            "full_details_url": r.full_details_url,
            "fetched_at": r.fetched_at,
            "updated_at": r.updated_at,
        }
        for r in rows
    ]


@router.post("/case-status/query", response_model=CaseStatusLookupResponse)
def query_case_status(
    payload: CaseStatusLookupRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return case_sync_service.query_case_status(payload.case_number)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Case status lookup failed: {exc}")


def _build_case_number_for_lookup(case: Case) -> Optional[str]:
    case_type = (case.case_type or "").strip()
    case_year = str(case.case_year or "").strip()
    raw_case_no = (case.case_number or "").strip()
    if not case_type or not re.fullmatch(r"\d{4}", case_year):
        return None
    m = re.search(r"(\d+)\s*/\s*\d{4}\s*$", raw_case_no)
    case_no = m.group(1).strip() if m else ""
    if not case_no:
        first_num = re.search(r"\d+", raw_case_no)
        case_no = first_num.group(0).strip() if first_num else ""
    if not case_no:
        return None
    return f"{case_type} {case_no}/{case_year}"


def _json_safe(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


@router.post("/{case_id}/case-status/refresh", response_model=CaseStatusLookupResponse)
def refresh_case_status_for_case(
    case_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    if case.advocate_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to access this case")

    case_number = _build_case_number_for_lookup(case)
    if not case_number:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Case details incomplete for refresh. Need case type, case number and year.",
        )

    try:
        result = case_sync_service.query_case_status(case_number)
        if not result.get("found"):
            return result

        now = datetime.utcnow()
        case.court_status = result.get("status_text") or case.court_status
        case.bench_type = result.get("stage") or case.bench_type
        case.judge_name = result.get("coram") or case.judge_name
        if result.get("next_hearing_date"):
            case.next_hearing_date = result.get("next_hearing_date")
        case.khc_source_url = result.get("full_details_url") or result.get("source_url") or case.khc_source_url
        case.last_synced_at = now
        case.sync_status = "synced"
        case.sync_error = None
        if result.get("petitioner_name"):
            case.petitioner_name = result.get("petitioner_name")
        if result.get("respondent_name"):
            case.respondent_name = result.get("respondent_name")
        case.raw_court_data = _json_safe(result)

        db.commit()
        return result
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Case status lookup failed: {exc}")


@router.post("/case-status/add-to-dashboard", response_model=AddCaseToDashboardResponse)
def add_case_to_dashboard(
    payload: AddCaseToDashboardRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return case_sync_service.add_case_to_dashboard(
            db=db,
            user=current_user,
            case_number=payload.case_number,
            petitioner_name=payload.petitioner_name,
            respondent_name=payload.respondent_name,
            status_text=payload.status_text,
            stage=payload.stage,
            last_order_date=payload.last_order_date,
            next_hearing_date=payload.next_hearing_date,
            source_url=payload.source_url,
            full_details_url=payload.full_details_url,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


# ============================================================================
# Single Case Endpoints
# ============================================================================

@router.get("/{case_id}/documents")
def get_case_documents(
    case_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get documents for a case. Requires case ownership."""
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    if case.advocate_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to access this case")
    documents = db.query(Document).filter(Document.case_id == case_id).order_by(Document.created_at.desc()).all()
    return {"data": documents, "items": documents}


@router.get("/{case_id}")
def get_case(
    case_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get case details with documents, history, and AI analysis
    """
    case = db.query(Case).filter(Case.id == case_id).first()
    
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found"
        )
    
    # Verify ownership
    if case.advocate_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this case"
        )
    
    # Get related data
    documents = db.query(Document).filter(
        Document.case_id == case_id
    ).all()
    
    history = db.query(CaseHistory).filter(
        CaseHistory.case_id == case_id
    ).order_by(CaseHistory.event_date.desc()).all()
    
    ai_analysis = db.query(AIAnalysis).filter(
        AIAnalysis.case_id == case_id
    ).first()
    
    # Build response (snake_case for frontend transformCase)
    def _serialize_obj(obj):
        if obj is None:
            return None
        return {
            k: (v.isoformat() if hasattr(v, "isoformat") and callable(getattr(v, "isoformat")) else (getattr(v, "value", v) if hasattr(v, "value") else v))
            for k, v in obj.__dict__.items() if not k.startswith("_")
        }
    return {
        "id": str(case.id),
        "advocate_id": str(case.advocate_id),
        "case_number": case.case_number,
        "efiling_number": case.efiling_number,
        "case_type": case.case_type,
        "case_year": case.case_year,
        "party_role": getattr(case.party_role, "value", case.party_role),
        "petitioner_name": case.petitioner_name,
        "respondent_name": case.respondent_name,
        "efiling_date": case.efiling_date,
        "efiling_details": case.efiling_details,
        "bench_type": case.bench_type,
        "judge_name": case.judge_name,
        "court_number": case.court_number,
        "status": getattr(case.status, "value", case.status),
        "next_hearing_date": case.next_hearing_date,
        "cnr_number": (
            case.raw_court_data.get("cnr_number")
            if isinstance(case.raw_court_data, dict)
            else None
        ),
        "khc_source_url": case.khc_source_url,
        "last_synced_at": case.last_synced_at,
        "sync_status": case.sync_status,
        "court_status": case.court_status,
        "is_visible": case.is_visible,
        "transferred_reason": case.transferred_reason,
        "transferred_at": case.transferred_at,
        "created_at": case.created_at,
        "updated_at": case.updated_at,
        "hearing_history": (
            case.raw_court_data.get("hearing_history")
            if isinstance(case.raw_court_data, dict)
            else None
        ),
        "first_hearing_date": (
            case.raw_court_data.get("first_hearing_date")
            if isinstance(case.raw_court_data, dict)
            else None
        ),
        "last_order_date": (
            case.raw_court_data.get("last_order_date")
            if isinstance(case.raw_court_data, dict)
            else None
        ),
        "documents": [_serialize_obj(doc) for doc in documents],
        "history": [_serialize_obj(h) for h in history],
        "ai_analysis": _serialize_obj(ai_analysis),
    }


@router.patch("/{case_id}")
def update_case(
    case_id: UUID,
    update_data: CaseUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update case details
    """
    case = db.query(Case).filter(Case.id == case_id).first()
    
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found"
        )
    
    if case.advocate_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to modify this case"
        )
    
    # Update fields
    for field, value in update_data.dict(exclude_unset=True).items():
        setattr(case, field, value)
    
    case.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(case)
    
    return case


@router.delete("/{case_id}")
def delete_case(
    case_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Soft delete a case (sets is_visible=False)
    """
    case = db.query(Case).filter(Case.id == case_id).first()
    
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found"
        )
    
    if case.advocate_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this case"
        )
    
    # Soft delete
    case.is_visible = False
    case.updated_at = datetime.utcnow()
    db.commit()
    
    return {
        "message": "Case deleted successfully",
        "case_id": str(case_id)
    }


@router.get("/recycle-bin/items")
def get_deleted_cases(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = (
        db.query(Case)
        .filter(
            Case.advocate_id == current_user.id,
            Case.is_visible == False,
        )
        .order_by(Case.updated_at.desc())
    )

    total = query.count()
    total_pages = max(1, (total + per_page - 1) // per_page)
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
    }


@router.post("/{case_id}/restore")
def restore_case(
    case_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found"
        )

    if case.advocate_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to restore this case"
        )

    case.is_visible = True
    case.updated_at = datetime.utcnow()
    db.commit()
    return {
        "message": "Case restored successfully",
        "case_id": str(case_id)
    }
