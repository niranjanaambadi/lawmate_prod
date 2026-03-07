"""
Lawmate Scraper Service
=======================
Runs on Oracle Cloud VM (Mumbai) for Indian IP access to KHC court portals.

Scheduled jobs (IST):
  - Case status sync    : 5:00 AM | 2:00 PM | 6:30 PM  (all active cases, all users)
  - Advocate cause list : 7:15 PM                       (per user with KHC code)
  - Daily cause list PDF: 6:45 PM | 7:15 PM             (once globally → S3 → DB)

HTTP endpoints (secured with x-scraper-secret header):
  GET  /health
  POST /scrape/case/{case_id}   — on-demand single case refresh
  POST /scrape/cause-list       — on-demand cause list for one user
  POST /scrape/daily-pdf        — on-demand daily PDF fetch
"""

from __future__ import annotations

import logging
import os
import re
import time
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, Header, HTTPException
from sqlalchemy.orm import Session

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("scraper_service")

IST = ZoneInfo("Asia/Kolkata")

# ── Shared secret (Railway → Oracle VM auth) ──────────────────────────────────
SCRAPER_SERVICE_SECRET = os.getenv("SCRAPER_SERVICE_SECRET", "").strip()


def _require_secret(x_scraper_secret: str = Header(...)) -> None:
    if not SCRAPER_SERVICE_SECRET:
        raise HTTPException(500, "SCRAPER_SERVICE_SECRET not configured on scraper service")
    if x_scraper_secret != SCRAPER_SERVICE_SECRET:
        raise HTTPException(403, "Invalid scraper secret")


# ── Lazy imports (after env is loaded by config) ───────────────────────────────
def _get_db() -> Session:
    from app.db.database import SessionLocal
    return SessionLocal()


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


def _build_case_number_for_lookup(case: Any) -> Optional[str]:
    case_type = (case.case_type or "").strip()
    case_year = str(case.case_year or "").strip()
    raw_case_no = (case.case_number or "").strip()
    if not case_type or not re.fullmatch(r"\d{4}", case_year):
        return None
    m = re.search(r"(\d+)\s*/\s*\d{4}\s*$", raw_case_no)
    case_no = m.group(1).strip() if m else ""
    if not case_no:
        first_num = re.search(r"\d+", raw_case_no)
        case_no = first_num.group(0).strip() if first_num else ""
    if not case_no:
        return None
    return f"{case_type} {case_no}/{case_year}"


# ══════════════════════════════════════════════════════════════════════════════
# SCHEDULED JOB 1 — Case status sync (all active cases, all users)
# Runs: 5:00 AM | 2:00 PM | 6:30 PM IST
# ══════════════════════════════════════════════════════════════════════════════

def run_case_status_sync() -> None:
    """
    Fetches latest court status for every active (pending/filed/registered) case
    across ALL users and writes results directly to the Railway DB.
    Adds a 2-second delay between cases to avoid hammering the court portal.
    """
    logger.info("JOB case_status_sync — starting")

    from app.db.models import Case, CaseStatus
    from app.services.case_sync_service import CaseSyncService

    case_sync = CaseSyncService()
    db = _get_db()

    try:
        active_statuses = [CaseStatus.pending, CaseStatus.filed, CaseStatus.registered]
        cases = (
            db.query(Case)
            .filter(Case.status.in_(active_statuses), Case.is_visible == True)
            .order_by(Case.last_synced_at.asc().nullsfirst())   # least-recently synced first
            .all()
        )

        logger.info("JOB case_status_sync — %d cases to process", len(cases))
        refreshed = failed = skipped = 0

        for c in cases:
            case_number = _build_case_number_for_lookup(c)
            if not case_number:
                skipped += 1
                continue

            try:
                result = case_sync.query_case_status(case_number)
                if not result.get("found"):
                    failed += 1
                    logger.warning("case_status_sync: not found — %s", case_number)
                    continue

                now = datetime.utcnow()
                c.court_status   = result.get("status_text") or c.court_status
                c.bench_type     = result.get("stage") or c.bench_type
                c.judge_name     = result.get("coram") or c.judge_name
                c.last_synced_at = now
                c.sync_status    = "synced"
                c.sync_error     = None
                if result.get("next_hearing_date"):
                    c.next_hearing_date = result["next_hearing_date"]
                if result.get("petitioner_name"):
                    c.petitioner_name = result["petitioner_name"]
                if result.get("respondent_name"):
                    c.respondent_name = result["respondent_name"]
                c.khc_source_url = (
                    result.get("full_details_url")
                    or result.get("source_url")
                    or c.khc_source_url
                )
                c.raw_court_data = _json_safe(result)

                db.commit()
                refreshed += 1
                logger.info("case_status_sync: updated — %s", case_number)

            except Exception as exc:
                failed += 1
                db.rollback()
                logger.exception("case_status_sync: error on %s — %s", case_number, exc)

            time.sleep(2)   # be polite to the court portal

        logger.info(
            "JOB case_status_sync — done. refreshed=%d failed=%d skipped=%d",
            refreshed, failed, skipped,
        )

    except Exception as exc:
        logger.exception("JOB case_status_sync — fatal: %s", exc)
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════════════════
# SCHEDULED JOB 2 — Advocate cause list (per user, tomorrow's date)
# Runs: 7:15 PM IST
# ══════════════════════════════════════════════════════════════════════════════

async def run_advocate_causelist_sync() -> None:
    """
    Fetches tomorrow's cause list from hckinfo for every user who has their
    KHC advocate code configured in their profile.
    """
    logger.info("JOB advocate_causelist_sync — starting")

    from app.db.models import User
    from app.services.advocate_causelist_service import fetch_and_store_advocate_causelist

    tomorrow = (datetime.now(IST) + timedelta(days=1)).date()
    db = _get_db()

    try:
        users = (
            db.query(User)
            .filter(
                User.khc_advocate_code != None,
                User.khc_advocate_code != "",
                User.is_active == True,
            )
            .all()
        )

        logger.info(
            "JOB advocate_causelist_sync — %d users with KHC code, date=%s",
            len(users), tomorrow,
        )

        success = failed = 0
        for user in users:
            try:
                rows = await fetch_and_store_advocate_causelist(
                    advocate_name=user.khc_advocate_name or "",
                    target_date=tomorrow,
                    lawyer_id=str(user.id),
                    db=db,
                    enrollment_number=user.khc_enrollment_number or "",
                    advocate_code=user.khc_advocate_code or "",
                )
                success += 1
                logger.info(
                    "advocate_causelist_sync: %s — %d rows",
                    user.khc_advocate_name, len(rows),
                )
            except Exception as exc:
                failed += 1
                logger.exception(
                    "advocate_causelist_sync: error for user %s — %s",
                    user.id, exc,
                )

            time.sleep(1)   # brief pause between users

        logger.info(
            "JOB advocate_causelist_sync — done. success=%d failed=%d",
            success, failed,
        )

    except Exception as exc:
        logger.exception("JOB advocate_causelist_sync — fatal: %s", exc)
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════════════════
# SCHEDULED JOB 3 — Daily cause list PDF (global, once for everyone → S3)
# Runs: 6:45 PM | 7:15 PM IST
# ══════════════════════════════════════════════════════════════════════════════

def run_daily_pdf_sync() -> None:
    """
    Fetches the KHC daily cause list PDFs and stores them in S3.
    Runs twice (6:45 PM + 7:15 PM) to catch first wave and any stragglers.
    """
    logger.info("JOB daily_pdf_sync — starting")

    from app.services.daily_pdf_fetch_service import DailyPdfFetchService

    db = _get_db()
    try:
        service = DailyPdfFetchService()
        stats = service.fetch_daily_pdfs_to_s3(db=db, max_tabs=3)
        logger.info(
            "JOB daily_pdf_sync — done. fetched=%d runs=%d failed=%d",
            stats.fetched, stats.runs, stats.failed_runs,
        )
    except Exception as exc:
        logger.exception("JOB daily_pdf_sync — fatal: %s", exc)
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════════════════
# APScheduler setup
# ══════════════════════════════════════════════════════════════════════════════

_scheduler: AsyncIOScheduler | None = None


def _start_scheduler() -> None:
    global _scheduler
    _scheduler = AsyncIOScheduler(timezone=IST)

    # Case status — 5:00 AM IST
    _scheduler.add_job(
        run_case_status_sync,
        CronTrigger(hour=5, minute=0, timezone=IST),
        id="case_status_0500",
        max_instances=1,
        misfire_grace_time=600,
    )
    # Case status — 2:00 PM IST
    _scheduler.add_job(
        run_case_status_sync,
        CronTrigger(hour=14, minute=0, timezone=IST),
        id="case_status_1400",
        max_instances=1,
        misfire_grace_time=600,
    )
    # Case status — 6:30 PM IST
    _scheduler.add_job(
        run_case_status_sync,
        CronTrigger(hour=18, minute=30, timezone=IST),
        id="case_status_1830",
        max_instances=1,
        misfire_grace_time=600,
    )

    # Advocate cause list — 7:15 PM IST
    _scheduler.add_job(
        run_advocate_causelist_sync,
        CronTrigger(hour=19, minute=15, timezone=IST),
        id="causelist_1915",
        max_instances=1,
        misfire_grace_time=300,
    )

    # Daily cause list PDF — 6:45 PM IST (first wave)
    _scheduler.add_job(
        run_daily_pdf_sync,
        CronTrigger(hour=18, minute=45, timezone=IST),
        id="daily_pdf_1845",
        max_instances=1,
        misfire_grace_time=300,
    )
    # Daily cause list PDF — 7:15 PM IST (catch stragglers)
    _scheduler.add_job(
        run_daily_pdf_sync,
        CronTrigger(hour=19, minute=15, timezone=IST),
        id="daily_pdf_1915",
        max_instances=1,
        misfire_grace_time=300,
    )

    _scheduler.start()
    logger.info("Scheduler started — 6 jobs registered")


# ══════════════════════════════════════════════════════════════════════════════
# FastAPI app
# ══════════════════════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    _start_scheduler()
    yield
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)


app = FastAPI(title="Lawmate Scraper Service", lifespan=lifespan)


@app.get("/health")
def health():
    return {"ok": True, "service": "lawmate-scraper", "time_ist": datetime.now(IST).isoformat()}


# ── On-demand: single case status refresh ─────────────────────────────────────

@app.post("/scrape/case/{case_id}")
def scrape_case(case_id: str, x_scraper_secret: str = Header(...)) -> Dict[str, Any]:
    _require_secret(x_scraper_secret)

    from app.db.models import Case
    from app.services.case_sync_service import CaseSyncService

    db = _get_db()
    try:
        case = db.query(Case).filter(Case.id == case_id, Case.is_visible == True).first()
        if not case:
            raise HTTPException(404, "Case not found")

        case_number = _build_case_number_for_lookup(case)
        if not case_number:
            raise HTTPException(422, "Case has incomplete details for lookup")

        case_sync = CaseSyncService()
        result = case_sync.query_case_status(case_number)
        if not result.get("found"):
            return {"found": False, "case_id": case_id}

        now = datetime.utcnow()
        case.court_status   = result.get("status_text") or case.court_status
        case.bench_type     = result.get("stage") or case.bench_type
        case.judge_name     = result.get("coram") or case.judge_name
        case.last_synced_at = now
        case.sync_status    = "synced"
        case.sync_error     = None
        if result.get("next_hearing_date"):
            case.next_hearing_date = result["next_hearing_date"]
        if result.get("petitioner_name"):
            case.petitioner_name = result["petitioner_name"]
        if result.get("respondent_name"):
            case.respondent_name = result["respondent_name"]
        case.khc_source_url = result.get("full_details_url") or result.get("source_url") or case.khc_source_url
        case.raw_court_data = _json_safe(result)
        db.commit()

        # Return the full enriched result so the Railway backend can pass it
        # directly to the frontend (same shape as case_sync_service.query_case_status).
        return {
            "found": True,
            "case_id": case_id,
            "case_number": case_number,
            **_json_safe(result),
        }

    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("on-demand case scrape failed: %s", exc)
        raise HTTPException(500, str(exc))
    finally:
        db.close()


# ── On-demand: ad-hoc case query by case number (no DB write) ─────────────────

@app.post("/scrape/query")
def scrape_query(payload: Dict[str, Any], x_scraper_secret: str = Header(...)) -> Dict[str, Any]:
    """
    Ad-hoc case status lookup by case_number string (e.g. 'Mat.Appeal 80/2024').
    Does NOT require the case to exist in the DB and does NOT write back to DB.
    Used by the case-status-check page on Railway.
    """
    _require_secret(x_scraper_secret)
    case_number = (payload.get("case_number") or "").strip()
    if not case_number:
        raise HTTPException(422, "case_number is required")

    from app.services.case_sync_service import CaseSyncService
    try:
        case_sync = CaseSyncService()
        result = case_sync.query_case_status(case_number)
        return result or {"found": False, "case_number": case_number}
    except Exception as exc:
        logger.exception("ad-hoc case query failed: %s", exc)
        raise HTTPException(500, str(exc))


# ── On-demand: advocate cause list for one user ───────────────────────────────

@app.post("/scrape/cause-list")
async def scrape_cause_list(
    payload: Dict[str, Any],
    x_scraper_secret: str = Header(...),
) -> Dict[str, Any]:
    _require_secret(x_scraper_secret)

    from app.db.models import User
    from app.services.advocate_causelist_service import fetch_and_store_advocate_causelist

    user_id: str = payload.get("user_id", "")
    target_date_str: str = payload.get("date", "")

    if not user_id:
        raise HTTPException(422, "user_id required")

    target_date = (
        date.fromisoformat(target_date_str)
        if target_date_str
        else (datetime.now(IST) + timedelta(days=1)).date()
    )

    db = _get_db()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(404, "User not found")
        if not user.khc_advocate_code:
            raise HTTPException(422, "User has no KHC advocate code configured")

        rows = await fetch_and_store_advocate_causelist(
            advocate_name=user.khc_advocate_name or "",
            target_date=target_date,
            lawyer_id=str(user.id),
            db=db,
            enrollment_number=user.khc_enrollment_number or "",
            advocate_code=user.khc_advocate_code or "",
        )
        return {"ok": True, "rows": len(rows), "date": str(target_date)}

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("on-demand cause list scrape failed: %s", exc)
        raise HTTPException(500, str(exc))
    finally:
        db.close()


# ── On-demand: daily cause list PDF ──────────────────────────────────────────

@app.post("/scrape/daily-pdf")
def scrape_daily_pdf(x_scraper_secret: str = Header(...)) -> Dict[str, Any]:
    _require_secret(x_scraper_secret)

    from app.services.daily_pdf_fetch_service import DailyPdfFetchService

    db = _get_db()
    try:
        stats = DailyPdfFetchService().fetch_daily_pdfs_to_s3(db=db, max_tabs=3)
        return {
            "ok": True,
            "fetched": stats.fetched,
            "runs": stats.runs,
            "failed_runs": stats.failed_runs,
        }
    except Exception as exc:
        logger.exception("on-demand daily PDF scrape failed: %s", exc)
        raise HTTPException(500, str(exc))
    finally:
        db.close()
