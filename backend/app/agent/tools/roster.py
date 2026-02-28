"""
agent/tools/roster.py

Returns Kerala HC judge bench assignments from the roster.
Wraps: app.services.roster_service
"""

from __future__ import annotations

from app.agent.context import AgentContext
from app.agent.tools.registry import BaseTool


class RosterTool(BaseTool):

    name = "get_roster"

    description = (
        "Returns the current Kerala High Court judge roster — which judge "
        "sits in which court hall and bench. "
        "Use when the lawyer asks about bench assignments, which judge is "
        "sitting in a specific court hall, or the current roster."
    )

    input_schema = {
        "properties": {
            "court_number": {
                "type": "string",
                "description": "Filter by specific court number e.g. '5'. Optional.",
            },
        },
        "required": [],
    }

    async def run(self, inputs: dict, context: AgentContext) -> dict:
        try:
            from app.services.roster_service import get_latest_roster
            roster_data = await get_latest_roster()

            if not roster_data:
                return self.err(
                    "Roster data is not available. "
                    "Try syncing the roster from the Roster page."
                )

            court_filter = inputs.get("court_number")
            if court_filter:
                roster_data = [
                    r for r in roster_data
                    if str(r.get("court_number", "")) == str(court_filter)
                ]

            return self.ok({
                "roster":  roster_data,
                "count":   len(roster_data),
                "source":  "Kerala HC Roster (roster_service)",
            })

        except Exception as e:
            return self.err(f"Could not fetch roster: {str(e)}")