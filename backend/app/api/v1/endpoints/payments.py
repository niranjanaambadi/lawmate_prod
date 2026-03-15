"""
Razorpay payment integration endpoints.

All amounts are driven by environment variables defined in app/core/config.py:
  RAZORPAY_KEY_ID               — public key (returned to frontend for checkout)
  RAZORPAY_KEY_SECRET           — secret key (server-side only)
  RAZORPAY_WEBHOOK_SECRET       — used to verify Razorpay webhook signatures
  RAZORPAY_EARLY_BIRD_PLAN_ID   — Razorpay Plan ID for the early-bird tier
  RAZORPAY_STANDARD_PLAN_ID     — Razorpay Plan ID for the standard tier
  EARLY_BIRD_PLAN_AMOUNT_PAISE  — price in paise for early bird (default 120000 = ₹1,200)
  STANDARD_PLAN_AMOUNT_PAISE    — price in paise for standard  (default 150000 = ₹1,500)
  TOPUP_AMOUNT_PAISE            — price in paise per top-up   (default 20000  = ₹200)
  TOPUP_AI_ANALYSES             — analyses added per top-up    (default 20)
  EARLY_BIRD_SLOTS              — max users eligible for early-bird pricing (default 100)

Routes:
  GET  /payments/config                — public, returns Razorpay key + pricing
  POST /payments/create-topup-order    — creates Razorpay order for a top-up
  POST /payments/verify-topup          — verifies signature; credits usage_topups row
  POST /payments/create-subscription   — creates Razorpay recurring subscription
  POST /payments/verify-subscription   — verifies signature; activates plan in DB
  POST /payments/webhook               — handles Razorpay webhook events (no auth)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.core.config import settings
from app.db.database import get_db
from app.db.models import (
    BillingCycle,
    Subscription,
    SubscriptionPlan,
    SubscriptionStatus,
    User,
)
from app.services import subscription_service

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Internal helpers ──────────────────────────────────────────────────────────

def _razorpay_client():
    """Lazily initialise the Razorpay SDK client.
    Raises HTTP 503 if the package is not installed or keys are not set."""
    try:
        import razorpay  # type: ignore
    except ImportError:
        raise HTTPException(503, "razorpay package not installed on this server")

    if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        raise HTTPException(
            503,
            "Razorpay keys not configured. "
            "Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET in environment.",
        )
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def _verify_signature(body: str, signature: str, secret: str) -> bool:
    """HMAC-SHA256 verification for Razorpay payment/subscription callbacks."""
    expected = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


# ── GET /payments/config ──────────────────────────────────────────────────────

@router.get("/config")
def get_payment_config():
    """
    Return public Razorpay key + current plan pricing.
    No authentication required — safe to call from landing page / checkout modal.
    """
    return {
        "keyId": settings.RAZORPAY_KEY_ID,
        "earlyBirdAmountPaise": settings.EARLY_BIRD_PLAN_AMOUNT_PAISE,
        "standardAmountPaise": settings.STANDARD_PLAN_AMOUNT_PAISE,
        "topupAmountPaise": settings.TOPUP_AMOUNT_PAISE,
        "topupAiAnalyses": settings.TOPUP_AI_ANALYSES,
        "earlyBirdSlots": settings.EARLY_BIRD_SLOTS,
        "currency": "INR",
    }


# ── POST /payments/create-topup-order ────────────────────────────────────────

class CreateTopupOrderOut(BaseModel):
    orderId: str
    amountPaise: int
    currency: str
    keyId: str
    aiAnalyses: int


@router.post("/create-topup-order", response_model=CreateTopupOrderOut)
def create_topup_order(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CreateTopupOrderOut:
    """
    Step 1 of the top-up flow.
    Creates a Razorpay order and returns the order ID + public key so the
    frontend can open the Razorpay checkout modal.
    """
    client = _razorpay_client()
    try:
        order = client.order.create(
            {
                "amount": settings.TOPUP_AMOUNT_PAISE,
                "currency": "INR",
                "notes": {
                    "user_id": str(current_user.id),
                    "type": "topup",
                    "ai_analyses": settings.TOPUP_AI_ANALYSES,
                },
            }
        )
    except Exception as exc:
        logger.exception("Razorpay order creation failed for user %s", current_user.id)
        raise HTTPException(502, f"Payment gateway error: {exc}")

    return CreateTopupOrderOut(
        orderId=order["id"],
        amountPaise=settings.TOPUP_AMOUNT_PAISE,
        currency="INR",
        keyId=settings.RAZORPAY_KEY_ID,
        aiAnalyses=settings.TOPUP_AI_ANALYSES,
    )


# ── POST /payments/verify-topup ───────────────────────────────────────────────

class VerifyTopupIn(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


@router.post("/verify-topup")
def verify_topup(
    payload: VerifyTopupIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Step 2 of the top-up flow.
    Verifies the Razorpay payment signature and — if valid — credits
    TOPUP_AI_ANALYSES analyses to the user's current billing period.
    """
    if not settings.RAZORPAY_KEY_SECRET:
        raise HTTPException(503, "Payment gateway not configured")

    body = f"{payload.razorpay_order_id}|{payload.razorpay_payment_id}"
    if not _verify_signature(body, payload.razorpay_signature, settings.RAZORPAY_KEY_SECRET):
        raise HTTPException(400, "Payment verification failed — signature mismatch")

    result = subscription_service.purchase_topup(
        db,
        user_id=str(current_user.id),
        payment_reference=payload.razorpay_payment_id,
    )
    return result


# ── POST /payments/create-subscription ───────────────────────────────────────

class CreateSubscriptionOut(BaseModel):
    subscriptionId: str
    keyId: str
    amountPaise: int
    planType: str  # "early_bird" | "standard"


@router.post("/create-subscription", response_model=CreateSubscriptionOut)
def create_razorpay_subscription(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CreateSubscriptionOut:
    """
    Step 1 of the subscription flow.
    Creates a Razorpay recurring subscription (early-bird or standard based on
    current slot count). Returns subscription ID + public key for the modal.
    """
    client = _razorpay_client()

    # Determine early-bird eligibility by counting active users
    active_count: int = db.query(User).filter(User.is_active == True).count()
    is_early_bird = active_count < settings.EARLY_BIRD_SLOTS

    plan_id = (
        settings.RAZORPAY_EARLY_BIRD_PLAN_ID
        if is_early_bird
        else settings.RAZORPAY_STANDARD_PLAN_ID
    )
    amount_paise = (
        settings.EARLY_BIRD_PLAN_AMOUNT_PAISE
        if is_early_bird
        else settings.STANDARD_PLAN_AMOUNT_PAISE
    )
    plan_type = "early_bird" if is_early_bird else "standard"

    if not plan_id:
        raise HTTPException(
            503,
            "Razorpay plan IDs not configured. "
            "Set RAZORPAY_EARLY_BIRD_PLAN_ID / RAZORPAY_STANDARD_PLAN_ID in environment.",
        )

    try:
        subscription = client.subscription.create(
            {
                "plan_id": plan_id,
                "total_count": 12,      # 12 monthly billing cycles
                "quantity": 1,
                "customer_notify": 1,
                "notes": {
                    "user_id": str(current_user.id),
                    "plan_type": plan_type,
                },
            }
        )
    except Exception as exc:
        logger.exception("Razorpay subscription creation failed for user %s", current_user.id)
        raise HTTPException(502, f"Payment gateway error: {exc}")

    return CreateSubscriptionOut(
        subscriptionId=subscription["id"],
        keyId=settings.RAZORPAY_KEY_ID,
        amountPaise=amount_paise,
        planType=plan_type,
    )


# ── POST /payments/verify-subscription ───────────────────────────────────────

class VerifySubscriptionIn(BaseModel):
    razorpay_payment_id: str
    razorpay_subscription_id: str
    razorpay_signature: str


@router.post("/verify-subscription")
def verify_subscription(
    payload: VerifySubscriptionIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Step 2 of the subscription flow.
    Verifies the Razorpay payment signature and — if valid — upgrades the
    user's subscription to professional/active in the database.
    """
    if not settings.RAZORPAY_KEY_SECRET:
        raise HTTPException(503, "Payment gateway not configured")

    body = f"{payload.razorpay_payment_id}|{payload.razorpay_subscription_id}"
    if not _verify_signature(body, payload.razorpay_signature, settings.RAZORPAY_KEY_SECRET):
        raise HTTPException(400, "Subscription verification failed — signature mismatch")

    now = datetime.utcnow()
    sub = (
        db.query(Subscription)
        .filter(Subscription.user_id == str(current_user.id))
        .order_by(Subscription.created_at.desc())
        .first()
    )

    if sub:
        sub.plan = SubscriptionPlan.professional
        sub.status = SubscriptionStatus.active
        sub.razorpay_subscription_id = payload.razorpay_subscription_id
        sub.amount = settings.EARLY_BIRD_PLAN_AMOUNT_PAISE
        sub.start_date = now
        sub.end_date = now + timedelta(days=365)
        sub.updated_at = now
    else:
        sub = Subscription(
            user_id=str(current_user.id),
            plan=SubscriptionPlan.professional,
            status=SubscriptionStatus.active,
            billing_cycle=BillingCycle.monthly,
            amount=settings.EARLY_BIRD_PLAN_AMOUNT_PAISE,
            currency="INR",
            start_date=now,
            end_date=now + timedelta(days=365),
            auto_renew=True,
            razorpay_subscription_id=payload.razorpay_subscription_id,
        )
        db.add(sub)

    db.commit()
    return {
        "status": "active",
        "plan": "professional",
        "subscriptionId": payload.razorpay_subscription_id,
    }


# ── POST /payments/webhook ────────────────────────────────────────────────────

@router.post("/webhook")
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """
    Razorpay webhook receiver (no user auth — verified by HMAC signature).
    Register this URL in Razorpay Dashboard > Webhooks:
      https://your-api.com/api/v1/payments/webhook

    Events handled:
      subscription.activated  — mark plan as active
      subscription.charged    — log renewal (future: generate invoice)
      subscription.cancelled  — mark as cancelled, disable auto_renew
      subscription.halted     — treat as cancelled (payment failures)
      subscription.completed  — treat as cancelled (all cycles done)
    """
    body_bytes = await request.body()

    # Verify webhook signature when secret is configured (always do this in production)
    webhook_secret = (settings.RAZORPAY_WEBHOOK_SECRET or "").strip()
    if webhook_secret:
        if not x_razorpay_signature:
            logger.warning("Razorpay webhook missing signature header — request rejected")
            raise HTTPException(400, "Missing webhook signature")

        expected = hmac.new(
            webhook_secret.encode(),
            body_bytes,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, x_razorpay_signature.strip()):
            logger.warning("Razorpay webhook signature mismatch — request rejected")
            raise HTTPException(400, "Invalid webhook signature")

    event = json.loads(body_bytes)
    event_type: str = event.get("event", "")
    logger.info("Razorpay webhook received: %s", event_type)

    if event_type == "subscription.activated":
        _handle_sub_activated(event, db)
    elif event_type == "subscription.charged":
        _handle_sub_charged(event, db)
    elif event_type in (
        "subscription.cancelled",
        "subscription.halted",
        "subscription.completed",
    ):
        _handle_sub_cancelled(event, db)

    return {"status": "ok"}


# ── Webhook handlers ──────────────────────────────────────────────────────────

def _sub_entity(event: dict) -> dict:
    return event.get("payload", {}).get("subscription", {}).get("entity", {})


def _handle_sub_activated(event: dict, db: Session) -> None:
    sub_id = _sub_entity(event).get("id")
    if not sub_id:
        return
    sub = (
        db.query(Subscription)
        .filter(Subscription.razorpay_subscription_id == sub_id)
        .first()
    )
    if sub:
        sub.status = SubscriptionStatus.active
        sub.plan = SubscriptionPlan.professional
        db.commit()
        logger.info("Subscription activated via webhook: %s", sub_id)


def _handle_sub_charged(event: dict, db: Session) -> None:
    # Future: insert Invoice row for billing history
    sub_id = _sub_entity(event).get("id")
    logger.info("Subscription charged via webhook: %s", sub_id)


def _handle_sub_cancelled(event: dict, db: Session) -> None:
    sub_id = _sub_entity(event).get("id")
    if not sub_id:
        return
    sub = (
        db.query(Subscription)
        .filter(Subscription.razorpay_subscription_id == sub_id)
        .first()
    )
    if sub:
        sub.status = SubscriptionStatus.cancelled
        sub.auto_renew = False
        db.commit()
        logger.info("Subscription cancelled via webhook: %s", sub_id)
