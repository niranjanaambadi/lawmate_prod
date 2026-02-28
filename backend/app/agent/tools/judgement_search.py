"""
agent/tools/judgment_search.py

Searches Kerala HC judgments via IndianKanoon API.
Fire-and-forget ingestion into Bedrock KB after each search.
Falls back gracefully when INDIANKANOON_API_TOKEN is not set.
"""
from __future__ import annotations
import asyncio
import logging
import os
from typing import Any

from app.agent.tools.registry import BaseTool

logger = logging.getLogger(__name__)

INDIANKANOON_TOKEN = os.getenv("INDIANKANOON_API_TOKEN", "")
INDIANKANOON_URL   = "https://api.indiankanoon.org"


class JudgmentSearchTool(BaseTool):
    name        = "search_judgments"
    description = (
        "Searches Kerala High Court judgments and case law on IndianKanoon. "
        "Use when asked to find precedents, case law, or judgments on a legal topic. "
        "Returns case titles, citations, dates, and brief summaries. "
        "Examples: 'find bail judgments in NDPS cases', "
        "'search for Kerala HC judgments on land acquisition compensation', "
        "'find precedents on anticipatory bail under Section 438'."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Legal search query e.g. 'bail NDPS Kerala High Court 2023'",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum results to return (default 5, max 10)",
                "default": 5,
            },
        },
        "required": ["query"],
    }

    async def run(self, context: Any, db: Any, **kwargs) -> dict:
        query:       str = kwargs.get("query", "").strip()
        max_results: int = min(int(kwargs.get("max_results", 5)), 10)

        if not query:
            return {"success": False, "data": None, "error": "Search query is required"}

        if not INDIANKANOON_TOKEN:
            return {
                "success": False,
                "data":    None,
                "error":   "IndianKanoon API token not configured. Set INDIANKANOON_API_TOKEN in .env",
            }

        try:
            import httpx

            # Always scope to Kerala HC
            scoped_query = query if "kerala" in query.lower() else f"{query} Kerala High Court"

            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(
                    f"{INDIANKANOON_URL}/search/",
                    headers={"Authorization": f"Token {INDIANKANOON_TOKEN}"},
                    data={
                        "formInput":  scoped_query,
                        "pagenum":    0,
                        "courtId":    "allhc",     # High Courts filter
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            docs = data.get("docs", [])[:max_results]
            if not docs:
                return {
                    "success": True,
                    "data": {
                        "query":   query,
                        "results": [],
                        "total":   0,
                    },
                    "error": "No judgments found for this query.",
                }

            results = []
            for doc in docs:
                results.append({
                    "title":      doc.get("title", ""),
                    "citation":   doc.get("citation", ""),
                    "date":       doc.get("date", ""),
                    "court":      doc.get("court", "Kerala High Court"),
                    "doc_id":     str(doc.get("tid", "")),
                    "source_url": f"https://indiankanoon.org/doc/{doc.get('tid', '')}/",
                    "headline":   _strip_html(doc.get("headline", "")),
                })

            # Fire-and-forget KB ingestion (non-blocking)
            asyncio.create_task(_ingest_async(results, query))

            return {
                "success": True,
                "data": {
                    "query":   query,
                    "results": results,
                    "total":   len(results),
                },
                "error": None,
            }

        except Exception as e:
            logger.warning("JudgmentSearchTool error: %s", e)
            return {"success": False, "data": None, "error": str(e)}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _strip_html(text: str) -> str:
    import re
    return re.sub(r"<[^>]+>", " ", text).strip()


async def _ingest_async(results: list[dict], query: str) -> None:
    """Fire-and-forget KB ingestion — never blocks the agent response."""
    try:
        from app.services.judgment_ingestion_service import ingest_judgments
        await ingest_judgments(results, query)
    except Exception as e:
        logger.debug("KB ingestion skipped (non-blocking): %s", e)