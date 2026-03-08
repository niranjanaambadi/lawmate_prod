"""
app/api/v1/endpoints/causelist.py

Endpoints for daily cause list data (parsed PDF rows stored in DB).

Prefix: /api/v1/causelist

Routes
------
GET  /today     → user's tracked cases that appear in today's cause list
GET  /relevant  → user's tracked cases in a date range
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional  # Any kept for _items_for_dates return type
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
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


