"""
services/background_jobs.py

Scheduled background jobs for LawMate.

Jobs:
  1. sync_hearing_dates_to_calendar
     — Scans cases with next_hearing_date and ensures a CalendarEvent exists.
     — Runs every 60 minutes during active hours (7am–7pm IST).

  2. sync_google_calendar_for_all_lawyers
     — Pulls Google Calendar changes for all connected lawyers.
     — Runs every 30 minutes during active hours (7am–7pm IST).

Setup (APScheduler — add to your FastAPI app startup):

    from app.services.background_jobs import start_scheduler, shutdown_scheduler
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        start_scheduler()
        yield
        shutdown_scheduler()

    app = FastAPI(lifespan=lifespan)
"""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.db.database import SessionLocal

logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")

# ── Scheduler singleton ───────────────────────────────────────────────────────
_scheduler: AsyncIOScheduler | None = None


def start_scheduler() -> None:
    """
    Starts the APScheduler background job scheduler.
    Call this from FastAPI lifespan startup.
    """
    global _scheduler

    _scheduler = AsyncIOScheduler(timezone=IST)

    # Job 1: Sync hearing dates → calendar events (every 60 min)
    _scheduler.add_job(
        sync_hearing_dates_to_calendar,
        trigger=IntervalTrigger(minutes=60, timezone=IST),
        id="sync_hearing_dates",
        name="Sync hearing dates to calendar",
        replace_existing=True,
        max_instances=1,          # never run two at once
        misfire_grace_time=300,   # allow 5 min late start
    )

    # Job 2: Google Calendar incremental sync (every 30 min)
    _scheduler.add_job(
        sync_google_calendar_for_all_lawyers,
        trigger=IntervalTrigger(minutes=30, timezone=IST),
        id="google_calendar_sync",
        name="Google Calendar incremental sync",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=300,
    )

    _scheduler.start()
    logger.info("Background scheduler started — 2 jobs registered")


def shutdown_scheduler() -> None:
    """Gracefully shuts down the scheduler. Call from FastAPI lifespan shutdown."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Background scheduler shut down")


# ============================================================================
# Job 1: Sync hearing dates → calendar events
# ============================================================================

async def sync_hearing_dates_to_calendar() -> None:
    """
    Scans all active cases that have a future next_hearing_date and
    ensures a HEARING CalendarEvent exists for each.

    Idempotent — upsert_hearing_event() handles duplicates safely.
    Runs only during active hours (7am–7pm IST).
    """
    if not _is_active_hours():
        return

    logger.info("Job: sync_hearing_dates_to_calendar — starting")
    db = SessionLocal()

    try:
        from app.db.models import Case, CaseStatus
        from app.services.calendar_service import upsert_hearing_event

        now = datetime.now(IST).replace(tzinfo=None)

        # Fetch all cases with a future hearing date
        cases = (
            db.query(Case)
            .filter(
                Case.next_hearing_date != None,
                Case.next_hearing_date >= now,
                Case.is_visible == True,
                Case.status.notin_([CaseStatus.disposed, CaseStatus.transferred]),
            )
            .all()
        )

        created = 0
        updated = 0
        errors  = 0

        for case in cases:
            try:
                event = await upsert_hearing_event(
                    db=db,
                    lawyer_id=str(case.advocate_id),
                    case_id=str(case.id),
                    case_number=case.case_number or case.efiling_number,
                    hearing_date=case.next_hearing_date,
                    court_number=case.court_number,
                    judge_name=case.judge_name,
                )
                # Distinguish new vs updated by checking created_at ≈ updated_at
                delta = abs((event.updated_at - event.created_at).total_seconds())
                if delta < 5:
                    created += 1
                else:
                    updated += 1

            except Exception as e:
                logger.warning(
                    "Failed to upsert hearing event for case %s: %s", case.id, e
                )
                errors += 1

        logger.info(
            "Job: sync_hearing_dates_to_calendar — done. "
            "cases=%d created=%d updated=%d errors=%d",
            len(cases), created, updated, errors,
        )

    except Exception as e:
        logger.exception("Job: sync_hearing_dates_to_calendar — failed: %s", e)

    finally:
        db.close()


# ============================================================================
# Job 2: Google Calendar incremental sync for all connected lawyers
# ============================================================================

async def sync_google_calendar_for_all_lawyers() -> None:
    """
    Runs incremental Google Calendar sync for every lawyer who has
    connected their Google account and has an active sync token.

    Uses Google's sync token mechanism — only fetches changed events
    since last sync. Fast and cheap even with many lawyers.

    Runs only during active hours (7am–7pm IST).
    """
    if not _is_active_hours():
        return

    logger.info("Job: sync_google_calendar_for_all_lawyers — starting")
    db = SessionLocal()

    try:
        from app.db.models import CalendarSyncToken
        from app.services.google_calendar_sync_service import run_incremental_sync

        # Fetch all lawyers with active Google Calendar connections
        sync_tokens = (
            db.query(CalendarSyncToken)
            .filter(CalendarSyncToken.is_active == True)
            .all()
        )

        if not sync_tokens:
            logger.info("Job: sync_google_calendar — no connected lawyers, skipping")
            return

        total_created = 0
        total_updated = 0
        total_deleted = 0
        errors        = 0

        for token in sync_tokens:
            try:
                stats = await run_incremental_sync(
                    lawyer_id=str(token.lawyer_id),
                    db=db,
                )
                total_created += stats.get("created", 0)
                total_updated += stats.get("updated", 0)
                total_deleted += stats.get("deleted", 0)
                if stats.get("errors"):
                    errors += len(stats["errors"])

            except Exception as e:
                logger.warning(
                    "Google sync failed for lawyer %s: %s", token.lawyer_id, e
                )
                errors += 1

        logger.info(
            "Job: sync_google_calendar — done. "
            "lawyers=%d +%d ~%d -%d errors=%d",
            len(sync_tokens), total_created, total_updated, total_deleted, errors,
        )

    except Exception as e:
        logger.exception("Job: sync_google_calendar_for_all_lawyers — failed: %s", e)

    finally:
        db.close()


# ============================================================================
# Active hours guard
# ============================================================================

def _is_active_hours() -> bool:
    """
    Returns True only between 7am and 7pm IST.
    All background jobs check this before doing any work.
    """
    now_ist = datetime.now(IST)
    return 7 <= now_ist.hour < 19