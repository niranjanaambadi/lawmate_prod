from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.db.models import User

router = APIRouter()


class UserProfileUpdateIn(BaseModel):
    email: Optional[EmailStr] = None
    mobile: Optional[str] = None
    khc_enrollment_number: Optional[str] = None
    khc_advocate_code: Optional[str] = None   # numeric adv_cd on hckinfo digicourt
    preferences: Optional[Dict[str, Any]] = None


def _profile_payload(user: User) -> Dict[str, Any]:
    return {
        "id": str(user.id),
        "email": user.email,
        "mobile": user.mobile,
        "khc_advocate_id": user.khc_advocate_id,
        "khc_advocate_name": user.khc_advocate_name,
        "khc_enrollment_number": user.khc_enrollment_number,
        "khc_advocate_code": user.khc_advocate_code,
        "role": getattr(user.role, "value", user.role),
        "is_active": user.is_active,
        "is_verified": user.is_verified,
        "profile_verified_at": user.profile_verified_at,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
        "last_login_at": user.last_login_at,
        "last_sync_at": user.last_sync_at,
        "preferences": user.preferences or {},
    }


@router.get("/profile")
def get_profile(current_user: User = Depends(get_current_user)) -> Dict[str, Any]:
    return {"data": _profile_payload(current_user)}


@router.patch("/profile")
def update_profile(
    payload: UserProfileUpdateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    body = payload.model_dump(exclude_unset=True)

    if "email" in body and body["email"] != current_user.email:
        existing = (
            db.query(User)
            .filter(User.email == body["email"], User.id != current_user.id)
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists",
            )

    if "mobile" in body:
        mobile = (body.get("mobile") or "").strip() or None
        body["mobile"] = mobile
        if mobile:
            existing_mobile = (
                db.query(User)
                .filter(User.mobile == mobile, User.id != current_user.id)
                .first()
            )
            if existing_mobile:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This mobile number is already registered",
                )

    if "khc_enrollment_number" in body:
        body["khc_enrollment_number"] = (body.get("khc_enrollment_number") or "").strip() or None

    if "khc_advocate_code" in body:
        body["khc_advocate_code"] = (body.get("khc_advocate_code") or "").strip() or None

    for field, value in body.items():
        setattr(current_user, field, value)

    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return {"data": _profile_payload(current_user)}
