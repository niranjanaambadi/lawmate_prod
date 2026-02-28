"""
services/advocate_causelist_service.py

Fetches advocate-wise cause list from hckinfo.keralacourts.in/digicourt
using the direct POST API endpoint (no CSRF dance required).

API endpoint:
  POST https://hckinfo.keralacourts.in/digicourt/index.php/Casedetailssearch/Casebyadv1

Payload (form-encoded):
  advocate_name  — base64( url_encode( "FULLNAME(ENROLLMENT)" ) )
                   e.g. base64("SANJAY%20JOHNSON(K%2F000671%2F2018)")
  from_date      — YYYY-MM-DD
  adv_cd         — numeric advocate code from hckinfo

Freshness strategy:
  - Scheduler calls this at 7:15 PM IST for ALL users, using tomorrow's date.
  - Manual refresh available via API.
  - Past dates served from DB cache by the tool.

DB: upserts into advocate_cause_lists with unique constraint
    (lawyer_id, advocate_name, date, case_no) — fully idempotent.
"""

from __future__ import annotations

import base64
import logging
import re
from datetime import date, datetime
from typing import Optional
from urllib.parse import quote
from uuid import UUID

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db.models import AdvocateCauseList, AdvocateCauseListFetchStatus

logger = logging.getLogger(__name__)

BASE_URL    = "https://hckinfo.keralacourts.in"
API_URL     = f"{BASE_URL}/digicourt/index.php/Casedetailssearch/Casebyadv1"
SEARCH_PAGE = f"{BASE_URL}/digicourt/Casedetailssearch/Advocatesearch"
# jQuery UI autocomplete endpoint used by the search page
AUTOCOMPLETE_URL = f"{BASE_URL}/digicourt/index.php/Casedetailssearch/getadvocatename"
TIMEOUT     = 25.0

# Realistic browser headers — site rejects bare httpx user agents
HEADERS = {
    "User-Agent":   (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer":         SEARCH_PAGE,
    "Origin":          BASE_URL,
    "Content-Type":    "application/x-www-form-urlencoded",
}


# ============================================================================
# Public interface
# ============================================================================

def build_advocate_name_param(full_name: str, enrollment_number: str) -> str:
    """
    Builds the base64-encoded advocate_name parameter expected by the API.

    Format: base64( url_encode( "FULL NAME(ENROLLMENT)" ) )
    Example: base64("SANJAY%20JOHNSON(K%2F000671%2F2018)")
           → "U0FOSkFZJTIwSk9ITlNPTihLJTJGMDAwNjcxJTJGMjAxOCk="
    """
    combined   = f"{full_name.strip().upper()}({enrollment_number.strip()})"
    url_encoded = quote(combined, safe="")
    return base64.b64encode(url_encoded.encode()).decode()


async def lookup_advocate_code(advocate_name: str, enrollment_number: str = "") -> str | None:
    """
    Auto-detects the numeric adv_cd for an advocate from hckinfo digicourt.

    Strategy (tries each in order, returns first hit):
      1. jQuery UI autocomplete endpoint (getadvocatename?term=...)
         — returns JSON [{label: "NAME(ENROLLMENT)", value: "adv_cd"}, ...]
      2. Form-based search: GET search page → POST with name → parse <select> / <option>
      3. Form-based search: parse result HTML table for embedded adv_cd values

    Args:
        advocate_name:     Full name as on KHC (e.g. "SANJAY JOHNSON")
        enrollment_number: KHC enrollment (e.g. "K/000671/2018") — used to pick
                           the right match when multiple advocates share a name

    Returns:
        adv_cd string (e.g. "25126") or None if not found
    """
    name_upper = advocate_name.strip().upper()

    async with httpx.AsyncClient(
        headers=HEADERS,
        timeout=TIMEOUT,
        follow_redirects=True,
    ) as client:

        # ── Strategy 1: autocomplete JSON endpoint ───────────────────────────
        try:
            resp = await client.get(
                AUTOCOMPLETE_URL,
                params={"term": name_upper[:10]},   # partial match
                headers={**HEADERS, "Accept": "application/json, text/javascript, */*"},
            )
            if resp.status_code == 200:
                data = resp.json()
                # Expected: [{"label": "SANJAY JOHNSON(K/000671/2018)", "value": "25126"}, ...]
                if isinstance(data, list):
                    match = _best_autocomplete_match(data, name_upper, enrollment_number)
                    if match:
                        logger.info("adv_cd lookup via autocomplete: %s → %s", name_upper, match)
                        return match
        except Exception as exc:
            logger.debug("Autocomplete lookup failed (%s), trying form search", exc)

        # ── Strategy 2: form-based search → parse <select> / <option> ────────
        try:
            # GET the search page for CSRF token
            page_resp = await client.get(SEARCH_PAGE)
            csrf = _extract_csrf(page_resp.text)

            post_resp = await client.post(
                SEARCH_PAGE,
                data={
                    "_token":        csrf,
                    "advocate_name": name_upper,
                    "search_type":   "advocate",
                },
            )
            code = _parse_adv_cd_from_html(post_resp.text, name_upper, enrollment_number)
            if code:
                logger.info("adv_cd lookup via form search: %s → %s", name_upper, code)
                return code
        except Exception as exc:
            logger.debug("Form-based adv_cd lookup failed: %s", exc)

    logger.warning("Could not auto-detect adv_cd for %s", name_upper)
    return None


# ── Lookup helpers ────────────────────────────────────────────────────────────

def _best_autocomplete_match(
    items: list[dict],
    name_upper: str,
    enrollment: str,
) -> str | None:
    """
    Pick the best match from a jQuery UI autocomplete response.
    Each item is {"label": "FULL NAME(ENROLLMENT)", "value": "adv_cd"}.
    """
    enrollment_clean = enrollment.strip().upper()

    for item in items:
        label = str(item.get("label", "")).upper()
        value = str(item.get("value", "")).strip()
        if not value:
            continue

        # Exact enrollment match is the strongest signal
        if enrollment_clean and enrollment_clean in label:
            return value

        # Fallback: name starts-with match
        if label.startswith(name_upper):
            return value

    return None


def _extract_csrf(html: str) -> str:
    """Extract Laravel CSRF token from page HTML."""
    soup = BeautifulSoup(html, "html.parser")
    token = soup.find("input", {"name": "_token"})
    if token and token.get("value"):
        return token["value"]
    meta = soup.find("meta", {"name": "csrf-token"})
    if meta and meta.get("content"):
        return meta["content"]
    return ""


def _parse_adv_cd_from_html(
    html: str,
    name_upper: str,
    enrollment: str,
) -> str | None:
    """
    Parses advocate search result HTML for the adv_cd.

    Handles two common patterns:
      A) <select name="adv_cd"><option value="25126">SANJAY JOHNSON(...)</option></select>
      B) <input type="hidden" name="adv_cd" value="25126"> near the advocate name
      C) Table row with adv_cd embedded in a form/link
    """
    soup = BeautifulSoup(html, "html.parser")
    enrollment_clean = enrollment.strip().upper()

    # Pattern A: <select> with options
    for select in soup.find_all("select"):
        for option in select.find_all("option"):
            label = option.get_text(strip=True).upper()
            value = str(option.get("value", "")).strip()
            if not value or not value.isdigit():
                continue
            if enrollment_clean and enrollment_clean in label:
                return value
            if name_upper in label:
                return value

    # Pattern B: hidden input named adv_cd
    hidden = soup.find("input", {"name": "adv_cd"})
    if hidden and hidden.get("value"):
        return str(hidden["value"]).strip()

    # Pattern C: any element whose text contains the name with a nearby numeric id
    #            look for data-adv-cd or data-id attributes on table rows
    for tag in soup.find_all(attrs={"data-adv-cd": True}):
        label = tag.get_text(separator=" ", strip=True).upper()
        if name_upper in label:
            return str(tag["data-adv-cd"]).strip()

    for tag in soup.find_all(attrs={"data-id": True}):
        label = tag.get_text(separator=" ", strip=True).upper()
        if name_upper in label and str(tag["data-id"]).isdigit():
            if not enrollment_clean or enrollment_clean in label:
                return str(tag["data-id"]).strip()

    return None


async def fetch_and_store_advocate_causelist(
    advocate_name:     str,
    target_date:       date,
    lawyer_id:         str,
    db:                Session,
    enrollment_number: str = "",
    advocate_code:     str = "",
) -> list[AdvocateCauseList]:
    """
    Calls the hckinfo POST API and upserts results into DB.

    Args:
        advocate_name:     Full name as registered with KHC (e.g. "SANJAY JOHNSON")
        target_date:       Date to fetch cause list for (usually tomorrow)
        lawyer_id:         UUID string — used as FK on each row
        db:                SQLAlchemy session
        enrollment_number: KHC enrollment e.g. "K/000671/2018" (used in name param)
        advocate_code:     hckinfo adv_cd numeric code e.g. "25126"

    Returns:
        List of upserted AdvocateCauseList ORM rows

    Raises:
        Exception on HTTP/parse failure — caller should catch and log
    """
    # Build the encoded advocate_name parameter
    if enrollment_number:
        enc_name = build_advocate_name_param(advocate_name, enrollment_number)
    else:
        # Fall back: base64 of the plain name if no enrollment stored
        enc_name = base64.b64encode(advocate_name.upper().encode()).decode()

    # Full identifier string stored in DB rows for cache lookups
    db_advocate_name = (
        f"{advocate_name.strip().upper()}({enrollment_number.strip()})"
        if enrollment_number
        else advocate_name.strip().upper()
    )

    logger.info(
        "Fetching advocate cause list: %s  date=%s  adv_cd=%s",
        db_advocate_name, target_date, advocate_code,
    )

    rows = await _fetch(enc_name, target_date, advocate_code)

    if not rows:
        logger.info("No listings found for %s on %s", db_advocate_name, target_date)
        return []

    upserted = _upsert_rows(
        db=db,
        rows=rows,
        lawyer_id=lawyer_id,
        db_advocate_name=db_advocate_name,
        advocate_code=advocate_code,
        target_date=target_date,
    )

    logger.info(
        "Upserted %d cause list rows for %s on %s",
        len(upserted), db_advocate_name, target_date,
    )
    return upserted


# ============================================================================
# HTTP fetch
# ============================================================================

async def _fetch(enc_name: str, target_date: date, adv_cd: str) -> list[dict]:
    """
    POSTs to the Casebyadv1 endpoint and parses the HTML table response.
    """
    form_data = {
        "advocate_name": enc_name,
        "from_date":     target_date.strftime("%Y-%m-%d"),
        "adv_cd":        adv_cd,
    }

    async with httpx.AsyncClient(
        headers=HEADERS,
        timeout=TIMEOUT,
        follow_redirects=True,
    ) as client:
        resp = await client.post(API_URL, data=form_data)
        resp.raise_for_status()

    return _parse_table(resp.text, target_date)


# ============================================================================
# HTML parser
# ============================================================================

def _parse_table(html: str, target_date: date) -> list[dict]:
    """
    Parses the response HTML table.

    Expected columns (Kerala HC digicourt):
      Item No | Court Hall | Bench | List Type | Judge Name | Case No | Petitioner | Respondent
    """
    soup  = BeautifulSoup(html, "html.parser")
    table = soup.find("table")

    if not table:
        body_text = soup.get_text(separator=" ", strip=True).lower()
        if any(p in body_text for p in ["no record", "no case", "not found", "no data"]):
            return []
        logger.warning("No table found in hckinfo response — may be a site change or empty list")
        return []

    rows   = table.find_all("tr")
    result = []

    for row in rows[1:]:          # skip header
        cols = row.find_all("td")
        if len(cols) < 6:
            continue

        texts = [c.get_text(separator=" ", strip=True) for c in cols]

        item_no_raw       = texts[0] if len(texts) > 0 else ""
        court_hall        = texts[1] if len(texts) > 1 else ""
        bench             = texts[2] if len(texts) > 2 else ""
        list_type         = texts[3] if len(texts) > 3 else ""
        judge_name        = texts[4] if len(texts) > 4 else ""
        case_no           = texts[5] if len(texts) > 5 else ""
        petitioner        = texts[6] if len(texts) > 6 else ""
        respondent        = texts[7] if len(texts) > 7 else ""

        result.append({
            "date":             target_date,
            "item_no":          _parse_int(item_no_raw),
            "court_hall":       court_hall or None,
            "court_hall_number": _extract_court_hall_number(court_hall),
            "bench":            bench or None,
            "list_type":        list_type or None,
            "judge_name":       judge_name or None,
            "case_no":          case_no or None,
            "petitioner":       (petitioner[:500] if petitioner else None),
            "respondent":       (respondent[:500] if respondent else None),
        })

    return result


# ============================================================================
# DB upsert
# ============================================================================

def _upsert_rows(
    db:               Session,
    rows:             list[dict],
    lawyer_id:        str,
    db_advocate_name: str,
    advocate_code:    str,
    target_date:      date,
) -> list[AdvocateCauseList]:
    """
    PostgreSQL ON CONFLICT DO UPDATE upsert.
    Unique constraint: uq_advocate_cause_lists_lawyer_adv_date_case
    """
    now = datetime.utcnow()

    for row in rows:
        stmt = pg_insert(AdvocateCauseList).values(
            lawyer_id=UUID(lawyer_id),
            advocate_name=db_advocate_name,
            advocate_code=advocate_code or None,
            date=row["date"],
            item_no=row["item_no"],
            court_hall=row["court_hall"],
            court_hall_number=row["court_hall_number"],
            bench=row["bench"],
            list_type=row["list_type"],
            judge_name=row["judge_name"],
            case_no=row["case_no"],
            petitioner=row["petitioner"],
            respondent=row["respondent"],
            fetch_status=AdvocateCauseListFetchStatus.fetched,
            fetch_error=None,
            source_url=API_URL,
            fetched_at=now,
        ).on_conflict_do_update(
            constraint="uq_advocate_cause_lists_lawyer_adv_date_case",
            set_={
                "item_no":           pg_insert(AdvocateCauseList).excluded.item_no,
                "court_hall":        pg_insert(AdvocateCauseList).excluded.court_hall,
                "court_hall_number": pg_insert(AdvocateCauseList).excluded.court_hall_number,
                "bench":             pg_insert(AdvocateCauseList).excluded.bench,
                "list_type":         pg_insert(AdvocateCauseList).excluded.list_type,
                "judge_name":        pg_insert(AdvocateCauseList).excluded.judge_name,
                "petitioner":        pg_insert(AdvocateCauseList).excluded.petitioner,
                "respondent":        pg_insert(AdvocateCauseList).excluded.respondent,
                "fetch_status":      pg_insert(AdvocateCauseList).excluded.fetch_status,
                "fetch_error":       None,
                "source_url":        pg_insert(AdvocateCauseList).excluded.source_url,
                "fetched_at":        pg_insert(AdvocateCauseList).excluded.fetched_at,
                "updated_at":        now,
            },
        )
        db.execute(stmt)

    db.commit()

    return (
        db.query(AdvocateCauseList)
        .filter(
            AdvocateCauseList.lawyer_id     == UUID(lawyer_id),
            AdvocateCauseList.advocate_name == db_advocate_name,
            AdvocateCauseList.date          == target_date,
        )
        .order_by(AdvocateCauseList.item_no)
        .all()
    )


# ============================================================================
# Helpers
# ============================================================================

def _parse_int(value: str) -> Optional[int]:
    if not value:
        return None
    m = re.search(r"\d+", value)
    return int(m.group()) if m else None


def _extract_court_hall_number(court_hall: str) -> Optional[int]:
    """Extracts numeric hall number from 'Court Hall 5', 'CH-12', etc."""
    if not court_hall:
        return None
    m = re.search(r"\d+", court_hall)
    return int(m.group()) if m else None
