"""
Public (unauthenticated) stats endpoints.
Used by the marketing landing page.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings
from app.db.models import User

router = APIRouter()


@router.get("/stats")
def get_public_stats(db: Session = Depends(get_db)):
    """
    Returns early-bird slot count — no auth required.
    Counts all active registered users (is_active=True).
    Slot count is driven by EARLY_BIRD_SLOTS env var (default: 100).
    """
    slots = settings.EARLY_BIRD_SLOTS
    taken: int = db.query(User).filter(User.is_active == True).count()
    taken = min(taken, slots)
    return {
        "earlyBirdSlotsTotal": slots,
        "earlyBirdSlotsTaken": taken,
        "earlyBirdSlotsRemaining": slots - taken,
        "earlyBirdAvailable": taken < slots,
    }
