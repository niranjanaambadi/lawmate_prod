"""
agent/tools/cause_list.py

Returns the lawyer's precomputed daily cause list from the
daily_cause_lists table (populated by the existing PDF pipeline).

Wraps: daily_cause_lists table via direct DB query.
No scraping — data is already in DB.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.agent.context import AgentContext
from app.agent.tools.registry import BaseTool
from app.db.database import SessionLocal
from app.db.models import DailyCauseList


class CauseListTool(BaseTool):

    name = "get_cause_list"

    description = (
        "Returns the lawyer's cause list (cases listed for hearing) for a given date. "
        "Defaults to today if no date is provided. "
        "Use when the lawyer asks 'what cases do I have today/tomorrow', "
        "'how many cases am I appearing in', or any schedule-related question."
    )

    input_schema = {
        "properties": {
            "date": {
                "type": "string",
                "description": (
                    "Date in YYYY-MM-DD format. Defaults to today (IST) if not provided."
                ),
            },
        },
        "required": [],
    }

    async def run(self, inputs: dict, context: AgentContext) -> dict:
        try:
            # Parse date or default to today IST
            target_date = _parse_date(inputs.get("date"))

            db: Session = SessionLocal()
            try:
                row = (
                    db.query(DailyCauseList)
                    .filter(
                        DailyCauseList.advocate_id == UUID(context.lawyer_id),
                        DailyCauseList.date == target_date,
                    )
                    .first()
                )

                if not row:
                    return self.ok({
                        "date":     target_date.isoformat(),
                        "listings": [],
                        "total":    0,
                        "message":  f"No cause list found for {target_date.strftime('%d %B %Y')}. "
                                    "The list may not have been processed yet.",
                    })

                if row.parse_error:
                    return self.err(
                        f"Cause list for {target_date} has a parse error: {row.parse_error}"
                    )

                listings = row.result_json.get("listings", []) if isinstance(row.result_json, dict) else []

                return self.ok({
                    "date":           target_date.strftime("%d %B %Y"),
                    "total_listings": row.total_listings,
                    "listings":       listings,
                    "source":         "daily_cause_lists (precomputed)",
                })

            finally:
                db.close()

        except Exception as e:
            return self.err(f"Could not fetch cause list: {str(e)}")


def _parse_date(date_str: str | None) -> date:
    """Parses YYYY-MM-DD string or returns today in IST."""
    if date_str:
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            pass

    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("Asia/Kolkata")).date()