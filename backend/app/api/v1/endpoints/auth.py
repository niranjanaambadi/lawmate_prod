import os
import secrets
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import timedelta, datetime
import re

from app.db.database import get_db
from app.db import models, schemas
from app.db.models import UserRole
from app.core.security import get_password_hash, verify_password, create_access_token
from app.core.config import settings
from app.core.logger import logger
from app.api.deps import get_current_user
from app.services.otp_service import otp_service

router = APIRouter()

RESET_TOKEN_EXPIRY_HOURS = 1
PROFILE_OTP_EXPIRY_MINUTES = 5

# @router.post("/register", response_model=schemas.UserOut)
# def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
#     """Register new user"""
#     # Check if user exists
#     existing_user = db.query(models.User).filter(
#         models.User.email == user.email
#     ).first()
    
#     if existing_user:
#         raise HTTPException(
#             status_code=400,
#             detail="Email already registered"
#         )
    
#     # Check KHC ID
#     existing_khc = db.query(models.User).filter(
#         models.User.khc_advocate_id == user.khc_advocate_id
#     ).first()
    
#     if existing_khc:
#         raise HTTPException(
#             status_code=400,
#             detail="KHC Advocate ID already registered"
#         )
    
#     # Create user
#     db_user = models.User(
#         email=user.email,
#         password_hash=get_password_hash(user.password),
#         khc_advocate_id=user.khc_advocate_id,
#         khc_advocate_name=user.khc_advocate_name,
#         mobile=user.mobile,
#         khc_enrollment_number=user.khc_enrollment_number,
#         role="advocate",
#         is_active=True,
#         is_verified=False
#     )
    
#     db.add(db_user)
#     db.commit()
#     db.refresh(db_user)
    
#     return db_user

@router.post("/login")
def login(form_data: schemas.UserLogin, db: Session = Depends(get_db)):
    """Login endpoint. Email is normalized to lowercase for consistency with register."""
    email = (form_data.email or "").strip().lower()
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email is required")

    user = db.query(models.User).filter(models.User.email == email).first()
    
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive"
        )
    
    # Create token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=access_token_expires
    )
    
    # Update last login
    user.last_login_at = datetime.utcnow()
    db.commit()
    
    return {
        "access_token": access_token,
        "refresh_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "email": user.email,
            "khc_advocate_id": user.khc_advocate_id,
            "khc_advocate_name": user.khc_advocate_name,
            "role": getattr(user.role, "value", user.role) if hasattr(user, "role") else (user.role or "advocate"),
            "is_verified": getattr(user, "is_verified", False),
            "profile_verified_at": user.profile_verified_at,
        }
    }
    
@router.get("/me", response_model=schemas.UserOut)
def get_current_user_info(
    current_user: models.User = Depends(get_current_user)
):
    """Get current user profile"""
    return current_user

@router.post("/logout")
def logout():
    """Logout endpoint (stateless JWT - client deletes token)"""
    return {"message": "Logged out successfully"}


@router.post("/forgot-password")
def forgot_password(body: schemas.ForgotPasswordRequest, db: Session = Depends(get_db)):
    """
    Request password reset. Always returns success to prevent email enumeration.
    If user exists, stores a reset token (and optionally sends email).
    """
    email = (body.email or "").strip().lower()
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email is required")

    user = db.query(models.User).filter(models.User.email == email).first()

    if user:
        reset_token = secrets.token_hex(32)
        reset_expiry = datetime.utcnow() + timedelta(hours=RESET_TOKEN_EXPIRY_HOURS)
        user.password_reset_token = reset_token
        user.password_reset_token_expiry = reset_expiry
        db.commit()

        base_url = os.getenv("FRONTEND_URL") or os.getenv("NEXTAUTH_URL") or "http://localhost:3000"
        reset_url = f"{base_url.rstrip('/')}/auth/reset-password?token={reset_token}"
        if settings.DEBUG or os.getenv("ENVIRONMENT") == "development":
            print(f"[DEV] Password reset link: {reset_url}")

        # TODO: Send email with reset_url (e.g. Resend, SendGrid)

    return {
        "success": True,
        "message": "If an account exists with this email, you will receive reset instructions.",
    }


@router.post("/reset-password")
def reset_password(body: schemas.ResetPasswordRequest, db: Session = Depends(get_db)):
    """
    Reset password using token from forgot-password email/link.
    """
    token = (body.token or "").strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset link. Please request a new one.",
        )
    if len(body.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters",
        )

    user = (
        db.query(models.User)
        .filter(
            models.User.password_reset_token == token,
            models.User.password_reset_token_expiry > datetime.utcnow(),
        )
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset link. Please request a new one.",
        )

    user.password_hash = get_password_hash(body.password)
    user.password_reset_token = None
    user.password_reset_token_expiry = None
    db.commit()

    return {"success": True, "message": "Your password has been reset. You can sign in now."}


@router.post("/register", response_model=schemas.UserOut)
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    """Register new user. Aligned with webapp: normalized email, duplicate checks, is_verified=True."""
    email = (user.email or "").strip().lower()
    khc_id = (user.khc_advocate_id or "").strip()
    name = (user.khc_advocate_name or "").strip()
    mobile = (user.mobile or "").strip() or None
    enrollment = (user.khc_enrollment_number or "").strip() or None

    if not email:
        raise HTTPException(status_code=400, detail="Email is required")
    if not khc_id:
        raise HTTPException(status_code=400, detail="KHC Advocate ID is required")
    if not name:
        raise HTTPException(status_code=400, detail="Full name is required")

    existing_user = db.query(models.User).filter(models.User.email == email).first()
    if existing_user:
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    existing_khc = db.query(models.User).filter(models.User.khc_advocate_id == khc_id).first()
    if existing_khc:
        raise HTTPException(status_code=409, detail="This KHC Advocate ID is already registered")

    if mobile:
        existing_mobile = db.query(models.User).filter(models.User.mobile == mobile).first()
        if existing_mobile:
            raise HTTPException(status_code=409, detail="This mobile number is already registered")

    db_user = models.User(
        email=email,
        password_hash=get_password_hash(user.password),
        khc_advocate_id=khc_id,
        khc_advocate_name=name,
        mobile=mobile,
        khc_enrollment_number=enrollment,
        role=UserRole.advocate,
        is_active=True,
        is_verified=True,  # Allow immediate access; set False when email verification is added
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def _normalize_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9\s]", " ", value or "")
    return re.sub(r"\s+", " ", cleaned).strip().lower()


def _mask_mobile(mobile: str) -> str:
    digits = re.sub(r"\D", "", mobile or "")
    if len(digits) < 4:
        return "****"
    return f"{'*' * (len(digits) - 4)}{digits[-4:]}"


def _mask_email(email: str) -> str:
    value = (email or "").strip()
    if "@" not in value:
        return "****"
    local, domain = value.split("@", 1)
    if len(local) <= 2:
        local_masked = "*" * len(local)
    else:
        local_masked = local[:2] + ("*" * (len(local) - 2))
    return f"{local_masked}@{domain}"


@router.post("/profile-verification/start", response_model=schemas.ProfileVerificationStartResponse)
def start_profile_verification(
    body: schemas.ProfileVerificationStartRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    full_name = (body.full_name or "").strip()
    verify_via = (body.verify_via or "").strip().lower()
    if not full_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Full name is required")
    if verify_via not in {"phone", "email"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification method")

    # Match entered name against KHC advocate registry.
    name_matches = db.query(models.KHCAdvocate).filter(
        func.lower(models.KHCAdvocate.advocate_name) == full_name.lower(),
        models.KHCAdvocate.is_active == True,
    ).order_by(models.KHCAdvocate.updated_at.desc()).all()
    if not name_matches:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Lawmate is exclusive to lawyers practising at the High Court of Kerala.",
        )

    # Prefer matching user's stored KHC ID when duplicates exist for same name.
    registry = None
    current_khc = (current_user.khc_advocate_id or "").strip()
    if current_khc:
        registry = next((row for row in name_matches if (row.khc_advocate_id or "").strip() == current_khc), None)
    if not registry:
        registry = name_matches[0]

    target_phone = (registry.mobile or "").strip()
    target_email = (registry.email or "").strip()
    if verify_via == "phone" and not target_phone:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Phone verification is not available for this profile")
    if verify_via == "email" and not target_email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email verification is not available for this profile")

    otp = f"{secrets.randbelow(900000) + 100000}"
    current_user.verification_otp_code = otp
    current_user.verification_otp_expires_at = datetime.utcnow() + timedelta(minutes=PROFILE_OTP_EXPIRY_MINUTES)
    # Sync user identity from trusted registry row.
    current_user.khc_advocate_id = registry.khc_advocate_id
    current_user.khc_advocate_name = registry.advocate_name
    if target_phone:
        current_user.mobile = target_phone
    db.commit()

    delivery_provider = ""
    try:
        if verify_via == "phone":
            send_result = otp_service.send_sms_otp(target_phone, otp)
            delivery_provider = send_result.get("provider", "")
        else:
            send_result = otp_service.send_email_otp(target_email, otp)
            delivery_provider = send_result.get("provider", "")
    except Exception as exc:
        logger.error("OTP delivery failed", extra={"user_id": str(current_user.id), "via": verify_via, "error": str(exc)})
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Failed to send OTP via {verify_via}")

    return schemas.ProfileVerificationStartResponse(
        success=True,
        message=(
            f"OTP sent to { _mask_mobile(target_phone) }"
            if verify_via == "phone"
            else f"OTP sent to { _mask_email(target_email) }"
        ),
        verify_via=verify_via,
        masked_mobile=_mask_mobile(target_phone) if verify_via == "phone" else None,
        masked_email=_mask_email(target_email) if verify_via == "email" else None,
        expires_in_seconds=PROFILE_OTP_EXPIRY_MINUTES * 60,
        dev_otp=otp if (settings.DEBUG and delivery_provider == "dev") else None,
    )


@router.post("/profile-verification/confirm", response_model=schemas.ProfileVerificationConfirmResponse)
def confirm_profile_verification(
    body: schemas.ProfileVerificationConfirmRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    otp = (body.otp or "").strip()
    if not current_user.verification_otp_code or not current_user.verification_otp_expires_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No active OTP. Request a new OTP.")
    if datetime.utcnow() > current_user.verification_otp_expires_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP expired. Request a new OTP.")
    if otp != current_user.verification_otp_code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OTP")

    now = datetime.utcnow()
    current_user.profile_verified_at = now
    current_user.verification_otp_code = None
    current_user.verification_otp_expires_at = None
    db.commit()

    return schemas.ProfileVerificationConfirmResponse(
        success=True,
        message="Verification successful",
        verified_at=now,
    )
