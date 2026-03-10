"""
app/services/scraper_client_service.py

Thin synchronous HTTP client that delegates scraping tasks to the Oracle Cloud VM
scraper service (running at SCRAPER_SERVICE_URL).

Used when SCRAPER_SERVICE_URL is configured in settings.
Falls back gracefully to local Playwright when SCRAPER_SERVICE_URL is empty.

Functions
---------
is_scraper_remote()                        → True if Oracle VM routing is enabled
scrape_case(case_id)                       → POST /scrape/case/{case_id}  — fetch + DB write on VM
scrape_cause_list(user_id, date_str)       → POST /scrape/cause-list — fetch + DB write on VM
scrape_full_cause_list_url(target_date)    → POST /scrape/full-cause-list-url — PDF URL for date
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


# ── Ad-hoc case query by case number (no DB write) ───────────────────────────

def scrape_query_by_case_number(case_number: str) -> Dict[str, Any]:
    """
    Calls the Oracle VM's POST /scrape/query endpoint.
    Used for the case-status-check page — no DB case required, no DB write.

    Oracle VM returns raw court data + hearing history parsed from HTML.
    Railway performs Bedrock enrichment here (credentials are valid on Railway).
    Returns the same dict shape as case_sync_service.query_case_status().
    """
    from datetime import datetime
    from app.services.bedrock_case_enrichment_service import bedrock_case_enrichment_service
    from app.services.case_sync_service import CaseSyncService

    url = f"{_base_url()}/scrape/query"
    timeout = float(settings.SCRAPER_SERVICE_TIMEOUT)

    logger.info("scraper_client: delegating ad-hoc query to Oracle VM — case_number=%s", case_number)
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, headers=_headers(), json={"case_number": case_number})
        resp.raise_for_status()
        data: Dict[str, Any] = resp.json()
    except httpx.HTTPStatusError as exc:
        logger.error(
            "scraper_client: Oracle VM HTTP error %s for query case_number=%s — %s",
            exc.response.status_code, case_number, exc.response.text,
        )
        raise RuntimeError(
            f"Scraper service error {exc.response.status_code}: {exc.response.text}"
        ) from exc
    except httpx.RequestError as exc:
        logger.error(
            "scraper_client: Could not reach Oracle VM for query case_number=%s — %s",
            case_number, exc,
        )
        raise RuntimeError(f"Could not reach scraper service: {exc}") from exc

    # Oracle VM returns _raw_payload so Railway can enrich with Bedrock
    # (Oracle VM's AWS credentials may be stale; Railway's are always current)
    raw_payload = data.pop("_raw_payload", None)
    if not data.get("found"):
        return data

    if raw_payload:
        enriched = bedrock_case_enrichment_service.enrich_case_data(raw_payload)
        case_sync = CaseSyncService()
        hearing_history = data.get("hearing_history") or enriched.get("hearing_history")
        return {
            "found": True,
            "case_number": case_number,
            "case_type": enriched.get("case_type"),
            "filing_number": enriched.get("filing_number"),
            "filing_date": enriched.get("filing_date"),
            "registration_number": enriched.get("registration_number"),
            "registration_date": enriched.get("registration_date"),
            "cnr_number": enriched.get("cnr_number"),
            "efile_number": enriched.get("efile_number"),
            "first_hearing_date": enriched.get("first_hearing_date"),
            "status_text": enriched.get("court_status"),
            "coram": enriched.get("coram"),
            "stage": enriched.get("bench"),
            "last_order_date": enriched.get("last_hearing_date"),
            "next_hearing_date": enriched.get("next_hearing_date"),
            "last_listed_date": enriched.get("last_listed_date"),
            "last_listed_bench": enriched.get("last_listed_bench"),
            "last_listed_list": enriched.get("last_listed_list"),
            "last_listed_item": enriched.get("last_listed_item"),
            "petitioner_name": enriched.get("petitioner"),
            "petitioner_advocates": enriched.get("petitioner_advocates"),
            "respondent_name": enriched.get("respondent"),
            "respondent_advocates": enriched.get("respondent_advocates"),
            "served_on": enriched.get("served_on"),
            "acts": enriched.get("acts"),
            "sections": enriched.get("sections"),
            "hearing_history": hearing_history,
            "interim_orders": enriched.get("interim_orders"),
            "category_details": enriched.get("category_details"),
            "objections": enriched.get("objections"),
            "summary": enriched.get("raw_summary"),
            "source_url": data.get("source_url", ""),
            "full_details_url": data.get("full_details_url"),
            "fetched_at": datetime.utcnow(),
            "message": "Case status fetched",
        }

    # Fallback: Oracle VM returned pre-enriched result (old behaviour)
    return data


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


# ── Full daily cause list PDF URL ─────────────────────────────────────────────

def scrape_full_cause_list_url(target_date: str) -> Dict[str, Any]:
    """
    Calls the Oracle VM's POST /scrape/full-cause-list-url endpoint.

    The Oracle VM:
      1. GETs hckinfo viewCauselist (seeds session/cookies)
      2. POSTs to clistbyDate with the date
      3. Parses the HTML response to find the "VIEW LATEST ENTIRE LIST (DAILY)" PDF link
      4. Returns {"ok": True, "pdf_url": "<url>", "date": "<YYYY-MM-DD>"}

    Raises RuntimeError on HTTP or connection errors.
    """
    url = f"{_base_url()}/scrape/full-cause-list-url"
    timeout = float(settings.SCRAPER_SERVICE_TIMEOUT)

    logger.info(
        "scraper_client: delegating full-cause-list-url to Oracle VM — date=%s",
        target_date,
    )
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(
                url,
                headers=_headers(),
                json={"date": target_date},
            )
        resp.raise_for_status()
        data: Dict[str, Any] = resp.json()
        logger.info(
            "scraper_client: Oracle VM full-cause-list-url done — date=%s pdf_url=%s",
            target_date, data.get("pdf_url"),
        )
        return data

    except httpx.HTTPStatusError as exc:
        logger.error(
            "scraper_client: Oracle VM HTTP error %s for full-cause-list-url date=%s — %s",
            exc.response.status_code, target_date, exc.response.text,
        )
        raise RuntimeError(
            f"Scraper service error {exc.response.status_code}: {exc.response.text}"
        ) from exc

    except httpx.RequestError as exc:
        logger.error(
            "scraper_client: Could not reach Oracle VM for full-cause-list-url date=%s — %s",
            target_date, exc,
        )
        raise RuntimeError(f"Could not reach scraper service: {exc}") from exc
