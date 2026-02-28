from __future__ import annotations

import asyncio
import functools
from datetime import date, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.logger import logger
from app.db.database import SessionLocal, get_db
from app.db.models import CauseListIngestionRun, CauseListSource, User
from app.services.cause_list_renderer import cause_list_renderer
from app.services.daily_pdf_fetch_service import daily_pdf_fetch_service
from app.services.cause_list_store import cause_list_store
from app.services.mediation_enrichment_service import mediation_enrichment_service
from jobs.daily_cause_list_job import run_daily_cause_list_job

router = APIRouter()


def _parse_date(value: str | None) -> date:
    if not value:
        return date.today()
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {value}") from exc


# ---------------------------------------------------------------------------
# Background pipeline — owns its own DB session so it safely runs after
# the HTTP response has been returned and the request-scoped session closed.
# ---------------------------------------------------------------------------

async def _run_process_job(listing_date: date) -> None:
    """
    Full pipeline runs in the background:
      1. Fetch PDF to S3  — Playwright (sync/blocking) → asyncio.to_thread
      2. Parse + store    — run_daily_cause_list_job (async, own session)

    Never blocks the event loop.
    """
    # ── Step 1: PDF fetch ────────────────────────────────────────────────────
    db = SessionLocal()
    try:
        existing_run = (
            db.query(CauseListIngestionRun)
            .filter(
                CauseListIngestionRun.source == CauseListSource.daily,
                CauseListIngestionRun.listing_date == listing_date,
            )
            .first()
        )
        if not existing_run:
            try:
                fetch_fn = functools.partial(
                    daily_pdf_fetch_service.fetch_daily_pdfs_to_s3,
                    db=db,
                    max_tabs=3,
                )
                await asyncio.to_thread(fetch_fn)
                db.commit()
                logger.info("Background PDF fetch completed for %s", listing_date)
            except Exception as exc:
                logger.warning(
                    "Background PDF fetch failed for %s: %s — continuing to parse",
                    listing_date, exc,
                )
    except Exception as exc:
        logger.warning("Background job setup error for %s: %s", listing_date, exc)
    finally:
        db.close()

    # ── Step 2: Parse + store (creates its own session internally) ───────────
    try:
        summary = await run_daily_cause_list_job(listing_date)
        logger.info(
            "Background cause list job completed for %s: %s", listing_date, summary
        )
    except Exception as exc:
        logger.error(
            "Background cause list job failed for %s: %s", listing_date, exc
        )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/cause-list")
def get_cause_list(
    date_value: str | None = Query(None, alias="date"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    listing_date = _parse_date(date_value)
    advocate_name = (current_user.khc_advocate_name or "").strip()

    mediation_listings = mediation_enrichment_service.get_mediation_listings_for_advocate(
        db=db,
        listing_date=listing_date,
        advocate_name=advocate_name,
    )

    row = cause_list_store.fetch_result(
        db, advocate_id=str(current_user.id), listing_date=listing_date
    )
    if not row:
        if mediation_listings:
            result_json: dict = {"listings": mediation_listings}
            html = cause_list_renderer.render(result_json)
            return {
                "html": html,
                "total_listings": len(mediation_listings),
                "date": listing_date.isoformat(),
                "mediation_listings": len(mediation_listings),
            }
        return {
            "html": cause_list_renderer.render_empty(listing_date.isoformat()),
            "total_listings": 0,
            "date": listing_date.isoformat(),
            "mediation_listings": 0,
        }

    result_json = row.result_json if isinstance(row.result_json, dict) else {}

    if mediation_listings:
        result_json = mediation_enrichment_service.inject_into_result(
            result_json, mediation_listings
        )

    html = cause_list_renderer.render(result_json)
    return {
        "html": html,
        "total_listings": int(row.total_listings or 0) + len(mediation_listings),
        "date": listing_date.isoformat(),
        "mediation_listings": len(mediation_listings),
    }


@router.post("/cause-list/fetch-daily")
def fetch_daily_cause_list_pdf_to_s3(
    max_tabs: int = Query(3, ge=1, le=10),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ = current_user
    stats = daily_pdf_fetch_service.fetch_daily_pdfs_to_s3(db=db, max_tabs=max_tabs)
    return {
        "success": True,
        "source": stats.source,
        "fetched": stats.fetched,
        "runs": stats.runs,
        "failed_runs": stats.failed_runs,
        "listing_dates": sorted(list(stats.listing_dates or set())),
    }


@router.post("/cause-list/process")
async def process_cause_list_for_date(
    background_tasks: BackgroundTasks,
    date_value: str | None = Query(None, alias="date"),
    current_user: User = Depends(get_current_user),
):
    """
    Kick off the daily pipeline (PDF fetch → LLM parse → store) as a
    background task and return immediately.

    The Playwright PDF fetch and LLM parsing each take 1–5 minutes — running
    them inside the request would block the event loop for all other users.
    Instead we return right away; the page auto-polls for results.
    """
    _ = current_user
    listing_date = _parse_date(date_value)

    background_tasks.add_task(_run_process_job, listing_date)

    return {
        "success": True,
        "status": "started",
        "date": listing_date.isoformat(),
        "message": (
            "Job started in background. "
            "PDF fetch + LLM parsing typically takes 1–3 minutes. "
            "Results will appear automatically."
        ),
    }


@router.post("/cause-list/enrich-mediation")
async def enrich_mediation_cases(
    date_value: str | None = Query(None, alias="date"),
    max_cases: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ = current_user
    listing_date = _parse_date(date_value)
    stats = await asyncio.to_thread(
        mediation_enrichment_service.enrich_pending_cases,
        db,
        listing_date,
        max_cases,
    )
    return {"success": True, "date": listing_date.isoformat(), **stats}


@router.get("/cause-list/mediation-status")
def get_mediation_status(
    date_value: str | None = Query(None, alias="date"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ = current_user
    listing_date = _parse_date(date_value)
    return mediation_enrichment_service.get_status_summary(db, listing_date)
