from fastapi import APIRouter, HTTPException

from app.core.logger import logger
from app.services.roster_service import RosterService

router = APIRouter()


@router.get("/latest")
def get_latest_roster():
    """
    Return latest roster metadata + signed URL from S3.
    If missing, performs a sync first.
    """
    try:
        service = RosterService()
        return {"ok": True, "data": service.get_latest_roster()}
    except Exception as exc:
        logger.exception("Failed to fetch latest roster")
        raise HTTPException(status_code=502, detail=f"Failed to fetch latest roster: {str(exc)}")


@router.post("/sync")
def sync_roster():
    """
    Force sync latest roster from Kerala High Court source and save into:
    s3://lawmate-khc-prod/roster/
    """
    try:
        service = RosterService()
        return {"ok": True, "data": service.sync_latest_roster()}
    except Exception as exc:
        logger.exception("Failed to sync roster")
        raise HTTPException(status_code=502, detail=f"Failed to sync roster: {str(exc)}")
