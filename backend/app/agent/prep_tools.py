"""
agent/prep_tools.py

Self-contained tool module for Case Prep AI — Precedent Finder mode.

Designed to be independently deployable (no dependency on agent.py or the
main chat-widget agent loop) so Case Prep AI can be extracted as a separate
microservice when needed.

Tool cascade (in order of preference):
  1. search_judgment_kb     — Bedrock Knowledge Base (cached, fast, no API cost)
  2. search_indiankanoon    — IndianKanoon API (live, comprehensive Kerala HC judgments)
  3. search_web             — Tavily web search (last resort: SCC Online, Manupatra, etc.)

Additional tools (callable any time):
  4. search_legal_resources — Resources KB: Kerala HC Rules, bare acts, court fees,
                              limitation, practice directions, constitutional provisions

Claude's decision logic (baked into system prompt):
  - Always try search_judgment_kb first.
  - If results < 2 or user asks for more, call search_indiankanoon.
  - If IndianKanoon yields < 2 results or user is still unsatisfied, call search_web.
  - Call search_legal_resources whenever statutes / rules / fees are relevant.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)


# ============================================================================
# Tool Specs (Bedrock converse API format)
# ============================================================================

PREP_TOOL_SPECS: list[dict] = [
    {
        "name": "search_judgment_kb",
        "description": (
            "Search the LawMate Judgments Knowledge Base for cached Kerala HC judgments. "
            "This is the fastest source — always try this first. "
            "Returns judgment titles, citations, dates, holdings, and source URLs. "
            "If this returns fewer than 2 good results, follow up with search_indiankanoon."
        ),
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Legal search query. Be specific — include the legal issue, "
                            "relevant statute/section, and 'Kerala High Court'. "
                            "E.g. 'anticipatory bail Section 438 CrPC Kerala High Court'."
                        ),
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Max results to return. Default 5.",
                    },
                },
                "required": ["query"],
            }
        },
    },
    {
        "name": "search_indiankanoon",
        "description": (
            "Search IndianKanoon for live Kerala High Court judgments. "
            "Use when the Knowledge Base returns fewer than 2 results, "
            "or when the user explicitly asks to search IndianKanoon or wants more judgments. "
            "Returns titles, citations, dates, headlines, and source URLs. "
            "Results are ingested into the KB in the background for future queries."
        ),
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Legal search query for IndianKanoon. "
                            "E.g. 'bail NDPS Act Kerala High Court 2023' or "
                            "'anticipatory bail Section 438 CrPC'. "
                            "'Kerala High Court' is added automatically if missing."
                        ),
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Max results to return (default 5, max 10).",
                    },
                },
                "required": ["query"],
            }
        },
    },
    {
        "name": "search_web",
        "description": (
            "Search legal databases on the web (SCC Online, Manupatra, Bar and Bench, etc.) "
            "via Tavily. Use ONLY when both search_judgment_kb and search_indiankanoon "
            "return insufficient results, or when the user explicitly asks for a web search. "
            "Restricted to configured legal domains."
        ),
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Search query. Include relevant legal terms, court name, year. "
                            "E.g. 'Kerala High Court bail NDPS 2024 SCC site:manupatra.com'."
                        ),
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Max results (default 5, max 10).",
                    },
                },
                "required": ["query"],
            }
        },
    },
    {
        "name": "search_legal_resources",
        "description": (
            "Search indexed Kerala HC legal resources: court rules, court fee schedules, "
            "bare acts (IPC/BNS, CrPC/BNSS, CPC, Evidence Act, Limitation Act, etc.), "
            "e-filing guidelines, and practice directions. "
            "Use when the lawyer asks about: filing fees, limitation periods, "
            "procedural requirements, specific sections of statutes, "
            "or Kerala HC practice directions. Always cite resource name and section."
        ),
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Search query. E.g. 'court fee writ petition Kerala HC' or "
                            "'Section 34 Limitation Act' or 'e-filing document requirements'."
                        ),
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Optional tag filters to narrow the search. "
                            "Available: fees, filing, procedure, rules, limitation, "
                            "constitution, bare_acts, practice_directions, efiling."
                        ),
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Max results (default 3, max 5).",
                    },
                },
                "required": ["query"],
            }
        },
    },
]


# ============================================================================
# Tool dispatcher
# ============================================================================

async def dispatch_prep_tool(tool_name: str, tool_inputs: dict) -> dict:
    """
    Dispatch a Case Prep tool call and return the result dict.

    Always returns {"success": bool, "data": ..., "error": str | None}.
    Never raises — errors are captured into the result dict.
    """
    handlers = {
        "search_judgment_kb":    _run_search_judgment_kb,
        "search_indiankanoon":   _run_search_indiankanoon,
        "search_web":            _run_search_web,
        "search_legal_resources": _run_search_legal_resources,
    }
    handler = handlers.get(tool_name)
    if not handler:
        return {"success": False, "data": None, "error": f"Unknown tool: {tool_name}"}
    try:
        return await handler(tool_inputs)
    except Exception as exc:
        logger.exception("Prep tool %s failed: %s", tool_name, exc)
        return {"success": False, "data": None, "error": str(exc)}


def summarise_prep_tool_result(tool_name: str, result: dict) -> str:
    """Human-readable summary of a tool result for the UI tool badge."""
    if not result.get("success"):
        return f"⚠ {result.get('error', 'Tool failed')}"

    data = result.get("data") or {}
    count = data.get("count", 0)

    summaries = {
        "search_judgment_kb":     lambda d: f"{d.get('count', 0)} judgments from Knowledge Base",
        "search_indiankanoon":    lambda d: f"{d.get('count', 0)} judgments from IndianKanoon",
        "search_web":             lambda d: f"{d.get('count', 0)} results from web search",
        "search_legal_resources": lambda d: f"{d.get('count', 0)} resources found",
    }

    fn = summaries.get(tool_name)
    if fn:
        try:
            return fn(data)
        except Exception:
            pass

    return f"✓ {tool_name.replace('_', ' ')} completed"


# ============================================================================
# Tool implementations
# ============================================================================

async def _run_search_judgment_kb(inputs: dict) -> dict:
    """
    Search the Bedrock judgments Knowledge Base (cached, fast).
    Uses bedrock-agent-runtime retrieve API.
    """
    import boto3

    query       = (inputs.get("query") or "").strip()
    max_results = min(int(inputs.get("max_results", 5)), 10)

    if not query:
        return {"success": False, "data": None, "error": "query is required"}

    kb_id  = os.getenv("BEDROCK_KNOWLEDGE_BASE_ID", "")
    region = os.getenv("AWS_REGION", "ap-south-1")

    if not kb_id:
        return {
            "success": True,
            "data": {"query": query, "results": [], "count": 0, "source": "kb"},
            "error": "BEDROCK_KNOWLEDGE_BASE_ID not configured — KB search skipped.",
        }

    try:
        client = boto3.client("bedrock-agent-runtime", region_name=region)
        response = client.retrieve(
            knowledgeBaseId=kb_id,
            retrievalQuery={"text": query},
            retrievalConfiguration={
                "vectorSearchConfiguration": {"numberOfResults": max_results}
            },
        )

        results = []
        for item in response.get("retrievalResults", []):
            content  = item.get("content", {}).get("text", "")
            metadata = item.get("metadata", {})
            score    = item.get("score", 0)

            if score < 0.35:
                continue

            results.append({
                "title":      metadata.get("title", "Untitled Judgment"),
                "citation":   metadata.get("citation", ""),
                "date":       metadata.get("date", ""),
                "court":      metadata.get("court", "Kerala High Court"),
                "source_url": metadata.get("source_url", ""),
                "excerpt":    content[:800],
                "score":      round(score, 3),
            })

        return {
            "success": True,
            "data": {
                "query":   query,
                "results": results,
                "count":   len(results),
                "source":  "LawMate Judgments KB",
            },
            "error": None if results else "No judgments found in KB for this query.",
        }

    except Exception as exc:
        logger.warning("Judgment KB search failed: %s", exc)
        return {"success": False, "data": None, "error": str(exc)}


async def _run_search_indiankanoon(inputs: dict) -> dict:
    """
    Search IndianKanoon API for Kerala HC judgments (live).
    Fire-and-forget ingestion into KB after each search.
    """
    query       = (inputs.get("query") or "").strip()
    max_results = min(int(inputs.get("max_results", 5)), 10)

    if not query:
        return {"success": False, "data": None, "error": "query is required"}

    token = os.getenv("INDIANKANOON_API_TOKEN", "")
    if not token:
        return {
            "success": False,
            "data": None,
            "error": "INDIANKANOON_API_TOKEN not configured.",
        }

    # Always scope to Kerala HC
    scoped_query = query if "kerala" in query.lower() else f"{query} Kerala High Court"

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                "https://api.indiankanoon.org/search/",
                headers={"Authorization": f"Token {token}"},
                data={
                    "formInput": scoped_query,
                    "pagenum":   0,
                    "courtId":   "allhc",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        docs = data.get("docs", [])[:max_results]
        if not docs:
            return {
                "success": True,
                "data": {"query": query, "results": [], "count": 0, "source": "IndianKanoon"},
                "error": "No judgments found on IndianKanoon for this query.",
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
        asyncio.create_task(_ingest_to_kb(results, query))

        return {
            "success": True,
            "data": {
                "query":   query,
                "results": results,
                "count":   len(results),
                "source":  "IndianKanoon",
            },
            "error": None,
        }

    except Exception as exc:
        logger.warning("IndianKanoon search failed: %s", exc)
        return {"success": False, "data": None, "error": str(exc)}


async def _run_search_web(inputs: dict) -> dict:
    """
    Tavily web search — last resort for precedent finding.
    Scoped to legal domains configured in TAVILY_ALLOWED_DOMAINS.
    """
    from app.core.config import settings

    query       = (inputs.get("query") or "").strip()
    max_results = min(int(inputs.get("max_results", 5)), 10)

    if not query:
        return {"success": False, "data": None, "error": "query is required"}

    if not settings.TAVILY_API_KEY:
        return {
            "success": False,
            "data": None,
            "error": "TAVILY_API_KEY not configured — web search unavailable.",
        }

    payload: dict[str, Any] = {
        "api_key":             settings.TAVILY_API_KEY,
        "query":               query,
        "max_results":         max_results,
        "search_depth":        "basic",
        "include_answer":      False,
        "include_raw_content": False,
        "include_images":      False,
    }

    allowed = settings.tavily_allowed_domains_list
    if allowed:
        payload["include_domains"] = allowed

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post("https://api.tavily.com/search", json=payload)
            resp.raise_for_status()
            body = resp.json()

        rows = []
        for item in (body.get("results") or []):
            rows.append({
                "title":   item.get("title", ""),
                "url":     item.get("url", ""),
                "snippet": item.get("content", ""),
                "score":   item.get("score"),
            })

        return {
            "success": True,
            "data": {
                "query":   query,
                "results": rows,
                "count":   len(rows),
                "source":  "web search",
            },
            "error": None,
        }

    except Exception as exc:
        logger.warning("Web search failed: %s", exc)
        return {"success": False, "data": None, "error": str(exc)}


async def _run_search_legal_resources(inputs: dict) -> dict:
    """
    Search indexed Kerala HC legal resources via Bedrock Resources KB.
    Covers: Kerala HC Rules, bare acts, court fees, limitation, practice directions.
    """
    import boto3

    query       = (inputs.get("query") or "").strip()
    tags        = inputs.get("tags") or []
    max_results = min(int(inputs.get("max_results", 3)), 5)

    if not query:
        return {"success": False, "data": None, "error": "query is required"}

    kb_id  = os.getenv("BEDROCK_RESOURCES_KB_ID", "")
    region = os.getenv("AWS_REGION", "ap-south-1")

    if not kb_id:
        return {
            "success": False,
            "data": None,
            "error": "BEDROCK_RESOURCES_KB_ID not configured — resource search unavailable.",
        }

    enriched_query = f"{query} [{' '.join(tags)}]" if tags else query

    try:
        client = boto3.client("bedrock-agent-runtime", region_name=region)
        response = client.retrieve(
            knowledgeBaseId=kb_id,
            retrievalQuery={"text": enriched_query},
            retrievalConfiguration={
                "vectorSearchConfiguration": {"numberOfResults": max_results}
            },
        )

        results = []
        for item in response.get("retrievalResults", []):
            content  = item.get("content", {}).get("text", "")
            metadata = item.get("metadata", {})
            score    = item.get("score", 0)

            if score < 0.35:
                continue

            results.append({
                "resource_name": metadata.get("name", "Unknown Resource"),
                "tags":          metadata.get("tags", []),
                "excerpt":       content[:600],
                "score":         round(score, 3),
                "source":        metadata.get("source", ""),
            })

        return {
            "success": True,
            "data": {
                "query":   query,
                "results": results,
                "count":   len(results),
                "source":  "Legal Resources KB",
            },
            "error": None if results else "No resources found for this query.",
        }

    except Exception as exc:
        logger.warning("Legal resources KB search failed: %s", exc)
        return {"success": False, "data": None, "error": str(exc)}


# ============================================================================
# Helpers
# ============================================================================

def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text).strip()


async def _ingest_to_kb(results: list[dict], query: str) -> None:
    """Fire-and-forget — ingest IndianKanoon results into Bedrock KB."""
    try:
        from app.services.judgement_ingestion_service import ingest_judgments
        await ingest_judgments(results, query)
    except Exception as exc:
        logger.debug("KB ingestion skipped (non-blocking): %s", exc)
