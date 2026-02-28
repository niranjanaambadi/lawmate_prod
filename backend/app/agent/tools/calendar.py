"""
agent/tools/calendar.py

Three calendar tools for the LawMate agent:
  - CreateCalendarEventTool
  - GetCalendarEventsTool
  - DeleteCalendarEventTool

All wrap app.services.calendar_service (to be built next).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from app.agent.context import AgentContext
from app.agent.tools.registry import BaseTool


# ============================================================================
# CreateCalendarEventTool
# ============================================================================

class CreateCalendarEventTool(BaseTool):

    name = "create_calendar_event"

    description = (
        "Creates a calendar event for the lawyer. "
        "Use whenever the lawyer says 'remind me', 'schedule', 'add to calendar', "
        "'set a reminder', or mentions a deadline or filing date. "
        "Also call this automatically when a new hearing date is confirmed "
        "from a case status refresh. "
        "The event syncs to Google Calendar if the lawyer has connected it."
    )

    input_schema = {
        "properties": {
            "title": {
                "type": "string",
                "description": "Event title e.g. 'Hearing — WP(C) 1234/2024' or 'File vakalatnama'.",
            },
            "event_type": {
                "type": "string",
                "enum": ["hearing", "deadline", "filing", "reminder", "meeting", "other"],
                "description": "Type of event.",
            },
            "start_datetime": {
                "type": "string",
                "description": (
                    "Start date/time in ISO format: YYYY-MM-DDTHH:MM:SS "
                    "or just YYYY-MM-DD for all-day events. "
                    "Always interpret in IST (Asia/Kolkata)."
                ),
            },
            "end_datetime": {
                "type": "string",
                "description": "End date/time ISO format. Optional.",
            },
            "all_day": {
                "type": "boolean",
                "description": "True for all-day events (deadlines, hearing dates). Default false.",
                "default": False,
            },
            "case_id": {
                "type": "string",
                "description": "LawMate case UUID to link this event to. Optional.",
            },
            "description": {
                "type": "string",
                "description": "Additional notes for the event. Optional.",
            },
            "location": {
                "type": "string",
                "description": "Location e.g. 'Court Hall 5, Kerala High Court'. Optional.",
            },
        },
        "required": ["title", "event_type", "start_datetime"],
    }

    async def run(self, inputs: dict, context: AgentContext) -> dict:
        try:
            from app.services.calendar_service import create_event
            from app.db.database import SessionLocal

            # Auto-link to active case if not specified
            case_id = inputs.get("case_id") or context.case_id

            db = SessionLocal()
            try:
                event = await create_event(
                    db=db,
                    lawyer_id=context.lawyer_id,
                    title=inputs["title"],
                    event_type=inputs["event_type"],
                    start_datetime=_parse_datetime(inputs["start_datetime"]),
                    end_datetime=_parse_datetime(inputs.get("end_datetime")),
                    all_day=inputs.get("all_day", False),
                    case_id=case_id,
                    description=inputs.get("description"),
                    location=inputs.get("location"),
                    source="agent",
                )
                return self.ok({
                    "event_id":       str(event.id),
                    "title":          event.title,
                    "event_type":     event.event_type.value,
                    "start_datetime": event.start_datetime.strftime("%d %B %Y %I:%M %p"),
                    "all_day":        event.all_day,
                    "google_synced":  event.google_event_id is not None,
                    "message":        f"✓ Added to calendar: {event.title}",
                })
            finally:
                db.close()

        except Exception as e:
            return self.err(f"Could not create calendar event: {str(e)}")


# ============================================================================
# GetCalendarEventsTool
# ============================================================================

class GetCalendarEventsTool(BaseTool):

    name = "get_calendar_events"

    description = (
        "Returns the lawyer's scheduled calendar events for a date range. "
        "Use when the lawyer asks 'what do I have this week', 'show my schedule', "
        "'what are my upcoming deadlines', or any question about future events."
    )

    input_schema = {
        "properties": {
            "date_from": {
                "type": "string",
                "description": "Start date YYYY-MM-DD. Defaults to today.",
            },
            "date_to": {
                "type": "string",
                "description": "End date YYYY-MM-DD. Defaults to 7 days from date_from.",
            },
            "case_id": {
                "type": "string",
                "description": "Filter events for a specific case. Optional.",
            },
            "event_type": {
                "type": "string",
                "enum": ["hearing", "deadline", "filing", "reminder", "meeting", "other"],
                "description": "Filter by event type. Optional.",
            },
        },
        "required": [],
    }

    async def run(self, inputs: dict, context: AgentContext) -> dict:
        try:
            from app.services.calendar_service import get_events
            from app.db.database import SessionLocal
            from zoneinfo import ZoneInfo

            ist = ZoneInfo("Asia/Kolkata")
            today = datetime.now(ist).date()

            date_from = _parse_date_only(inputs.get("date_from")) or today
            date_to   = _parse_date_only(inputs.get("date_to"))
            if not date_to:
                from datetime import timedelta
                date_to = date_from + timedelta(days=7)

            case_id    = inputs.get("case_id") or (context.case_id if inputs.get("case_id") else None)
            event_type = inputs.get("event_type")

            db = SessionLocal()
            try:
                events = await get_events(
                    db=db,
                    lawyer_id=context.lawyer_id,
                    date_from=date_from,
                    date_to=date_to,
                    case_id=case_id,
                    event_type=event_type,
                )

                formatted = [
                    {
                        "event_id":   str(e.id),
                        "title":      e.title,
                        "event_type": e.event_type.value,
                        "start":      e.start_datetime.strftime("%d %B %Y %I:%M %p") if not e.all_day
                                      else e.start_datetime.strftime("%d %B %Y"),
                        "all_day":    e.all_day,
                        "location":   e.location or "",
                        "case_id":    str(e.case_id) if e.case_id else None,
                    }
                    for e in events
                ]

                return self.ok({
                    "events":     formatted,
                    "count":      len(formatted),
                    "date_from":  date_from.strftime("%d %B %Y"),
                    "date_to":    date_to.strftime("%d %B %Y"),
                })
            finally:
                db.close()

        except Exception as e:
            return self.err(f"Could not fetch calendar events: {str(e)}")


# ============================================================================
# DeleteCalendarEventTool
# ============================================================================

class DeleteCalendarEventTool(BaseTool):

    name = "delete_calendar_event"

    description = (
        "Deletes a calendar event for the lawyer. "
        "Use when the lawyer says 'remove', 'cancel', or 'delete' a reminder or event. "
        "Always confirm the event title before deleting."
    )

    input_schema = {
        "properties": {
            "event_id": {
                "type": "string",
                "description": "The event UUID to delete. Get this from get_calendar_events first.",
            },
        },
        "required": ["event_id"],
    }

    async def run(self, inputs: dict, context: AgentContext) -> dict:
        try:
            from app.services.calendar_service import delete_event
            from app.db.database import SessionLocal

            db = SessionLocal()
            try:
                deleted = await delete_event(
                    db=db,
                    event_id=inputs["event_id"],
                    lawyer_id=context.lawyer_id,  # ownership check inside service
                )
                if not deleted:
                    return self.err("Event not found or you do not have permission to delete it.")

                return self.ok({"message": "✓ Event removed from calendar."})
            finally:
                db.close()

        except Exception as e:
            return self.err(f"Could not delete calendar event: {str(e)}")


# ============================================================================
# Helpers
# ============================================================================

def _parse_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    if not dt_str:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(dt_str, fmt)
        except ValueError:
            continue
    return None


def _parse_date_only(date_str: Optional[str]):
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return None