"""
agent/tools/read_url.py

Reads the full content of a legal URL via Firecrawl and returns
cleaned markdown. Enables the agent to read IndianKanoon judgments,
Bar & Bench articles, SCI orders, and KHC notifications in full —
not just snippets.

Allowed domains: curated list of trusted legal sources.
Content is truncated to FIRECRAWL_MAX_CONTENT_CHARS to stay within
the agent's context window.
"""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from app.agent.tools.registry import BaseTool
from app.core.config import settings

logger = logging.getLogger(__name__)

# Trusted legal domains — only these can be scraped via this tool.
# Add more via READ_URL_ALLOWED_DOMAINS config if needed.
_ALLOWED_DOMAINS: frozenset[str] = frozenset({
    "indiankanoon.org",
    "sci.gov.in",
    "main.sci.gov.in",
    "highcourt.kerala.gov.in",
    "hckinfo.keralacourts.in",
    "livelaw.in",
    "barandbench.com",
    "thehindu.com",
    "theleaflet.in",
    "lawmin.gov.in",
    "indiacode.nic.in",
    "ecourts.gov.in",
    "districts.ecourts.gov.in",
})


def _extract_domain(url: str) -> str:
    """Returns bare hostname without www. prefix."""
    try:
        host = urlparse(url).netloc.lower()
        if ":" in host:
            host = host.split(":")[0]
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""


def _is_allowed(url: str) -> bool:
    domain = _extract_domain(url)
    if not domain:
        return False
    # Exact match or subdomain match (e.g. sub.indiankanoon.org)
    if domain in _ALLOWED_DOMAINS:
        return True
    for allowed in _ALLOWED_DOMAINS:
        if domain.endswith("." + allowed):
            return True
    # Also check FIRECRAWL_ALLOWED_DOMAINS list
    for allowed in settings.firecrawl_allowed_domains_list:
        if domain == allowed or domain.endswith("." + allowed):
            return True
    return False


class ReadUrlTool(BaseTool):
    name = "read_url"
    description = (
        "Fetches and reads the full content of a legal URL — IndianKanoon judgments, "
        "Bar & Bench articles, Supreme Court orders, KHC notifications, bare act pages. "
        "Use when the lawyer shares a URL or when search results return a URL that "
        "needs full text for analysis (ratio decidendi, orders, citations). "
        "Only works on trusted legal domains (IndianKanoon, LiveLaw, BarAndBench, SCI, KHC, etc.). "
        "Returns cleaned markdown of the full page content."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": (
                    "Full URL to read. Must be from a trusted legal domain "
                    "(e.g. https://indiankanoon.org/doc/12345/, "
                    "https://livelaw.in/..., https://barandbench.com/...)."
                ),
            },
        },
        "required": ["url"],
    }

    async def run(self, context: Any, db: Any, **kwargs) -> dict:
        url: str = (kwargs.get("url") or "").strip()

        if not url:
            return self.err("url is required")

        if not settings.FIRECRAWL_API_KEY:
            return self.err(
                "Firecrawl API key not configured. Set FIRECRAWL_API_KEY in environment."
            )

        if not _is_allowed(url):
            domain = _extract_domain(url)
            return self.err(
                f"Domain '{domain}' is not in the trusted legal domain list. "
                "Only IndianKanoon, LiveLaw, BarAndBench, SCI, KHC, and similar "
                "legal sources can be read via this tool."
            )

        try:
            from firecrawl import FirecrawlApp

            app = FirecrawlApp(api_key=settings.FIRECRAWL_API_KEY)

            result = app.scrape_url(
                url,
                formats=["markdown"],
                only_main_content=True,  # strips nav, footer, ads
            )

            markdown: str = getattr(result, "markdown", None) or ""

            if not markdown:
                return self.err(
                    f"Firecrawl returned no content for {url}. "
                    "The page may be behind a login or have no readable text."
                )

            # Truncate to keep context window manageable
            max_chars = settings.FIRECRAWL_MAX_CONTENT_CHARS
            truncated = False
            if len(markdown) > max_chars:
                markdown = markdown[:max_chars]
                truncated = True

            metadata = getattr(result, "metadata", {}) or {}
            title = metadata.get("title") or metadata.get("og:title") or ""

            return self.ok({
                "url":       url,
                "title":     title,
                "content":   markdown,
                "truncated": truncated,
                "char_count": len(markdown),
                "source":    _extract_domain(url),
            })

        except Exception as e:
            logger.warning("ReadUrlTool error for %s: %s", url, e)
            return self.err(f"Could not read URL: {str(e)}")
