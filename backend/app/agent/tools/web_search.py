"""
agent/tools/web_search.py

Web search with Firecrawl as primary and Tavily as fallback.

Priority:
  1. Firecrawl (FIRECRAWL_API_KEY set) → full page markdown per result
  2. Tavily fallback (TAVILY_API_KEY set) → snippets, used when Firecrawl
     is not configured or raises an exception

Domain allowlist (FIRECRAWL_ALLOWED_DOMAINS) is enforced on both providers
so the agent cannot search outside configured legal domains.
"""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from app.agent.tools.registry import BaseTool
from app.core.config import settings

logger = logging.getLogger(__name__)


def _normalize_domain(value: str) -> str:
    candidate = (value or "").strip().lower()
    if not candidate:
        return ""
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    parsed = urlparse(candidate)
    host = (parsed.netloc or parsed.path or "").strip().lower()
    if not host:
        return ""
    if "@" in host:
        host = host.split("@", 1)[1]
    if ":" in host:
        host = host.split(":", 1)[0]
    if host.startswith("www."):
        host = host[4:]
    return host


def _filter_domains(requested: list[str]) -> list[str]:
    allowed = settings.firecrawl_allowed_domains_list
    if not allowed:
        return []
    if not requested:
        return allowed
    filtered = []
    for item in requested:
        host = _normalize_domain(item)
        if host and host in allowed and host not in filtered:
            filtered.append(host)
    return filtered


# Firecrawl: chars per result (full markdown trimmed to fit context window)
_CHARS_PER_RESULT = 3000


class WebSearchTool(BaseTool):
    name = "search_web"
    description = (
        "Searches the web for supplementary legal updates and references. "
        "Uses Firecrawl (full article content) with Tavily as fallback (snippets). "
        "Results are restricted to configured legal domains (LiveLaw, BarAndBench, etc.). "
        "Use only when DB tools and judgment/resource tools are insufficient."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Legal search query, e.g. 'Kerala HC NDPS bail 2024'.",
            },
            "max_results": {
                "type": "integer",
                "description": "Max results to return (default 5, max 10).",
            },
            "domains": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional domain filter; intersected with allowlist.",
            },
        },
        "required": ["query"],
    }

    async def run(self, context: Any, db: Any, **kwargs) -> dict:
        query = (kwargs.get("query") or "").strip()
        if not query:
            return self.err("query is required")

        max_results = kwargs.get("max_results", settings.FIRECRAWL_SEARCH_MAX_RESULTS)
        try:
            max_results = max(1, min(int(max_results), 10))
        except Exception:
            max_results = max(1, min(int(settings.FIRECRAWL_SEARCH_MAX_RESULTS or 5), 10))

        requested_domains = kwargs.get("domains") or []
        if not isinstance(requested_domains, list):
            requested_domains = []
        include_domains = _filter_domains([str(v) for v in requested_domains])

        # Reject if caller asked for specific domains that aren't in allowlist
        if settings.firecrawl_allowed_domains_list and requested_domains and not include_domains:
            return self.err("Requested domains are not in the allowed domain list.")

        # ── 1. Try Firecrawl ──────────────────────────────────────────────────
        if settings.FIRECRAWL_API_KEY:
            result = await _search_firecrawl(query, max_results, include_domains)
            if result.get("success"):
                return result
            # Firecrawl failed — log and fall through to Tavily
            logger.warning(
                "Firecrawl search failed (%s), falling back to Tavily",
                result.get("error"),
            )

        # ── 2. Tavily fallback ────────────────────────────────────────────────
        if settings.TAVILY_API_KEY:
            return await _search_tavily(query, max_results, include_domains)

        # ── Neither configured ────────────────────────────────────────────────
        return self.err(
            "No web search provider configured. "
            "Set FIRECRAWL_API_KEY (recommended) or TAVILY_API_KEY in environment."
        )


# ── Firecrawl implementation ──────────────────────────────────────────────────

async def _search_firecrawl(
    query: str,
    max_results: int,
    include_domains: list[str],
) -> dict:
    try:
        from firecrawl import FirecrawlApp

        app = FirecrawlApp(api_key=settings.FIRECRAWL_API_KEY)

        search_kwargs: dict[str, Any] = {
            "limit": max_results,
            "scrape_options": {"formats": ["markdown"]},
        }
        if include_domains:
            search_kwargs["include_domains"] = include_domains

        results = app.search(query, **search_kwargs)

        rows = []
        for item in (results.data or []):
            url = str(getattr(item, "url", "") or "")
            markdown = str(getattr(item, "markdown", "") or "")
            if len(markdown) > _CHARS_PER_RESULT:
                markdown = markdown[:_CHARS_PER_RESULT] + "…"
            rows.append({
                "title":   str(getattr(item, "title", "") or ""),
                "url":     url,
                "domain":  _normalize_domain(url),
                "content": markdown,
            })

        return BaseTool.ok({
            "query":        query,
            "results":      rows,
            "count":        len(rows),
            "used_domains": include_domains or settings.firecrawl_allowed_domains_list,
            "source":       "firecrawl",
        })

    except Exception as exc:
        return BaseTool.err(f"Firecrawl search failed: {exc}")


# ── Tavily fallback implementation ────────────────────────────────────────────

async def _search_tavily(
    query: str,
    max_results: int,
    include_domains: list[str],
) -> dict:
    try:
        import httpx

        payload: dict[str, Any] = {
            "api_key":             settings.TAVILY_API_KEY,
            "query":               query,
            "max_results":         max_results,
            "search_depth":        "basic",
            "include_answer":      False,
            "include_raw_content": False,
            "include_images":      False,
        }
        if include_domains:
            payload["include_domains"] = include_domains

        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.post("https://api.tavily.com/search", json=payload)
            resp.raise_for_status()
            body = resp.json()

        rows = []
        for item in body.get("results", []) or []:
            url = str(item.get("url") or "")
            rows.append({
                "title":   item.get("title") or "",
                "url":     url,
                "domain":  _normalize_domain(url),
                "content": item.get("content") or "",   # snippet only
            })

        return BaseTool.ok({
            "query":        query,
            "results":      rows,
            "count":        len(rows),
            "used_domains": include_domains or settings.firecrawl_allowed_domains_list,
            "source":       "tavily (fallback)",
        })

    except Exception as exc:
        return BaseTool.err(f"Tavily search also failed: {exc}")
