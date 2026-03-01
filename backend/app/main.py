# """

"""
FastAPI application entry point
"""
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.v1.api import api_router
from app.api import cause_list as cause_list_route
from app.core.logger import logger
from app.db.database import SessionLocal
from app.db.models import Case, CauseListIngestionRun, CauseListSource
from app.services.cause_list_store import cause_list_store
from app.services.daily_pdf_fetch_service import daily_pdf_fetch_service
from jobs.daily_cause_list_job import run_daily_cause_list_job

# ── New ───────────────────────────────────────────────────────────────────────
try:
    from app.api.v1.endpoints.agent import router as agent_router
except Exception as e:
    agent_router = None
    logger.warning("Agent router disabled: %s", e)

try:
    from app.api.v1.endpoints.calendar import router as calendar_router
except Exception as e:
    calendar_router = None
    logger.warning("Calendar router disabled: %s", e)

try:
    from app.services.background_jobs import (
        sync_hearing_dates_to_calendar,
        sync_google_calendar_for_all_lawyers,
    )
except Exception as e:
    sync_hearing_dates_to_calendar = None
    sync_google_calendar_for_all_lawyers = None
    logger.warning("Background calendar jobs disabled: %s", e)

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(api_router,              prefix="/api/v1")
app.include_router(cause_list_route.router, prefix="/api")
if agent_router is not None:
    app.include_router(agent_router, prefix="/api/v1")
if calendar_router is not None:
    app.include_router(calendar_router, prefix="/api/v1")

# ── Correlation ID middleware (must be added before CORS) ─────────────────────
try:
    from app.middleware.correlation import CorrelationMiddleware
    app.add_middleware(CorrelationMiddleware)
except Exception as _mw_err:
    logger.warning("CorrelationMiddleware disabled: %s", _mw_err)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_origin_regex=settings.CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Correlation-ID", "X-Tab-ID", "*"],
)


@app.get("/")
def read_root():
    logger.info("Root endpoint accessed")
    return {"message": "Lawmate API is running", "version": "1.0.0", "docs": "/docs"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}


# ── Existing scheduled loops (unchanged) ─────────────────────────────────────

SCHEDULED_CAUSELIST_RUNS_IST = [(5, 0), (18, 50), (19, 10)]


def _seconds_until_next_ist_run(hour: int, minute: int) -> float:
    ist = ZoneInfo("Asia/Kolkata")
    now = datetime.now(ist)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target = target + timedelta(days=1)
    return max((target - now).total_seconds(), 1.0)


def _next_scheduled_ist_run() -> tuple[float, datetime]:
    ist = ZoneInfo("Asia/Kolkata")
    now = datetime.now(ist)
    candidates: list[datetime] = []
    for hour, minute in SCHEDULED_CAUSELIST_RUNS_IST:
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target = target + timedelta(days=1)
        candidates.append(target)
    next_target = min(candidates)
    return max((next_target - now).total_seconds(), 1.0), next_target


async def _scheduled_daily_pdf_fetch_loop() -> None:
    if not settings.CAUSELIST_ENABLE_SCHEDULED_SYNC:
        logger.info("Daily cause-list PDF fetch scheduler disabled")
        return

    while True:
        try:
            delay, target = _next_scheduled_ist_run()
            logger.info("Next cause-list sync in %.0f seconds at %s", delay, target.isoformat())
            await asyncio.sleep(delay)
            db = SessionLocal()
            try:
                stats = daily_pdf_fetch_service.fetch_daily_pdfs_to_s3(db=db, max_tabs=3)
                listing_dates: set = set()
                for value in (stats.listing_dates or set()):
                    try:
                        listing_dates.add(datetime.strptime(value, "%Y-%m-%d").date())
                    except Exception:
                        continue

                if not listing_dates:
                    recent_runs = (
                        db.query(CauseListIngestionRun)
                        .filter(CauseListIngestionRun.source == CauseListSource.daily)
                        .order_by(CauseListIngestionRun.fetched_at.desc())
                        .limit(3)
                        .all()
                    )
                    listing_dates = {run.listing_date for run in recent_runs if run.listing_date}

                logger.info(
                    "Scheduled cause-list PDF fetch completed: source=%s fetched=%s runs=%s dates=%s",
                    stats.source, stats.fetched, stats.runs,
                    sorted([d.isoformat() for d in listing_dates]),
                )
            finally:
                db.close()

            for listing_date in sorted(listing_dates):
                try:
                    summary = await run_daily_cause_list_job(listing_date)
                    logger.info("Scheduled cause-list processing completed: %s", summary)
                except Exception:
                    logger.exception("Scheduled cause-list processing failed for date=%s", listing_date.isoformat())

            if settings.CAUSELIST_RETENTION_ENABLED:
                db = SessionLocal()
                try:
                    deleted = cause_list_store.purge_older_than(db, settings.CAUSELIST_RETENTION_DAYS)
                    db.commit()
                    if deleted > 0:
                        logger.info(
                            "Cause-list retention cleanup deleted %s rows older than %s days",
                            deleted, settings.CAUSELIST_RETENTION_DAYS,
                        )
                except Exception:
                    db.rollback()
                    logger.exception("Cause-list retention cleanup failed")
                finally:
                    db.close()
        except Exception:
            logger.exception("Scheduled daily cause-list PDF fetch failed")
            await asyncio.sleep(60)


async def _scheduled_recycle_bin_cleanup_loop() -> None:
    if not settings.CASES_RECYCLE_BIN_PURGE_ENABLED:
        logger.info("Recycle-bin cleanup scheduler disabled")
        return

    while True:
        try:
            delay = _seconds_until_next_ist_run(5, 30)
            logger.info("Next recycle-bin cleanup in %.0f seconds", delay)
            await asyncio.sleep(delay)

            cutoff = datetime.utcnow() - timedelta(days=max(1, int(settings.CASES_RECYCLE_BIN_RETENTION_DAYS)))
            db = SessionLocal()
            try:
                deleted = (
                    db.query(Case)
                    .filter(Case.is_visible == False, Case.updated_at < cutoff)
                    .delete(synchronize_session=False)
                )
                db.commit()
                if deleted:
                    logger.info(
                        "Recycle-bin cleanup deleted %s cases older than %s days",
                        deleted, settings.CASES_RECYCLE_BIN_RETENTION_DAYS,
                    )
            except Exception:
                db.rollback()
                logger.exception("Recycle-bin cleanup failed")
            finally:
                db.close()
        except Exception:
            logger.exception("Recycle-bin cleanup scheduler crashed")
            await asyncio.sleep(60)


# ── New background job loops (thin wrappers — logic lives in background_jobs.py)

async def _sync_hearing_dates_loop() -> None:
    """Calls sync_hearing_dates_to_calendar() every 60 min. Active hours guard is inside the job."""
    if sync_hearing_dates_to_calendar is None:
        logger.info("Hearing-date sync loop disabled")
        return
    while True:
        try:
            await asyncio.sleep(3600)
            await sync_hearing_dates_to_calendar()
        except Exception:
            logger.exception("_sync_hearing_dates_loop crashed")
            await asyncio.sleep(60)


async def _sync_google_calendar_loop() -> None:
    """Calls sync_google_calendar_for_all_lawyers() every 30 min. Active hours guard is inside the job."""
    if sync_google_calendar_for_all_lawyers is None:
        logger.info("Google calendar sync loop disabled")
        return
    while True:
        try:
            await asyncio.sleep(1800)
            await sync_google_calendar_for_all_lawyers()
        except Exception:
            logger.exception("_sync_google_calendar_loop crashed")
            await asyncio.sleep(60)


async def _scheduled_advocate_causelist_loop() -> None:
    """
    Runs once daily at 7:15 PM IST.

    Fetches TOMORROW's cause list for every active user who has
    khc_advocate_name, khc_enrollment_number, and khc_advocate_code set.
    Upserts results into advocate_cause_lists so they are ready for the
    next morning when advocates check the dashboard.
    """
    from datetime import timedelta
    from app.db.models import User
    from app.services.advocate_causelist_service import fetch_and_store_advocate_causelist

    while True:
        try:
            delay = _seconds_until_next_ist_run(19, 15)   # 7:15 PM IST
            logger.info(
                "Advocate cause-list scheduler: next run in %.0f s (19:15 IST)",
                delay,
            )
            await asyncio.sleep(delay)

            ist       = ZoneInfo("Asia/Kolkata")
            tomorrow  = (datetime.now(ist) + timedelta(days=1)).date()

            db = SessionLocal()
            try:
                users = (
                    db.query(User)
                    .filter(
                        User.is_active           == True,
                        User.khc_advocate_name   != None,
                        User.khc_enrollment_number != None,
                        User.khc_advocate_code   != None,
                    )
                    .all()
                )

                logger.info(
                    "Advocate cause-list: fetching for %d users, date=%s",
                    len(users), tomorrow,
                )

                ok = failed = 0
                for user in users:
                    try:
                        await fetch_and_store_advocate_causelist(
                            advocate_name=user.khc_advocate_name,
                            target_date=tomorrow,
                            lawyer_id=str(user.id),
                            db=db,
                            enrollment_number=user.khc_enrollment_number or "",
                            advocate_code=user.khc_advocate_code or "",
                        )
                        ok += 1
                    except Exception:
                        failed += 1
                        logger.exception(
                            "Advocate cause-list fetch failed for user %s", user.id
                        )

                logger.info(
                    "Advocate cause-list batch done: %d ok, %d failed, date=%s",
                    ok, failed, tomorrow,
                )
            finally:
                db.close()

        except Exception:
            logger.exception("_scheduled_advocate_causelist_loop crashed")
            await asyncio.sleep(60)


# ── Startup / Shutdown ────────────────────────────────────────────────────────
# Case-status sync is now handled by the Lambda worker (live_status_sync).
# The Lambda calls POST /api/v1/live-status-worker/run-due every 15 minutes,
# which processes a rolling batch of pending cases oldest-first.

async def _idempotency_cleanup_loop() -> None:
    """Delete expired idempotency_records rows every hour."""
    from app.services.idempotency_service import delete_expired_idempotency_records

    while True:
        try:
            await asyncio.sleep(3600)
            db = SessionLocal()
            try:
                deleted = delete_expired_idempotency_records(db)
                if deleted:
                    logger.info("idempotency_cleanup: deleted %d expired rows", deleted)
            finally:
                db.close()
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("_idempotency_cleanup_loop crashed")
            await asyncio.sleep(60)


async def _doc_comparison_cleanup_loop() -> None:
    """Delete expired doc_comparisons rows every hour."""
    from app.services.document_comparison_service import delete_expired_comparisons
    from app.db.database import SessionLocal

    while True:
        try:
            await asyncio.sleep(3600)  # wait 1 hour between sweeps
            db = SessionLocal()
            try:
                deleted = delete_expired_comparisons(db)
                if deleted:
                    logger.info("doc_comparison_cleanup: deleted %d expired rows", deleted)
            finally:
                db.close()
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("_doc_comparison_cleanup_loop crashed")
            await asyncio.sleep(60)


@app.on_event("startup")
async def startup_event():
    logger.info("Lawmate API started")
    # Existing tasks
    app.state.daily_pdf_fetch_task      = asyncio.create_task(_scheduled_daily_pdf_fetch_loop())
    app.state.recycle_bin_cleanup_task  = asyncio.create_task(_scheduled_recycle_bin_cleanup_loop())
    # Calendar tasks
    app.state.hearing_sync_task         = asyncio.create_task(_sync_hearing_dates_loop())
    app.state.google_calendar_sync_task = asyncio.create_task(_sync_google_calendar_loop())
    # Advocate cause list — 7:15 PM IST daily, fetches tomorrow for all users
    app.state.advocate_causelist_task   = asyncio.create_task(_scheduled_advocate_causelist_loop())
    # Idempotency records — purge expired rows every hour
    app.state.idempotency_cleanup_task    = asyncio.create_task(_idempotency_cleanup_loop())
    # Doc comparison — purge expired rows every hour
    app.state.doc_comparison_cleanup_task = asyncio.create_task(_doc_comparison_cleanup_loop())
    # Note: case-status sync is handled by the live_status_sync Lambda worker,
    #       not by an in-process loop. See /api/v1/live-status-worker/run-due.


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Lawmate API shutdown")
    for task_name in [
        "daily_pdf_fetch_task",
        "recycle_bin_cleanup_task",
        "hearing_sync_task",
        "google_calendar_sync_task",
        "advocate_causelist_task",
        "idempotency_cleanup_task",
        "doc_comparison_cleanup_task",
    ]:
        task = getattr(app.state, task_name, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

