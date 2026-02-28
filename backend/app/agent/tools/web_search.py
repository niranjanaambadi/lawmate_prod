"""
agent/tools/web_search.py

Fallback web search via Tavily for supplementary legal references.
This tool is intentionally constrained by an allowlist so the agent
cannot search arbitrary domains.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from app.agent.tools.registry import BaseTool
from app.core.config import settings


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
    allowed = settings.tavily_allowed_domains_list
    if not allowed:
        return []
    if not requested:
        return allowed

    normalized_requested = []
    for item in requested:
        host = _normalize_domain(item)
        if host:
            normalized_requested.append(host)

    filtered = []
    for host in normalized_requested:
        if host in allowed and host not in filtered:
            filtered.append(host)
    return filtered


class WebSearchTool(BaseTool):
    name = "search_web"
    description = (
        "Searches the web for supplementary legal updates and references using Tavily. "
        "Use only when DB tools and judgment/resource tools are insufficient. "
        "Results are restricted to configured legal domains."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query.",
            },
            "max_results": {
                "type": "integer",
                "description": "Max results to return (default from config, cap 10).",
            },
            "domains": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional domain filter; will be intersected with allowlist.",
            },
        },
        "required": ["query"],
    }

    async def run(self, context: Any, db: Any, **kwargs) -> dict:
        query = (kwargs.get("query") or "").strip()
        if not query:
            return self.err("query is required")

        if not settings.TAVILY_API_KEY:
            return self.err("Tavily API key not configured")

        max_results = kwargs.get("max_results", settings.TAVILY_MAX_RESULTS)
        try:
            max_results = max(1, min(int(max_results), 10))
        except Exception:
            max_results = max(1, min(int(settings.TAVILY_MAX_RESULTS or 5), 10))

        requested_domains = kwargs.get("domains") or []
        if not isinstance(requested_domains, list):
            requested_domains = []
        include_domains = _filter_domains([str(v) for v in requested_domains])
        if settings.tavily_allowed_domains_list and requested_domains and not include_domains:
            return self.err("Requested domains are not in allowed domain list")

        payload: dict[str, Any] = {
            "api_key": settings.TAVILY_API_KEY,
            "query": query,
            "max_results": max_results,
            "search_depth": "basic",
            "include_answer": False,
            "include_raw_content": False,
            "include_images": False,
        }
        if include_domains:
            payload["include_domains"] = include_domains

        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                resp = await client.post("https://api.tavily.com/search", json=payload)
                resp.raise_for_status()
                body = resp.json()
        except Exception as exc:
            return self.err(f"Tavily search failed: {exc}")

        rows = []
        for item in body.get("results", []) or []:
            url = str(item.get("url") or "")
            rows.append(
                {
                    "title": item.get("title") or "",
                    "url": url,
                    "domain": _normalize_domain(url),
                    "snippet": item.get("content") or "",
                    "score": item.get("score"),
                }
            )

        return self.ok(
            {
                "query": query,
                "results": rows,
                "count": len(rows),
                "used_domains": include_domains or settings.tavily_allowed_domains_list,
                "source": "tavily",
            }
        )
