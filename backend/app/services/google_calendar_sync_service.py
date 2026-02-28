from __future__ import annotations

from typing import Any, Dict
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import CalendarEvent, CalendarSyncToken


def _google_enabled() -> bool:
    return bool(
        getattr(settings, "GOOGLE_CLIENT_ID", None)
        and getattr(settings, "GOOGLE_CLIENT_SECRET", None)
        and getattr(settings, "GOOGLE_REDIRECT_URI", None)
    )


def get_oauth_url(state: str) -> str:
    if not _google_enabled():
        raise ValueError("Google Calendar is not configured")
    from urllib.parse import urlencode
    params = {
        "client_id":     settings.GOOGLE_CLIENT_ID,
        "redirect_uri":  settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope":         "https://www.googleapis.com/auth/calendar",
        "access_type":   "offline",
        "state":         state,
        "prompt":        "consent",
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)


async def exchange_code_for_tokens(code: str, lawyer_id: str, db: Session) -> None:
    if not _google_enabled():
        raise ValueError("Google Calendar is not configured")
    # Placeholder no-op for local/dev until full OAuth exchange is wired.
    return None


async def run_incremental_sync(lawyer_id: str, db: Session) -> Dict[str, Any]:
    if not _google_enabled():
        return {"error": "Google Calendar is not configured"}
    # Placeholder no-op sync stats.
    return {"created": 0, "updated": 0, "deleted": 0, "errors": []}


async def disconnect_google_calendar(lawyer_id: str, db: Session) -> None:
    token = (
        db.query(CalendarSyncToken)
        .filter(CalendarSyncToken.lawyer_id == UUID(lawyer_id))
        .first()
    )
    if token:
        token.is_active = False
        db.commit()


async def push_event_to_google(event: CalendarEvent, sync_token: CalendarSyncToken, db: Session) -> None:
    # Placeholder no-op (non-blocking hooks in calendar_service call this).
    return None


async def update_event_on_google(event: CalendarEvent, sync_token: CalendarSyncToken, db: Session) -> None:
    # Placeholder no-op.
    return None


async def delete_event_on_google(google_event_id: str, sync_token: CalendarSyncToken, db: Session) -> None:
    # Placeholder no-op.
    return None
