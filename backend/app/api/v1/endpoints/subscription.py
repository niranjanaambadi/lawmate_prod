"""
Subscription & billing management endpoints.

Webapp expectations:
- Uses JSON request bodies for mutations.
- Destructures `{ data }` from responses.
So we return `{ "data": ... }` envelopes here.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.db.models import User
from app.services import subscription_service

router = APIRouter()


class UpgradePlanIn(BaseModel):
    plan: str
    billing_cycle: str


class CancelSubscriptionIn(BaseModel):
    reason: Optional[str] = None


class PaymentMethodIn(BaseModel):
    payment_method: str


class AutoRenewIn(BaseModel):
    auto_renew: bool


class PurchaseTopupIn(BaseModel):
    payment_reference: Optional[str] = None


@router.get("/current")
def get_current_subscription(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    subscription = subscription_service.get_or_create_current_subscription(db, current_user.id)
    return {"data": subscription}


@router.get("/plans")
def get_available_plans() -> Dict[str, Any]:
    return {"data": subscription_service.get_all_plans()}


@router.get("/usage")
def get_usage_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    return {"data": subscription_service.get_usage_stats(db, current_user.id)}


@router.get("/invoices")
def get_invoices(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    return {"data": subscription_service.get_invoices(db, current_user.id)}


@router.post("/upgrade")
def upgrade_plan(
    payload: UpgradePlanIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    checkout_url = subscription_service.upgrade_plan(db, current_user.id, payload.plan, payload.billing_cycle)
    return {"data": {"checkout_url": checkout_url}}


@router.post("/cancel")
def cancel_subscription(
    payload: CancelSubscriptionIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    subscription_service.cancel_subscription(db, current_user.id, payload.reason)
    return {"data": {"message": "Subscription cancelled successfully"}}


@router.patch("/payment-method")
def update_payment_method(
    payload: PaymentMethodIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    subscription_service.update_payment_method(db, current_user.id, payload.payment_method)
    return {"data": {"message": "Payment method updated"}}


@router.patch("/auto-renew")
def toggle_auto_renew(
    payload: AutoRenewIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    subscription_service.toggle_auto_renew(db, current_user.id, payload.auto_renew)
    return {"data": {"message": f"Auto-renewal {'enabled' if payload.auto_renew else 'disabled'}"}}


@router.post("/topup")
def purchase_topup(
    payload: PurchaseTopupIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Record a ₹200 top-up (+20 AI analyses for the current billing period).
    In production, only call this after Razorpay payment verification via webhook.
    """
    result = subscription_service.purchase_topup(
        db, str(current_user.id), payload.payment_reference
    )
    return {"data": result}