from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse

from app.core.logger import logger
from app.services.roster_service import RosterService

router = APIRouter()


@router.get("/latest")
def get_latest_roster():
    """Return latest roster metadata + presigned S3 URL. Auto-syncs if nothing is in S3 yet."""
    try:
        service = RosterService()
        return {"ok": True, "data": service.get_latest_roster()}
    except Exception as exc:
        logger.exception("Failed to fetch latest roster")
        raise HTTPException(status_code=502, detail=f"Failed to fetch latest roster: {str(exc)}")


def _run_sync() -> None:
    try:
        RosterService().sync_latest_roster()
        logger.info("Background roster sync completed")
    except Exception:
        logger.exception("Background roster sync failed")


@router.post("/sync")
def sync_roster(background_tasks: BackgroundTasks):
    """
    Kick off a background roster sync and return 200 immediately.
    The sync (KHC fetch + PDF download + HTML generation + S3 upload) can take
    up to a few minutes, so it must not block the HTTP response.
    """
    background_tasks.add_task(_run_sync)
    return {"ok": True, "status": "sync_started"}


@router.get("/html", response_class=HTMLResponse)
def get_roster_html():
    """
    Return the pre-generated styled HTML version of the latest roster PDF.
    HTML is produced at sync time and cached in S3; returns 404 if not yet generated.
    """
    try:
        service = RosterService()
        html = service.get_latest_roster_html()
        if html is None:
            raise HTTPException(
                status_code=404,
                detail="Roster HTML not yet generated — try refreshing the roster first.",
            )
        return HTMLResponse(
            content=html,
            headers={"Cache-Control": "public, max-age=1800"},
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to fetch roster HTML")
        raise HTTPException(status_code=502, detail=f"Failed to fetch roster HTML: {str(exc)}")
