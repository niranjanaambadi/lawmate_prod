"""
api/v1/endpoints/advocate_cause_list.py

Endpoints for advocate-wise cause list from hckinfo.keralacourts.in/digicourt.

Endpoints
---------
GET  /advocate-cause-list          → return cached rows for a date (default: tomorrow)
POST /advocate-cause-list/refresh  → trigger a live fetch and return updated rows
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from zoneinfo import ZoneInfo

from app.api.v1.deps import get_current_user
from app.db.database import get_db
from app.db.models import AdvocateCauseList, User
from app.services.advocate_causelist_service import (
    fetch_and_store_advocate_causelist,
    lookup_advocate_code,
)

logger = logging.getLogger(__name__)
router = APIRouter()

IST = ZoneInfo("Asia/Kolkata")


# ── Response schema ───────────────────────────────────────────────────────────

class AdvocateCauseListRow(BaseModel):
    id:                str
    date:              date
    item_no:           Optional[int]
    court_hall:        Optional[str]
    court_hall_number: Optional[int]
    bench:             Optional[str]
    list_type:         Optional[str]
    judge_name:        Optional[str]
    case_no:           Optional[str]
    petitioner:        Optional[str]
    respondent:        Optional[str]
    fetched_at:        Optional[datetime]

    class Config:
        from_attributes = True


class AdvocateCauseListResponse(BaseModel):
    date:          date
    advocate_name: str
    total:         int
    rows:          List[AdvocateCauseListRow]
    from_cache:    bool


# ── Helpers ───────────────────────────────────────────────────────────────────

def _tomorrow_ist() -> date:
    return (datetime.now(IST) + timedelta(days=1)).date()


def _fetch_from_cache(
    db:           Session,
    lawyer_id:    str,
    target_date:  date,
) -> list[AdvocateCauseList]:
    return (
        db.query(AdvocateCauseList)
        .filter(
            AdvocateCauseList.lawyer_id == lawyer_id,
            AdvocateCauseList.date      == target_date,
        )
        .order_by(AdvocateCauseList.item_no)
        .all()
    )


def _assert_profile_complete(user: User) -> None:
    """Raise 422 if the user hasn't set up their digicourt credentials."""
    if not user.khc_advocate_name:
        raise HTTPException(
            status_code=422,
            detail="KHC advocate name not set on your profile. "
                   "Please update your profile to enable cause list fetching.",
        )
    if not user.khc_enrollment_number:
        raise HTTPException(
            status_code=422,
            detail="KHC enrollment number not set on your profile (e.g. K/000671/2018). "
                   "Please update your profile to enable cause list fetching.",
        )
    if not user.khc_advocate_code:
        raise HTTPException(
            status_code=422,
            detail="KHC advocate code (adv_cd) not set on your profile. "
                   "Please update your profile to enable cause list fetching.",
        )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=AdvocateCauseListResponse)
async def get_advocate_cause_list(
    target_date: Optional[date] = Query(
        None,
        description="Date to fetch (YYYY-MM-DD). Defaults to tomorrow (IST).",
    ),
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
):
    """
    Returns the advocate cause list for the given date.
    Serves from DB cache — use /refresh to pull fresh data from hckinfo.
    """
    fetch_date  = target_date or _tomorrow_ist()
    lawyer_id   = str(current_user.id)
    adv_name    = current_user.khc_advocate_name or ""
    enrollment  = current_user.khc_enrollment_number or ""
    db_adv_name = (
        f"{adv_name.strip().upper()}({enrollment.strip()})"
        if enrollment else adv_name.strip().upper()
    )

    rows = _fetch_from_cache(db, lawyer_id, fetch_date)

    return AdvocateCauseListResponse(
        date=fetch_date,
        advocate_name=db_adv_name,
        total=len(rows),
        rows=[AdvocateCauseListRow(
            id=str(r.id),
            date=r.date,
            item_no=r.item_no,
            court_hall=r.court_hall,
            court_hall_number=r.court_hall_number,
            bench=r.bench,
            list_type=r.list_type,
            judge_name=r.judge_name,
            case_no=r.case_no,
            petitioner=r.petitioner,
            respondent=r.respondent,
            fetched_at=r.fetched_at,
        ) for r in rows],
        from_cache=True,
    )


@router.post("/lookup-code")
async def lookup_advocate_code_endpoint(
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
):
    """
    Auto-detects the advocate's numeric adv_cd from hckinfo digicourt
    using their khc_advocate_name and khc_enrollment_number.

    On success, saves the code to the user's profile and returns it.
    Requires khc_advocate_name and khc_enrollment_number to be set.
    """
    if not current_user.khc_advocate_name:
        raise HTTPException(
            status_code=422,
            detail="KHC advocate name not set on your profile.",
        )

    code = await lookup_advocate_code(
        advocate_name=current_user.khc_advocate_name,
        enrollment_number=current_user.khc_enrollment_number or "",
    )

    if not code:
        raise HTTPException(
            status_code=404,
            detail=(
                "Could not find advocate code on hckinfo digicourt. "
                "The site may be down or the name may not match exactly. "
                "Please enter the code manually."
            ),
        )

    # Save it to the user's profile
    current_user.khc_advocate_code = code
    db.add(current_user)
    db.commit()

    logger.info(
        "Auto-detected adv_cd=%s for user %s (%s)",
        code, current_user.id, current_user.khc_advocate_name,
    )
    return {"adv_cd": code, "saved": True}


@router.post("/refresh", response_model=AdvocateCauseListResponse)
async def refresh_advocate_cause_list(
    target_date: Optional[date] = Query(
        None,
        description="Date to fetch (YYYY-MM-DD). Defaults to tomorrow (IST).",
    ),
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
):
    """
    Triggers a live fetch from hckinfo for the given date and upserts into DB.
    Requires khc_advocate_name, khc_enrollment_number, and khc_advocate_code
    to be set on the user's profile.
    """
    _assert_profile_complete(current_user)

    fetch_date = target_date or _tomorrow_ist()
    lawyer_id  = str(current_user.id)
    adv_name   = current_user.khc_advocate_name
    enrollment = current_user.khc_enrollment_number or ""
    adv_code   = current_user.khc_advocate_code or ""
    db_adv_name = (
        f"{adv_name.strip().upper()}({enrollment.strip()})"
        if enrollment else adv_name.strip().upper()
    )

    try:
        rows = await fetch_and_store_advocate_causelist(
            advocate_name=adv_name,
            target_date=fetch_date,
            lawyer_id=lawyer_id,
            db=db,
            enrollment_number=enrollment,
            advocate_code=adv_code,
        )
    except Exception as exc:
        logger.exception(
            "Live fetch failed for user %s on %s: %s", lawyer_id, fetch_date, exc
        )
        raise HTTPException(
            status_code=502,
            detail=f"Could not fetch from hckinfo: {exc}",
        )

    return AdvocateCauseListResponse(
        date=fetch_date,
        advocate_name=db_adv_name,
        total=len(rows),
        rows=[AdvocateCauseListRow(
            id=str(r.id),
            date=r.date,
            item_no=r.item_no,
            court_hall=r.court_hall,
            court_hall_number=r.court_hall_number,
            bench=r.bench,
            list_type=r.list_type,
            judge_name=r.judge_name,
            case_no=r.case_no,
            petitioner=r.petitioner,
            respondent=r.respondent,
            fetched_at=r.fetched_at,
        ) for r in rows],
        from_cache=False,
    )
