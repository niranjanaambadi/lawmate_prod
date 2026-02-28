"""
agent/tools/hearing_history.py

Returns past hearing history for a case from the already-parsed
proceedings_html stored in cases.raw_court_data.

Wraps: existing DB query — no new scraping needed.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.agent.context import AgentContext
from app.agent.tools.registry import BaseTool
from app.db.database import SessionLocal
from app.db.models import Case, CaseHistory


class HearingHistoryTool(BaseTool):

    name = "get_hearing_history"

    description = (
        "Returns the past hearing history for a Kerala HC case — dates, "
        "orders passed, business recorded, and judge names. "
        "Use when the lawyer asks what happened in previous hearings, "
        "how many times the case was adjourned, or what the last order said."
    )

    input_schema = {
        "properties": {
            "case_id": {
                "type": "string",
                "description": "LawMate case UUID. Uses active case if not provided.",
            },
            "limit": {
                "type": "integer",
                "description": "Max number of hearings to return. Default 10.",
                "default": 10,
            },
        },
        "required": [],
    }

    async def run(self, inputs: dict, context: AgentContext) -> dict:
        try:
            case_id = inputs.get("case_id") or context.case_id
            limit = inputs.get("limit", 10)

            if not case_id:
                return self.err(
                    "No case in context. Please open a case or provide a case ID."
                )

            db: Session = SessionLocal()
            try:
                # Primary source: CaseHistory table (structured)
                history_rows = (
                    db.query(CaseHistory)
                    .filter(CaseHistory.case_id == UUID(case_id))
                    .order_by(CaseHistory.event_date.desc())
                    .limit(limit)
                    .all()
                )

                if history_rows:
                    hearings = [
                        {
                            "date":             h.event_date.strftime("%d %B %Y") if h.event_date else "N/A",
                            "event_type":       h.event_type.value if h.event_type else "N/A",
                            "business":         h.business_recorded,
                            "judge":            h.judge_name or "N/A",
                            "court_number":     h.court_number or "N/A",
                            "next_hearing":     h.next_hearing_date.strftime("%d %B %Y") if h.next_hearing_date else "N/A",
                        }
                        for h in history_rows
                    ]
                    return self.ok({
                        "hearings":  hearings,
                        "count":     len(hearings),
                        "source":    "case_history table",
                    })

                # Fallback: raw_court_data proceedings from eCourts scrape
                case = db.query(Case).filter(Case.id == UUID(case_id)).first()
                if not case or not case.raw_court_data:
                    return self.ok({
                        "hearings": [],
                        "count":    0,
                        "source":   "no data available",
                    })

                raw_hearings = case.raw_court_data.get("hearing_history", [])
                return self.ok({
                    "hearings": raw_hearings[:limit],
                    "count":    len(raw_hearings),
                    "source":   "raw_court_data (eCourts)",
                })

            finally:
                db.close()

        except Exception as e:
            return self.err(f"Could not fetch hearing history: {str(e)}")