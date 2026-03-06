"""
app/api/v1/endpoints/causelist.py

Endpoints for daily cause list data (parsed PDF rows stored in DB).

Prefix: /api/v1/causelist

Routes
------
GET  /today              → user's cases listed today
GET  /relevant           → user's cases in a date range
GET  /rendered-html      → HTML render for a date (existing cause_list_store)
GET  /all                → all parsed rows for a date
POST /sync               → trigger PDF fetch + parse pipeline
GET  /mine-by-advocate   → rows matching user's advocate name
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.db.database import get_db
from app.db.models import (
    Case,
    CauseList,
    CauseListCaseItem,
    CauseListSource,
    User,
)

router = APIRouter()
IST = ZoneInfo("Asia/Kolkata")


# ── Response models ───────────────────────────────────────────────────────────

class CauseListRelevantItem(BaseModel):
    case_id: str
    case_number: Optional[str]
    efiling_number: str
    case_type: str
    party_role: str
    petitioner_name: str
    respondent_name: str
    listing_date: str
    source: str
    color: str
    court_number: Optional[str] = None
    bench_name: Optional[str] = None
    item_no: Optional[str] = None


class CauseListDayGroup(BaseModel):
    date: str
    items: List[CauseListRelevantItem]


class CauseListRelevantResponse(BaseModel):
    from_date: str
    to_date: str
    total: int
    days: List[CauseListDayGroup]


class CauseListAllItem(BaseModel):
    id: str
    case_number: str
    listing_date: str
    source: str
    cause_list_type: Optional[str] = None
    court_number: Optional[str] = None
    bench_name: Optional[str] = None
    item_no: Optional[str] = None
    party_names: Optional[str] = None
    petitioner_name: Optional[str] = None
    respondent_name: Optional[str] = None
    advocate_names: Optional[str] = None
    fetched_from_url: Optional[str] = None


class CauseListAllResponse(BaseModel):
    listing_date: str
    source: str
    total: int
    items: List[CauseListAllItem]


class CauseListRenderedHtmlResponse(BaseModel):
    listing_date: str
    source: str
    total: int
    html: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _today_ist() -> date:
    return datetime.now(IST).date()


def _parse_date(value: Optional[str]) -> date:
    if not value:
        return _today_ist()
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(400, f"Invalid date format '{value}'. Use YYYY-MM-DD.")


def _source_enum(source: Optional[str]) -> Optional[CauseListSource]:
    if not source:
        return None
    try:
        return CauseListSource(source)
    except ValueError:
        return None


def _first_str(names: Any) -> str:
    """Return first element of a JSONB list field as string, or ''."""
    if isinstance(names, list) and names:
        v = names[0]
        return v if isinstance(v, str) else str(v)
    return ""


def _cl_source_str(cl: CauseList) -> str:
    v = cl.source
    return v.value if hasattr(v, "value") else str(v)


def _items_for_dates(
    db: Session,
    from_date: date,
    to_date: date,
    source: Optional[str],
) -> List[Any]:
    """Return (CauseListCaseItem, CauseList) pairs for a date range."""
    q = (
        db.query(CauseListCaseItem, CauseList)
        .join(CauseList, CauseListCaseItem.cause_list_id == CauseList.id)
        .filter(
            CauseList.listing_date >= from_date,
            CauseList.listing_date <= to_date,
        )
    )
    src = _source_enum(source)
    if src:
        q = q.filter(CauseList.source == src)
    return q.all()


def _match_case(item: CauseListCaseItem, case: Case) -> bool:
    """True if a cause list item corresponds to the given tracked case."""
    # Method 1: structured fields (case_type + year + number)
    if item.case_type and item.case_year and item.case_number and case.case_type and case.case_year:
        if (
            item.case_type.upper() == (case.case_type or "").upper()
            and item.case_year == case.case_year
        ):
            # Extract numeric part from case.case_number e.g. "WP(C) 1234/2024" → "1234"
            m = re.search(r"(\d+)\s*/\s*\d{4}", case.case_number or "")
            if m and item.case_number == m.group(1):
                return True

    # Method 2: normalised string comparison (fallback)
    norm_item = re.sub(r"[\s()/]", "", (item.normalized_case_number or "").upper())
    norm_case = re.sub(r"[\s()/]", "", (case.case_number or "").upper())
    if norm_item and norm_case and len(norm_item) > 3 and len(norm_case) > 3:
        if norm_item == norm_case or norm_item in norm_case or norm_case in norm_item:
            return True

    return False


def _build_relevant_item(
    item: CauseListCaseItem,
    cl: CauseList,
    case: Case,
) -> CauseListRelevantItem:
    petitioner = _first_str(item.petitioner_names) or case.petitioner_name or ""
    respondent = _first_str(item.respondent_names) or case.respondent_name or ""

    # Determine party role: if the user's petitioner name matches the item, role = Petitioner
    adv_name_upper = ""  # not available here — default to Petitioner
    party_role = "Petitioner"

    today = _today_ist()
    if cl.listing_date == today:
        color = "green"
    elif cl.listing_date > today:
        color = "yellow"
    else:
        color = "blue"

    return CauseListRelevantItem(
        case_id=str(case.id),
        case_number=case.case_number,
        efiling_number=item.item_no or "",
        case_type=item.case_type or case.case_type or "",
        party_role=party_role,
        petitioner_name=petitioner,
        respondent_name=respondent,
        listing_date=cl.listing_date.isoformat(),
        source=_cl_source_str(cl),
        color=color,
        court_number=cl.court_number,
        bench_name=cl.bench_name,
        item_no=item.item_no,
    )


def _build_relevant_response(
    matched: List[CauseListRelevantItem],
    from_date: date,
    to_date: date,
) -> CauseListRelevantResponse:
    by_date: Dict[str, List[CauseListRelevantItem]] = {}
    for r in matched:
        by_date.setdefault(r.listing_date, []).append(r)
    days = [
        CauseListDayGroup(date=d, items=items)
        for d, items in sorted(by_date.items())
    ]
    return CauseListRelevantResponse(
        from_date=from_date.isoformat(),
        to_date=to_date.isoformat(),
        total=len(matched),
        days=days,
    )


def _all_items_response(
    pairs: List[Any],
    listing_date: date,
    source: Optional[str],
) -> CauseListAllResponse:
    items = [
        CauseListAllItem(
            id=str(item.id),
            case_number=item.normalized_case_number or item.case_number_raw or "",
            listing_date=cl.listing_date.isoformat(),
            source=_cl_source_str(cl),
            cause_list_type=cl.cause_list_type,
            court_number=cl.court_number,
            bench_name=cl.bench_name,
            item_no=item.item_no,
            party_names=item.party_names,
            petitioner_name=_first_str(item.petitioner_names) or None,
            respondent_name=_first_str(item.respondent_names) or None,
        )
        for item, cl in pairs
    ]
    return CauseListAllResponse(
        listing_date=listing_date.isoformat(),
        source=source or "daily",
        total=len(items),
        items=items,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/today", response_model=CauseListRelevantResponse)
def get_today_at_court(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns today's cause list entries that match the user's tracked cases.
    """
    today = _today_ist()

    user_cases = (
        db.query(Case)
        .filter(
            Case.advocate_id == current_user.id,
            Case.is_visible == True,
            Case.case_number.isnot(None),
        )
        .all()
    )

    if not user_cases:
        return CauseListRelevantResponse(
            from_date=today.isoformat(),
            to_date=today.isoformat(),
            total=0,
            days=[],
        )

    pairs = _items_for_dates(db, today, today, "daily")

    matched: List[CauseListRelevantItem] = []
    seen: set = set()
    for item, cl in pairs:
        for case in user_cases:
            if _match_case(item, case):
                key = (str(item.id), str(case.id))
                if key not in seen:
                    seen.add(key)
                    matched.append(_build_relevant_item(item, cl, case))
                break

    return _build_relevant_response(matched, today, today)


@router.get("/relevant", response_model=CauseListRelevantResponse)
def get_relevant_cause_list(
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns cause list entries in a date range that match the user's tracked cases.
    """
    today = _today_ist()
    fd = _parse_date(from_date) if from_date else today
    td = _parse_date(to_date) if to_date else today + timedelta(days=7)

    user_cases = (
        db.query(Case)
        .filter(
            Case.advocate_id == current_user.id,
            Case.is_visible == True,
            Case.case_number.isnot(None),
        )
        .all()
    )

    if not user_cases:
        return CauseListRelevantResponse(
            from_date=fd.isoformat(), to_date=td.isoformat(), total=0, days=[]
        )

    pairs = _items_for_dates(db, fd, td, source)

    matched: List[CauseListRelevantItem] = []
    seen: set = set()
    for item, cl in pairs:
        for case in user_cases:
            if _match_case(item, case):
                key = (str(item.id), str(case.id))
                if key not in seen:
                    seen.add(key)
                    matched.append(_build_relevant_item(item, cl, case))
                break

    return _build_relevant_response(matched, fd, td)


@router.get("/rendered-html", response_model=CauseListRenderedHtmlResponse)
def get_rendered_html(
    listing_date: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns the rendered HTML cause list for the given date (uses stored result_json).
    """
    from app.services.cause_list_renderer import cause_list_renderer
    from app.services.cause_list_store import cause_list_store

    ld = _parse_date(listing_date)

    row = cause_list_store.fetch_result(
        db, advocate_id=str(current_user.id), listing_date=ld
    )

    if not row:
        return CauseListRenderedHtmlResponse(
            listing_date=ld.isoformat(),
            source=source or "daily",
            total=0,
            html=cause_list_renderer.render_empty(ld.isoformat()),
        )

    result_json = row.result_json if isinstance(row.result_json, dict) else {}
    html = cause_list_renderer.render(result_json)

    return CauseListRenderedHtmlResponse(
        listing_date=ld.isoformat(),
        source=source or "daily",
        total=int(row.total_listings or 0),
        html=html,
    )


@router.get("/all", response_model=CauseListAllResponse)
def get_all_cause_list(
    listing_date: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns all parsed cause list rows for a given date.
    """
    ld = _parse_date(listing_date)

    q = (
        db.query(CauseListCaseItem, CauseList)
        .join(CauseList, CauseListCaseItem.cause_list_id == CauseList.id)
        .filter(CauseList.listing_date == ld)
    )
    src = _source_enum(source)
    if src:
        q = q.filter(CauseList.source == src)
    pairs = q.all()

    return _all_items_response(pairs, ld, source)


@router.post("/sync")
async def sync_cause_list(
    source: str = Query("daily"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user: User = Depends(get_current_user),
):
    """
    Triggers the daily cause list PDF fetch + parse pipeline in the background.
    Returns immediately.
    """
    from app.api.cause_list import _run_process_job

    listing_date = _today_ist()
    background_tasks.add_task(_run_process_job, listing_date)

    return [
        {
            "source": source,
            "fetched": 0,
            "runs": 0,
            "inserted": 0,
            "updated": 0,
            "failed_runs": 0,
            "listing_dates": [listing_date.isoformat()],
        }
    ]


@router.get("/mine-by-advocate", response_model=CauseListAllResponse)
def get_mine_by_advocate(
    listing_date: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns cause list items where the user's advocate name appears in the raw data.
    """
    ld = _parse_date(listing_date)
    adv_name = (current_user.khc_advocate_name or "").strip().upper()

    q = (
        db.query(CauseListCaseItem, CauseList)
        .join(CauseList, CauseListCaseItem.cause_list_id == CauseList.id)
        .filter(CauseList.listing_date == ld)
    )
    src = _source_enum(source)
    if src:
        q = q.filter(CauseList.source == src)
    pairs = q.all()

    if not adv_name:
        return _all_items_response(pairs, ld, source)

    filtered = []
    for item, cl in pairs:
        raw = item.raw_data or {}
        advocates_raw = str(raw.get("advocates", "") or "").upper()
        party_raw = (item.party_names or "").upper()
        if adv_name in advocates_raw or adv_name in party_raw:
            filtered.append((item, cl))

    return _all_items_response(filtered, ld, source)
