"""
services/calendar_service.py

Calendar CRUD operations for the LawMate agent.

Called by:
  - agent/tools/calendar.py  (CreateCalendarEventTool, GetCalendarEventsTool, DeleteCalendarEventTool)
  - api/v1/endpoints/calendar.py (REST API for the calendar page)
  - background jobs (auto-populate from case sync, cause list sync)

All writes trigger Google Calendar sync if the lawyer has connected their account.
Sync is fire-and-forget — calendar operations never fail because of Google.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import (
    CalendarEvent,
    CalendarEventSource,
    CalendarEventType,
    CalendarSyncToken,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Create
# ============================================================================

async def create_event(
    db:             Session,
    lawyer_id:      str,
    title:          str,
    event_type:     str,
    start_datetime: datetime,
    end_datetime:   Optional[datetime] = None,
    all_day:        bool               = False,
    case_id:        Optional[str]      = None,
    description:    Optional[str]      = None,
    location:       Optional[str]      = None,
    source:         str                = "manual",
) -> CalendarEvent:
    """
    Creates a calendar event and triggers async Google sync.

    Args:
        db:             SQLAlchemy session
        lawyer_id:      UUID string of the lawyer
        title:          Event title
        event_type:     One of CalendarEventType values
        start_datetime: Start datetime (naive, treated as IST)
        end_datetime:   Optional end datetime
        all_day:        True for all-day events
        case_id:        Optional case UUID to link
        description:    Optional notes
        location:       Optional location string
        source:         "agent" | "manual" | "court_sync"

    Returns:
        Created CalendarEvent ORM object
    """
    event = CalendarEvent(
        lawyer_id=UUID(lawyer_id),
        case_id=UUID(case_id) if case_id else None,
        title=title,
        event_type=CalendarEventType(event_type),
        source=CalendarEventSource(source),
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        all_day=all_day,
        description=description,
        location=location,
        is_active=True,
    )

    db.add(event)
    db.commit()
    db.refresh(event)

    # Fire-and-forget Google sync — never block the response
    await _trigger_google_sync_create(event, lawyer_id, db)

    logger.info(
        "Calendar event created: %s (type=%s, lawyer=%s)",
        event.title, event.event_type.value, lawyer_id,
    )

    return event


# ============================================================================
# Read
# ============================================================================

async def get_events(
    db:          Session,
    lawyer_id:   str,
    date_from:   date,
    date_to:     date,
    case_id:     Optional[str] = None,
    event_type:  Optional[str] = None,
) -> list[CalendarEvent]:
    """
    Returns calendar events for a lawyer in a date range.

    Filters:
        date_from / date_to: inclusive date range on start_datetime
        case_id:             if provided, only events linked to this case
        event_type:          if provided, filter by type
    """
    query = db.query(CalendarEvent).filter(
        CalendarEvent.lawyer_id == UUID(lawyer_id),
        CalendarEvent.is_active == True,
        CalendarEvent.start_datetime >= datetime.combine(date_from, datetime.min.time()),
        CalendarEvent.start_datetime <= datetime.combine(date_to, datetime.max.time()),
    )

    if case_id:
        query = query.filter(CalendarEvent.case_id == UUID(case_id))

    if event_type:
        query = query.filter(CalendarEvent.event_type == CalendarEventType(event_type))

    return query.order_by(CalendarEvent.start_datetime).all()


async def get_event_by_id(
    db:        Session,
    event_id:  str,
    lawyer_id: str,
) -> Optional[CalendarEvent]:
    """Fetches a single event. Returns None if not found or not owned by lawyer."""
    return db.query(CalendarEvent).filter(
        CalendarEvent.id        == UUID(event_id),
        CalendarEvent.lawyer_id == UUID(lawyer_id),
        CalendarEvent.is_active == True,
    ).first()


async def get_upcoming_events(
    db:        Session,
    lawyer_id: str,
    days:      int = 7,
) -> list[CalendarEvent]:
    """Convenience: returns events for the next N days from today."""
    from zoneinfo import ZoneInfo
    today    = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    date_to  = today + timedelta(days=days)
    return await get_events(db, lawyer_id, today, date_to)


# ============================================================================
# Update
# ============================================================================

async def update_event(
    db:             Session,
    event_id:       str,
    lawyer_id:      str,
    title:          Optional[str]      = None,
    start_datetime: Optional[datetime] = None,
    end_datetime:   Optional[datetime] = None,
    description:    Optional[str]      = None,
    location:       Optional[str]      = None,
    all_day:        Optional[bool]     = None,
) -> Optional[CalendarEvent]:
    """
    Updates mutable fields on a calendar event.
    Returns None if event not found or not owned by lawyer.
    """
    event = await get_event_by_id(db, event_id, lawyer_id)
    if not event:
        return None

    if title          is not None: event.title          = title
    if start_datetime is not None: event.start_datetime = start_datetime
    if end_datetime   is not None: event.end_datetime   = end_datetime
    if description    is not None: event.description    = description
    if location       is not None: event.location       = location
    if all_day        is not None: event.all_day        = all_day

    # Mark Google sync as stale
    event.google_synced_at = None

    db.commit()
    db.refresh(event)

    await _trigger_google_sync_update(event, lawyer_id, db)

    return event


# ============================================================================
# Delete
# ============================================================================

async def delete_event(
    db:        Session,
    event_id:  str,
    lawyer_id: str,
) -> bool:
    """
    Soft-deletes a calendar event (is_active = False).
    Triggers Google Calendar deletion if synced.

    Returns True if deleted, False if not found.
    """
    event = await get_event_by_id(db, event_id, lawyer_id)
    if not event:
        return False

    google_event_id = event.google_event_id  # capture before soft-delete

    event.is_active       = False
    event.google_synced_at = None
    db.commit()

    # Remove from Google Calendar if it was synced
    if google_event_id:
        await _trigger_google_sync_delete(
            google_event_id=google_event_id,
            lawyer_id=lawyer_id,
            db=db,
        )

    logger.info("Calendar event soft-deleted: %s (lawyer=%s)", event_id, lawyer_id)
    return True


# ============================================================================
# Auto-population helpers (called by background jobs)
# ============================================================================

async def upsert_hearing_event(
    db:             Session,
    lawyer_id:      str,
    case_id:        str,
    case_number:    str,
    hearing_date:   datetime,
    court_number:   Optional[str] = None,
    judge_name:     Optional[str] = None,
) -> CalendarEvent:
    """
    Creates or updates a HEARING calendar event from case sync.
    Idempotent — safe to call every time a case is synced.

    Looks for an existing hearing event for this case on this date
    and updates it rather than creating a duplicate.
    """
    existing = db.query(CalendarEvent).filter(
        CalendarEvent.lawyer_id   == UUID(lawyer_id),
        CalendarEvent.case_id     == UUID(case_id),
        CalendarEvent.event_type  == CalendarEventType.HEARING,
        CalendarEvent.start_datetime >= datetime.combine(hearing_date.date(), datetime.min.time()),
        CalendarEvent.start_datetime <= datetime.combine(hearing_date.date(), datetime.max.time()),
        CalendarEvent.is_active   == True,
    ).first()

    title    = f"Hearing — {case_number}"
    location = f"Court Hall {court_number}, Kerala High Court" if court_number else "Kerala High Court"
    desc     = f"Judge: {judge_name}" if judge_name else None

    if existing:
        existing.title          = title
        existing.location       = location
        existing.description    = desc
        existing.google_synced_at = None
        db.commit()
        db.refresh(existing)
        return existing

    return await create_event(
        db=db,
        lawyer_id=lawyer_id,
        title=title,
        event_type="hearing",
        start_datetime=hearing_date,
        all_day=True,
        case_id=case_id,
        description=desc,
        location=location,
        source="court_sync",
    )


# ============================================================================
# Google Calendar sync triggers (fire-and-forget)
# ============================================================================

async def _trigger_google_sync_create(
    event:     CalendarEvent,
    lawyer_id: str,
    db:        Session,
) -> None:
    """Fires async Google Calendar create — never raises."""
    try:
        sync_token = _get_sync_token(db, lawyer_id)
        if not sync_token:
            return

        import asyncio
        from app.services.google_calendar_sync_service import push_event_to_google
        asyncio.create_task(
            push_event_to_google(event=event, sync_token=sync_token, db=db)
        )
    except Exception as e:
        logger.warning("Google sync create trigger failed (non-blocking): %s", e)


async def _trigger_google_sync_update(
    event:     CalendarEvent,
    lawyer_id: str,
    db:        Session,
) -> None:
    """Fires async Google Calendar update — never raises."""
    try:
        sync_token = _get_sync_token(db, lawyer_id)
        if not sync_token or not event.google_event_id:
            return

        import asyncio
        from app.services.google_calendar_sync_service import update_event_on_google
        asyncio.create_task(
            update_event_on_google(event=event, sync_token=sync_token, db=db)
        )
    except Exception as e:
        logger.warning("Google sync update trigger failed (non-blocking): %s", e)


async def _trigger_google_sync_delete(
    google_event_id: str,
    lawyer_id:       str,
    db:              Session,
) -> None:
    """Fires async Google Calendar delete — never raises."""
    try:
        sync_token = _get_sync_token(db, lawyer_id)
        if not sync_token:
            return

        import asyncio
        from app.services.google_calendar_sync_service import delete_event_on_google
        asyncio.create_task(
            delete_event_on_google(
                google_event_id=google_event_id,
                sync_token=sync_token,
                db=db,
            )
        )
    except Exception as e:
        logger.warning("Google sync delete trigger failed (non-blocking): %s", e)


def _get_sync_token(db: Session, lawyer_id: str) -> Optional[CalendarSyncToken]:
    """Returns the lawyer's Google sync token row, or None if not connected."""
    return db.query(CalendarSyncToken).filter(
        CalendarSyncToken.lawyer_id == UUID(lawyer_id),
        CalendarSyncToken.is_active == True,
    ).first()