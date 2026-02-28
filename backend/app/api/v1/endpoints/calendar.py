"""
api/v1/endpoints/calendar.py

Calendar REST API for the LawMate calendar page.

Endpoints:
  GET    /api/v1/calendar/events              — list events in date range
  POST   /api/v1/calendar/events              — create event
  PATCH  /api/v1/calendar/events/{event_id}   — update event
  DELETE /api/v1/calendar/events/{event_id}   — delete event

  GET    /api/v1/calendar/google/auth-url     — get Google OAuth URL
  POST   /api/v1/calendar/google/callback     — exchange code for tokens
  POST   /api/v1/calendar/google/sync         — trigger incremental sync
  DELETE /api/v1/calendar/google/disconnect   — disconnect Google Calendar
  GET    /api/v1/calendar/google/status       — check connection status
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.db.database import get_db
from app.db.models import CalendarSyncToken, User
from app.services.calendar_service import (
    create_event,
    delete_event,
    get_event_by_id,
    get_events,
    update_event,
)
from app.services.google_calendar_sync_service import (
    disconnect_google_calendar,
    exchange_code_for_tokens,
    get_oauth_url,
    run_incremental_sync,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/calendar", tags=["calendar"])


# ============================================================================
# Request / Response schemas
# ============================================================================

class EventCreateRequest(BaseModel):
    title:          str
    event_type:     str                = Field(default="other")
    start_datetime: datetime
    end_datetime:   Optional[datetime] = None
    all_day:        bool               = False
    case_id:        Optional[str]      = None
    description:    Optional[str]      = None
    location:       Optional[str]      = None


class EventUpdateRequest(BaseModel):
    title:          Optional[str]      = None
    start_datetime: Optional[datetime] = None
    end_datetime:   Optional[datetime] = None
    all_day:        Optional[bool]     = None
    description:    Optional[str]      = None
    location:       Optional[str]      = None


class EventResponse(BaseModel):
    event_id:        str
    title:           str
    event_type:      str
    source:          str
    start_datetime:  str
    end_datetime:    Optional[str]
    all_day:         bool
    location:        Optional[str]
    description:     Optional[str]
    case_id:         Optional[str]
    google_event_id: Optional[str]
    google_synced:   bool
    is_active:       bool


class GoogleCallbackRequest(BaseModel):
    code:  str
    state: str


class SyncStatsResponse(BaseModel):
    created: int
    updated: int
    deleted: int
    errors:  list[str]


# ============================================================================
# Event CRUD
# ============================================================================

@router.get("/events", response_model=list[EventResponse])
async def list_events(
    date_from:    date               = Query(default=None),
    date_to:      date               = Query(default=None),
    case_id:      Optional[str]      = Query(default=None),
    event_type:   Optional[str]      = Query(default=None),
    current_user: User               = Depends(get_current_user),
    db:           Session            = Depends(get_db),
):
    """
    Returns calendar events for the authenticated lawyer.
    Defaults to current month if no date range provided.
    """
    from datetime import timedelta
    from zoneinfo import ZoneInfo

    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()

    if not date_from:
        date_from = today.replace(day=1)
    if not date_to:
        # Last day of current month
        next_month = today.replace(day=28) + timedelta(days=4)
        date_to    = next_month - timedelta(days=next_month.day)

    events = await get_events(
        db=db,
        lawyer_id=str(current_user.id),
        date_from=date_from,
        date_to=date_to,
        case_id=case_id,
        event_type=event_type,
    )

    return [_format_event(e) for e in events]


@router.post("/events", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
async def create_calendar_event(
    req:          EventCreateRequest,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """Creates a calendar event."""
    event = await create_event(
        db=db,
        lawyer_id=str(current_user.id),
        title=req.title,
        event_type=req.event_type,
        start_datetime=req.start_datetime,
        end_datetime=req.end_datetime,
        all_day=req.all_day,
        case_id=req.case_id,
        description=req.description,
        location=req.location,
        source="manual",
    )
    return _format_event(event)


@router.patch("/events/{event_id}", response_model=EventResponse)
async def update_calendar_event(
    event_id:     str,
    req:          EventUpdateRequest,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """Updates a calendar event. Only provided fields are changed."""
    event = await update_event(
        db=db,
        event_id=event_id,
        lawyer_id=str(current_user.id),
        **req.model_dump(exclude_none=True),
    )
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found or access denied",
        )
    return _format_event(event)


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_calendar_event(
    event_id:     str,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """Soft-deletes a calendar event and removes it from Google Calendar."""
    deleted = await delete_event(
        db=db,
        event_id=event_id,
        lawyer_id=str(current_user.id),
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found or access denied",
        )


# ============================================================================
# Google Calendar OAuth + Sync
# ============================================================================

@router.get("/google/auth-url")
async def google_auth_url(
    current_user: User = Depends(get_current_user),
):
    """
    Returns the Google OAuth consent URL.
    Frontend opens this URL (popup or redirect) to let the lawyer connect Google Calendar.
    State = lawyer ID — validated in callback.
    """
    state = str(current_user.id)
    url   = get_oauth_url(state=state)
    return {"auth_url": url}


@router.post("/google/callback")
async def google_oauth_callback(
    req:          GoogleCallbackRequest,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """
    Exchanges OAuth authorization code for tokens.
    Called after Google redirects back with ?code=...&state=...

    Validates that state == current_user.id to prevent CSRF.
    """
    # CSRF check — state must match the authenticated lawyer
    if req.state != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid state parameter",
        )

    try:
        await exchange_code_for_tokens(
            code=req.code,
            lawyer_id=str(current_user.id),
            db=db,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return {"message": "Google Calendar connected successfully"}


@router.post("/google/sync", response_model=SyncStatsResponse)
async def trigger_google_sync(
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """
    Triggers an incremental Google Calendar sync for the authenticated lawyer.
    Safe to call repeatedly — uses sync tokens, not full re-fetch.
    """
    stats = await run_incremental_sync(
        lawyer_id=str(current_user.id),
        db=db,
    )

    if "error" in stats:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=stats["error"],
        )

    return SyncStatsResponse(**stats)


@router.delete("/google/disconnect", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_google(
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """Revokes Google OAuth and removes sync token."""
    await disconnect_google_calendar(
        lawyer_id=str(current_user.id),
        db=db,
    )


@router.get("/google/status")
async def google_connection_status(
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """
    Returns Google Calendar connection status for the lawyer.
    Used by the calendar page to show connect/disconnect button.
    """
    sync_token = db.query(CalendarSyncToken).filter(
        CalendarSyncToken.lawyer_id == current_user.id,
        CalendarSyncToken.is_active == True,
    ).first()

    if not sync_token:
        return {"connected": False}

    return {
        "connected":      True,
        "calendar_id":    sync_token.google_calendar_id,
        "last_synced_at": sync_token.last_synced_at.isoformat() if sync_token.last_synced_at else None,
        "last_sync_error": sync_token.last_sync_error,
    }


# ============================================================================
# Helpers
# ============================================================================

def _format_event(event) -> EventResponse:
    """Converts a CalendarEvent ORM object to EventResponse."""
    return EventResponse(
        event_id=str(event.id),
        title=event.title,
        event_type=event.event_type.value,
        source=event.source.value,
        start_datetime=(
            event.start_datetime.strftime("%Y-%m-%d")
            if event.all_day
            else event.start_datetime.strftime("%Y-%m-%dT%H:%M:%S")
        ),
        end_datetime=(
            event.end_datetime.strftime("%Y-%m-%d")
            if event.end_datetime and event.all_day
            else event.end_datetime.strftime("%Y-%m-%dT%H:%M:%S")
            if event.end_datetime
            else None
        ),
        all_day=event.all_day,
        location=event.location,
        description=event.description,
        case_id=str(event.case_id) if event.case_id else None,
        google_event_id=event.google_event_id,
        google_synced=event.google_event_id is not None,
        is_active=event.is_active,
    )
