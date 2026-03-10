"""
Public (unauthenticated) stats endpoints.
Used by the marketing landing page.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db.models import User

router = APIRouter()

EARLY_BIRD_SLOTS = 100


@router.get("/stats")
def get_public_stats(db: Session = Depends(get_db)):
    """
    Returns early-bird slot count — no auth required.
    Counts all active registered users (is_active=True).
    """
    taken: int = db.query(User).filter(User.is_active == True).count()
    taken = min(taken, EARLY_BIRD_SLOTS)
    return {
        "earlyBirdSlotsTotal": EARLY_BIRD_SLOTS,
        "earlyBirdSlotsTaken": taken,
        "earlyBirdSlotsRemaining": EARLY_BIRD_SLOTS - taken,
        "earlyBirdAvailable": taken < EARLY_BIRD_SLOTS,
    }
