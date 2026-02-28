"""
agent/tools/advocate_cause_list.py

Fetches advocate-wise cause list from hckinfo.keralacourts.in/digicourt
to get item numbers, court halls, bench, and judge assignments.

Freshness strategy:
  - Today: always scrape fresh, upsert into advocate_cause_lists table
  - Past dates: serve from cache (advocate_cause_lists table)

Wraps: app.services.advocate_causelist_service (to be built)
Falls back to DB cache if service is unavailable.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.agent.context import AgentContext
from app.agent.tools.registry import BaseTool
from app.db.database import SessionLocal
from app.db.models import AdvocateCauseList


class AdvocateCauseListTool(BaseTool):

    name = "get_advocate_cause_list"

    description = (
        "Fetches the advocate-wise cause list from Kerala HC digicourt portal. "
        "Returns item numbers, court hall, bench code, judge name, and case details "
        "for each case listed for the advocate on a given date. "
        "Use when the lawyer asks for their item number, which court hall they are in, "
        "or who the judge is for a specific case today."
    )

    input_schema = {
        "properties": {
            "advocate_name": {
                "type": "string",
                "description": (
                    "Full advocate name as registered with Kerala HC. "
                    "Uses the logged-in lawyer's KHC name if not provided."
                ),
            },
            "date": {
                "type": "string",
                "description": "Date in YYYY-MM-DD format. Defaults to today (IST).",
            },
        },
        "required": [],
    }

    async def run(self, inputs: dict, context: AgentContext) -> dict:
        try:
            target_date = _parse_date(inputs.get("date"))
            advocate_name = inputs.get("advocate_name") or context.lawyer_name

            # Check cache first for past dates
            from zoneinfo import ZoneInfo
            today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
            is_today = (target_date == today)

            db: Session = SessionLocal()
            try:
                if not is_today:
                    # Past date — serve from cache always
                    return _fetch_from_cache(
                        db, context.lawyer_id, advocate_name, target_date
                    )

                # Today — try live scrape first, fall back to cache
                try:
                    from app.services.advocate_causelist_service import (
                        fetch_and_store_advocate_causelist,
                    )
                    rows = await fetch_and_store_advocate_causelist(
                        advocate_name=advocate_name,
                        target_date=target_date,
                        lawyer_id=context.lawyer_id,
                        db=db,
                    )
                    return self.ok(_format_rows(rows, target_date, "live scrape"))

                except Exception as scrape_err:
                    import logging
                    logging.getLogger(__name__).warning(
                        "Live scrape failed for %s on %s: %s — falling back to cache",
                        advocate_name, target_date, scrape_err,
                    )
                    return _fetch_from_cache(
                        db, context.lawyer_id, advocate_name, target_date
                    )

            finally:
                db.close()

        except Exception as e:
            return self.err(f"Could not fetch advocate cause list: {str(e)}")


# ============================================================================
# Helpers
# ============================================================================

def _fetch_from_cache(
    db: Session,
    lawyer_id: str,
    advocate_name: str,
    target_date: date,
) -> dict:
    rows = (
        db.query(AdvocateCauseList)
        .filter(
            AdvocateCauseList.lawyer_id == UUID(lawyer_id),
            AdvocateCauseList.date == target_date,
        )
        .order_by(AdvocateCauseList.item_no)
        .all()
    )

    if not rows:
        from app.agent.tools.registry import BaseTool
        return BaseTool.ok({
            "date":     target_date.isoformat(),
            "listings": [],
            "total":    0,
            "message":  f"No cause list data found for {target_date.strftime('%d %B %Y')}. "
                        "Try fetching fresh data or check if the cause list has been published.",
        })

    return BaseTool.ok(_format_rows(rows, target_date, "cache"))


def _format_rows(rows: list, target_date: date, source: str) -> dict:
    listings = [
        {
            "item_no":          r.item_no,
            "court_hall":       r.court_hall,
            "court_hall_number": r.court_hall_number,
            "bench":            r.bench,
            "list_type":        r.list_type,
            "judge_name":       r.judge_name,
            "case_no":          r.case_no,
            "petitioner":       r.petitioner,
            "respondent":       r.respondent,
        }
        for r in rows
    ]
    return {
        "date":     target_date.strftime("%d %B %Y"),
        "total":    len(listings),
        "listings": listings,
        "source":   f"hckinfo.keralacourts.in ({source})",
    }


def _parse_date(date_str: str | None) -> date:
    if date_str:
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            pass
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("Asia/Kolkata")).date()