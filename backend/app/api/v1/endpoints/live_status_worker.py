"""
Live-status worker endpoint — called by the AWS Lambda every 15 minutes.

The Lambda (backend/lambda/live_status_sync/) fires on EventBridge rate(15 minutes)
and POSTs to:  POST /api/v1/live-status-worker/run-due?batch_size=<N>

Authentication: x-mcp-token header must match settings.MCP_WORKER_TOKEN.

Design:
  - Picks `batch_size` pending cases ordered oldest-synced-first (NULLS FIRST).
  - Groups them by advocate so the existing per-user sync path is reused.
  - Each run processes a small rolling window; at scale (5 000 lawyers × 10 cases)
    the 15-min cadence works through the entire queue continuously.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logger import logger
from app.db.database import get_db
from app.db.models import Case, CaseStatus, User
from app.services.case_sync_service import case_sync_service

router = APIRouter()


# ── Security ──────────────────────────────────────────────────────────────────


def _verify_worker_token(x_mcp_token: Optional[str] = Header(None)) -> None:
    """
    Validate x-mcp-token header sent by the Lambda.
    The expected value is settings.MCP_WORKER_TOKEN (set via env var MCP_WORKER_TOKEN).
    If MCP_WORKER_TOKEN is empty the endpoint is disabled (returns 503).
    """
    expected = (settings.MCP_WORKER_TOKEN or "").strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Worker endpoint not configured (MCP_WORKER_TOKEN unset)",
        )
    if not x_mcp_token or x_mcp_token.strip() != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing x-mcp-token",
        )


# ── Endpoint ──────────────────────────────────────────────────────────────────


@router.post("/run-due")
def run_due(
    batch_size: int = Query(
        50, ge=1, le=500,
        description="Number of due cases to process per run",
    ),
    db: Session = Depends(get_db),
    _: None = Depends(_verify_worker_token),
) -> Dict[str, Any]:
    """
    Process the next batch of pending cases due for court-status sync.

    Cases are selected **oldest-synced-first** (last_synced_at ASC NULLS FIRST)
    so that cases which have never been synced are prioritised and the queue
    rotates evenly across all lawyers' cases over time.

    Returns a summary of what was processed in this invocation.
    """
    started_at = datetime.utcnow().isoformat()

    # ── 1. Pick the next batch ────────────────────────────────────────────────
    due_cases: List[Case] = (
        db.query(Case)
        .filter(
            Case.is_visible == True,           # noqa: E712
            Case.status == CaseStatus.pending,
            Case.case_number.isnot(None),
            Case.case_number != "",
        )
        .order_by(Case.last_synced_at.asc().nullsfirst())
        .limit(batch_size)
        .all()
    )

    if not due_cases:
        logger.info("live-status-worker/run-due: no pending cases due for sync")
        return {
            "ok": True,
            "startedAt": started_at,
            "finishedAt": datetime.utcnow().isoformat(),
            "processed": 0,
            "updated": 0,
            "failed": 0,
            "message": "No pending cases due for sync",
        }

    # ── 2. Group by advocate (reuse existing per-user sync path) ──────────────
    cases_by_user: Dict[str, List[Case]] = {}
    for case in due_cases:
        uid = str(case.advocate_id)
        cases_by_user.setdefault(uid, []).append(case)

    # Load the User rows for all affected advocate IDs in one query
    user_ids = list(cases_by_user.keys())
    users = db.query(User).filter(User.id.in_(user_ids)).all()
    user_map: Dict[str, User] = {str(u.id): u for u in users}

    # ── 3. Sync each user's batch ─────────────────────────────────────────────
    total_updated = 0
    total_failed = 0
    total_processed = 0

    for uid, cases in cases_by_user.items():
        user = user_map.get(uid)
        if not user:
            logger.warning(
                "live-status-worker: advocate %s not found — skipping %s cases",
                uid, len(cases),
            )
            total_failed += len(cases)
            continue

        try:
            summary = case_sync_service.sync_cases_list(db, user, cases)
            total_updated += summary.get("updated", 0)
            total_failed += summary.get("failed", 0)
            total_processed += summary.get("total", 0)
            logger.info(
                "live-status-worker: user=%s updated=%s failed=%s",
                uid, summary.get("updated"), summary.get("failed"),
            )
        except Exception:
            logger.exception(
                "live-status-worker: sync_cases_list raised for user=%s", uid
            )
            total_failed += len(cases)

    finished_at = datetime.utcnow().isoformat()
    logger.info(
        "live-status-worker/run-due complete — processed=%s updated=%s failed=%s",
        total_processed, total_updated, total_failed,
    )

    return {
        "ok": True,
        "startedAt": started_at,
        "finishedAt": finished_at,
        "processed": total_processed,
        "updated": total_updated,
        "failed": total_failed,
    }
