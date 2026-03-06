"""
app/services/scraper_client_service.py

Thin synchronous HTTP client that delegates scraping tasks to the Oracle Cloud VM
scraper service (running at SCRAPER_SERVICE_URL).

Used when SCRAPER_SERVICE_URL is configured in settings.
Falls back gracefully to local Playwright when SCRAPER_SERVICE_URL is empty.

Functions
---------
is_scraper_remote()          → True if Oracle VM routing is enabled
scrape_case(case_id)         → POST /scrape/case/{case_id}  — fetch + DB write on VM
scrape_cause_list(user_id, date_str) → POST /scrape/cause-list — fetch + DB write on VM
"""

from __future__ import annotations

import logging
from typing import Any, Dict

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


def is_scraper_remote() -> bool:
    """
    Returns True when Oracle VM routing is enabled
    (i.e. SCRAPER_SERVICE_URL is non-empty).
    """
    return bool(settings.SCRAPER_SERVICE_URL)


def _headers() -> Dict[str, str]:
    return {"x-scraper-secret": settings.SCRAPER_SERVICE_SECRET}


def _base_url() -> str:
    return settings.SCRAPER_SERVICE_URL.rstrip("/")


# ── Case status refresh ───────────────────────────────────────────────────────

def scrape_case(case_id: str) -> Dict[str, Any]:
    """
    Calls the Oracle VM's POST /scrape/case/{case_id} endpoint.

    The Oracle VM:
      1. Looks up the case in the shared DB
      2. Runs Playwright against hckinfo (Indian IP)
      3. Enriches with Bedrock
      4. Writes the updated fields back to DB
      5. Returns the full result dict (same format as case_sync_service.query_case_status())

    The caller (Railway backend) can pass this dict straight to the frontend
    and skip its own DB write (Oracle VM already handled it).

    Raises RuntimeError on HTTP or connection errors (caller wraps in HTTPException).
    """
    url = f"{_base_url()}/scrape/case/{case_id}"
    timeout = float(settings.SCRAPER_SERVICE_TIMEOUT)

    logger.info("scraper_client: delegating case refresh to Oracle VM — case_id=%s", case_id)
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, headers=_headers())
        resp.raise_for_status()
        data: Dict[str, Any] = resp.json()
        logger.info(
            "scraper_client: Oracle VM returned — case_id=%s found=%s",
            case_id, data.get("found"),
        )
        return data

    except httpx.HTTPStatusError as exc:
        logger.error(
            "scraper_client: Oracle VM HTTP error %s for case_id=%s — %s",
            exc.response.status_code, case_id, exc.response.text,
        )
        raise RuntimeError(
            f"Scraper service error {exc.response.status_code}: {exc.response.text}"
        ) from exc

    except httpx.RequestError as exc:
        logger.error(
            "scraper_client: Could not reach Oracle VM for case_id=%s — %s",
            case_id, exc,
        )
        raise RuntimeError(f"Could not reach scraper service: {exc}") from exc


# ── Advocate cause list refresh ───────────────────────────────────────────────

def scrape_cause_list(user_id: str, target_date: str) -> Dict[str, Any]:
    """
    Calls the Oracle VM's POST /scrape/cause-list endpoint.

    The Oracle VM:
      1. Looks up the user's KHC profile from DB
      2. Fetches from hckinfo (Indian IP, plain HTTP)
      3. Upserts rows into the advocate_cause_lists table
      4. Returns {"ok": True, "rows": <count>, "date": "<YYYY-MM-DD>"}

    After this call, the Railway endpoint re-reads the rows from DB to build
    the response (same pattern as the cached GET endpoint).

    Raises RuntimeError on HTTP or connection errors.
    """
    url = f"{_base_url()}/scrape/cause-list"
    timeout = float(settings.SCRAPER_SERVICE_TIMEOUT)

    logger.info(
        "scraper_client: delegating cause-list fetch to Oracle VM — user_id=%s date=%s",
        user_id, target_date,
    )
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(
                url,
                headers=_headers(),
                json={"user_id": user_id, "date": target_date},
            )
        resp.raise_for_status()
        data: Dict[str, Any] = resp.json()
        logger.info(
            "scraper_client: Oracle VM cause-list done — user_id=%s rows=%s",
            user_id, data.get("rows"),
        )
        return data

    except httpx.HTTPStatusError as exc:
        logger.error(
            "scraper_client: Oracle VM HTTP error %s for cause-list user_id=%s — %s",
            exc.response.status_code, user_id, exc.response.text,
        )
        raise RuntimeError(
            f"Scraper service error {exc.response.status_code}: {exc.response.text}"
        ) from exc

    except httpx.RequestError as exc:
        logger.error(
            "scraper_client: Could not reach Oracle VM for cause-list user_id=%s — %s",
            user_id, exc,
        )
        raise RuntimeError(f"Could not reach scraper service: {exc}") from exc
