"""
agent/tools/case_status.py

Fetches live case status from eCourts via the existing case_sync_service.
Wraps: app.services.case_sync_service.case_sync_service.query_case_status()
"""

from __future__ import annotations

from uuid import UUID

from app.agent.context import AgentContext
from app.agent.tools.registry import BaseTool
from app.db.database import SessionLocal
from app.db.models import Case
from app.services.case_sync_service import case_sync_service


class CaseStatusTool(BaseTool):

    name = "get_case_status"

    description = (
        "Fetches live case status from eCourts for a Kerala HC case. "
        "Returns bench, judge, next hearing date, court number, and current status. "
        "Use when the lawyer asks about the status of a case or when you need "
        "fresh court data before answering a case-related question."
    )

    input_schema = {
        "properties": {
            "case_id": {
                "type": "string",
                "description": (
                    "LawMate internal case UUID. Use this when available "
                    "(it is always available on case_detail and hearing_day pages)."
                ),
            },
            "case_number": {
                "type": "string",
                "description": (
                    "Kerala HC case number e.g. 'WP(C) 1234/2024'. "
                    "Use when case_id is not available."
                ),
            },
        },
        "required": [],
    }

    async def run(self, inputs: dict, context: AgentContext) -> dict:
        try:
            case_id = inputs.get("case_id") or context.case_id
            case_number = inputs.get("case_number")

            if not case_id and not case_number:
                return self.err(
                    "Please provide either a case ID or case number to fetch status."
                )

            if not case_number and case_id:
                db = SessionLocal()
                try:
                    case = (
                        db.query(Case)
                        .filter(Case.id == UUID(case_id), Case.advocate_id == UUID(context.lawyer_id))
                        .first()
                    )
                    if not case:
                        return self.err("Case not found for this user.")
                    case_number = (case.case_number or "").strip()
                finally:
                    db.close()

            if not case_number:
                return self.err("Case number is missing for this case.")

            result = case_sync_service.query_case_status(case_number=case_number)

            return self.ok({
                "case_number":      result.get("case_number"),
                "status":           result.get("status_text"),
                "next_hearing":     result.get("next_hearing_date"),
                "judge":            result.get("coram"),
                "bench":            result.get("stage"),
                "court_number":     result.get("last_listed_bench"),
                "petitioner":       result.get("petitioner_name"),
                "respondent":       result.get("respondent_name"),
                "last_synced":      result.get("fetched_at"),
                "source":           "eCourts Kerala HC",
            })

        except Exception as e:
            return self.err(f"Could not fetch case status: {str(e)}")
