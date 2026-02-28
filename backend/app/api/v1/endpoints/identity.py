
"""
Identity verification endpoints
"""
from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session
import re

from app.db.database import get_db
from app.db.models import User
from app.api.deps import get_current_user

router = APIRouter()


def normalize_name(value: str) -> str:
    if not value:
        return ""
    cleaned = re.sub(r"[^A-Za-z0-9\s]", " ", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
    return cleaned


@router.post("/verify")
def verify_identity(
    scraped_name: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Verify that scraped advocate name matches authenticated user
    This is the "handshake" protocol for extension
    """
    scraped = normalize_name(scraped_name)
    expected = normalize_name(current_user.khc_advocate_name)

    if not scraped or scraped != expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Advocate name mismatch. Data does not belong to you."
        )
    
    return {
        "verified": True,
        "khc_advocate_id": current_user.khc_advocate_id,
        "advocate_name": current_user.khc_advocate_name,
        "sync_token": f"sync_{current_user.id}"  # Can be used for additional verification
    }
# # app/api/v1/endpoints/identity.py

# from fastapi import APIRouter, HTTPException, Depends, status
# from sqlalchemy.orm import Session
# from pydantic import BaseModel
# from datetime import datetime

# from app.db.database import get_db
# from app.db.models import User
# from app.api.v1.deps import get_current_user
# from app.services.audit_service import AuditService

# router = APIRouter(prefix="/identity", tags=["identity"])

# # ============================================================================
# # Request Models
# # ============================================================================

# class IdentityVerificationRequest(BaseModel):
#     scraped_khc_id: str
#     scraped_name: str

# # ============================================================================
# # Endpoints
# # ============================================================================

# @router.post("/verify")
# async def verify_identity(
#     request: IdentityVerificationRequest,
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """
#     Verify that scraped KHC ID matches the authenticated user's registered KHC ID.
#     This is the critical "Identity Handshake" that prevents cross-account data pollution.
#     """
#     # Compare scraped ID with registered ID
#     if current_user.khc_advocate_id != request.scraped_khc_id:
#         # SECURITY BREACH: Log this event
#         await AuditService.log_identity_mismatch(
#             user_id=str(current_user.id),
#             scraped_khc_id=request.scraped_khc_id,
#             registered_khc_id=current_user.khc_advocate_id,
#             db=db
#         )
        
#         return {
#             "verified": False,
#             "error": "IDENTITY_MISMATCH",
#             "message": f"You are logged into KHC as {request.scraped_khc_id}, but your Lawmate account is registered for {current_user.khc_advocate_id}. Please log into KHC with the correct account.",
#             "expected_khc_id": current_user.khc_advocate_id
#         }
    
#     # Identity verified successfully
#     await AuditService.log_identity_verified(
#         user_id=str(current_user.id),
#         khc_id=request.scraped_khc_id,
#         db=db
#     )
    
#     # Generate sync token (short-lived, 1 hour)
#     from app.core.security import create_sync_token
#     sync_token = create_sync_token(
#         user_id=str(current_user.id),
#         khc_id=request.scraped_khc_id
#     )
    
#     return {
#         "verified": True,
#         "sync_token": sync_token,
#         "expires_in": 3600,  # 1 hour
#         "user": {
#             "id": str(current_user.id),
#             "khc_advocate_id": current_user.khc_advocate_id,
#             "khc_advocate_name": current_user.khc_advocate_name
#         }
#     }
