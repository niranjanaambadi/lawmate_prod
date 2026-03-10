"""
Subscription & billing business logic.

Models are aligned to webapp/prisma/schema.prisma.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import (
    AIAnalysis,
    AIAnalysisStatus,
    Case,
    Document,
    Invoice,
    InvoiceStatus,
    BillingCycle,
    Subscription,
    SubscriptionPlan,
    SubscriptionStatus,
    UsageTracking,
    UsageTopup,
)

# ---------------------------------------------------------------------------
# Plan limits — single source of truth for enforcement + UI display
# ---------------------------------------------------------------------------
PLAN_LIMITS: Dict[str, Dict[str, Any]] = {
    "free": {
        "cases": 5,
        "documents": 10,
        "storage_gb": 1,
        "ai_analyses": 5,
    },
    "professional": {
        "cases": 15,
        "documents": 60,
        "storage_gb": 30,
        "ai_analyses": 100,
    },
    "enterprise": {
        "cases": 999_999,
        "documents": 999_999,
        "storage_gb": 999_999,
        "ai_analyses": 999_999,
    },
}

TOPUP_AI_ANALYSES = 20   # units added per ₹200 top-up
TOPUP_PRICE_INR   = 200


def get_plan_limits(plan_name: str) -> Dict[str, Any]:
    return PLAN_LIMITS.get(plan_name, PLAN_LIMITS["free"])


def _enum_out(value) -> Optional[str]:
    """
    Frontend uses Prisma enums (UPPERCASE names).
    Our SQLAlchemy enums store lowercase values.
    Return Prisma-style UPPERCASE name when possible.
    """
    if value is None:
        return None
    try:
        return value.name.upper()
    except Exception:
        return str(value)


def _subscription_to_api(sub: Subscription) -> Dict[str, Any]:
    return {
        "id": str(sub.id),
        "userId": str(sub.user_id),
        "plan": _enum_out(sub.plan),
        "status": _enum_out(sub.status),
        "billingCycle": _enum_out(sub.billing_cycle),
        "amount": sub.amount,
        "currency": sub.currency,
        "startDate": sub.start_date,
        "endDate": sub.end_date,
        "trialEndDate": sub.trial_end_date,
        "autoRenew": sub.auto_renew,
        "paymentMethod": _enum_out(sub.payment_method),
        "createdAt": sub.created_at,
        "updatedAt": sub.updated_at,
    }


def _invoice_to_api(inv: Invoice) -> Dict[str, Any]:
    return {
        "id": str(inv.id),
        "subscriptionId": str(inv.subscription_id),
        "amount": inv.amount,
        "currency": inv.currency,
        "status": _enum_out(inv.status),
        "invoiceDate": inv.invoice_date,
        "dueDate": inv.due_date,
        "paidDate": inv.paid_date,
        "paymentMethod": _enum_out(inv.payment_method),
        "invoiceUrl": inv.invoice_url,
        "createdAt": inv.created_at,
    }


def get_or_create_current_subscription(db: Session, user_id: str) -> Dict[str, Any]:
    """
    Return current subscription row. If missing, create a default TRIAL/FREE.
    """
    sub = (
        db.query(Subscription)
        .filter(Subscription.user_id == user_id)
        .order_by(Subscription.created_at.desc())
        .first()
    )
    if not sub:
        now = datetime.utcnow()
        sub = Subscription(
            user_id=user_id,
            plan=SubscriptionPlan.free,
            status=SubscriptionStatus.trial,
            billing_cycle=BillingCycle.monthly,
            amount=0,
            currency="INR",
            start_date=now,
            end_date=now + timedelta(days=30),
            trial_end_date=now + timedelta(days=7),
            auto_renew=True,
            payment_method=None,
        )
        db.add(sub)
        db.commit()
        db.refresh(sub)

    return _subscription_to_api(sub)


def get_all_plans() -> List[Dict]:
    """
    Return available subscription plans
    """
    return [
        {
            "id": "free",
            "name": "Free",
            "description": "Perfect for getting started",
            "price_monthly": 0,
            "price_annually": 0,
            "features": {
                "max_cases": 50,
                "max_documents": 500,
                "ai_analyses_per_month": 10,
                "storage_gb": 5,
                "priority_support": False,
                "api_access": False,
                "custom_branding": False,
                "multi_user": False,
                "advanced_reports": False
            },
            "popular": False
        },
        {
            "id": "professional",
            "name": "Professional",
            "description": "For busy advocates managing many cases",
            "price_monthly": 999,
            "price_annually": 9990,
            "features": {
                "max_cases": "unlimited",
                "max_documents": "unlimited",
                "ai_analyses_per_month": 100,
                "storage_gb": 100,
                "priority_support": True,
                "api_access": True,
                "custom_branding": False,
                "multi_user": False,
                "advanced_reports": True
            },
            "popular": True
        },
        {
            "id": "enterprise",
            "name": "Enterprise",
            "description": "For law firms with multiple advocates",
            "price_monthly": 4999,
            "price_annually": 49990,
            "features": {
                "max_cases": "unlimited",
                "max_documents": "unlimited",
                "ai_analyses_per_month": "unlimited",
                "storage_gb": "unlimited",
                "priority_support": True,
                "api_access": True,
                "custom_branding": True,
                "multi_user": True,
                "advanced_reports": True
            },
            "popular": False
        }
    ]


def get_usage_stats(db: Session, user_id: str) -> Dict[str, Any]:
    """
    Return current-period usage alongside the user's plan limits.
    AI analyses are read directly from the ai_analyses table (completed, this month).
    Top-up buckets purchased this month are summed and added to the effective AI limit.
    A UsageTracking snapshot is upserted for audit / CloudWatch export.
    """
    now = datetime.utcnow()
    period_start = datetime(now.year, now.month, 1)

    # ── Plan ────────────────────────────────────────────────────────────────
    sub = (
        db.query(Subscription)
        .filter(Subscription.user_id == user_id)
        .order_by(Subscription.created_at.desc())
        .first()
    )
    plan_name = sub.plan.value if sub else "free"
    limits = get_plan_limits(plan_name)

    # ── Top-ups purchased this billing period ───────────────────────────────
    topups_ai: int = (
        db.query(func.sum(UsageTopup.ai_analyses_added))
        .filter(
            UsageTopup.user_id == user_id,
            UsageTopup.period_start >= period_start,
        )
        .scalar()
    ) or 0

    # ── Cases ───────────────────────────────────────────────────────────────
    cases_count: int = (
        db.query(Case)
        .filter(Case.advocate_id == user_id, Case.is_visible == True)
        .count()
    )

    # ── Documents ───────────────────────────────────────────────────────────
    documents_count: int = (
        db.query(Document)
        .join(Case)
        .filter(Case.advocate_id == user_id)
        .count()
    )

    # ── Storage ─────────────────────────────────────────────────────────────
    storage_bytes: int = (
        db.query(func.sum(Document.file_size))
        .join(Case)
        .filter(Case.advocate_id == user_id)
        .scalar()
    ) or 0

    # ── AI Analyses (completed this billing month) ───────────────────────────
    ai_analyses_used: int = (
        db.query(AIAnalysis)
        .filter(
            AIAnalysis.advocate_id == user_id,
            AIAnalysis.status == AIAnalysisStatus.completed,
            AIAnalysis.created_at >= period_start,
        )
        .count()
    )

    # ── Upsert UsageTracking snapshot ────────────────────────────────────────
    tracking = (
        db.query(UsageTracking)
        .filter(
            UsageTracking.user_id == user_id,
            UsageTracking.period_start == period_start,
        )
        .first()
    )
    if tracking:
        tracking.cases_count = cases_count
        tracking.documents_count = documents_count
        tracking.storage_used_bytes = storage_bytes
        tracking.ai_analyses_used = ai_analyses_used
        tracking.updated_at = now
    else:
        tracking = UsageTracking(
            user_id=user_id,
            period_start=period_start,
            period_end=now,
            cases_count=cases_count,
            documents_count=documents_count,
            storage_used_bytes=storage_bytes,
            ai_analyses_used=ai_analyses_used,
        )
        db.add(tracking)
    db.commit()

    effective_ai_limit = limits["ai_analyses"] + topups_ai

    return {
        "periodStart": period_start,
        "periodEnd": now,
        "plan": plan_name,
        "casesCount": cases_count,
        "documentsCount": documents_count,
        "storageUsedGb": float(round(storage_bytes / (1024 ** 3), 4)),
        "aiAnalysesUsed": ai_analyses_used,
        "topupsAiAdded": topups_ai,
        "limits": {
            "cases": limits["cases"],
            "documents": limits["documents"],
            "storageGb": limits["storage_gb"],
            "aiAnalyses": effective_ai_limit,
        },
    }


def check_ai_limit(db: Session, user_id: str) -> bool:
    """
    Returns True if the user may still run an AI analysis this month.
    Checks base plan limit + any purchased top-ups.
    """
    now = datetime.utcnow()
    period_start = datetime(now.year, now.month, 1)

    sub = (
        db.query(Subscription)
        .filter(Subscription.user_id == user_id)
        .order_by(Subscription.created_at.desc())
        .first()
    )
    plan_name = sub.plan.value if sub else "free"
    base_limit = get_plan_limits(plan_name)["ai_analyses"]

    topups_ai: int = (
        db.query(func.sum(UsageTopup.ai_analyses_added))
        .filter(
            UsageTopup.user_id == user_id,
            UsageTopup.period_start >= period_start,
        )
        .scalar()
    ) or 0

    ai_used: int = (
        db.query(AIAnalysis)
        .filter(
            AIAnalysis.advocate_id == user_id,
            AIAnalysis.status == AIAnalysisStatus.completed,
            AIAnalysis.created_at >= period_start,
        )
        .count()
    )

    return ai_used < (base_limit + topups_ai)


def purchase_topup(
    db: Session, user_id: str, payment_reference: Optional[str] = None
) -> Dict[str, Any]:
    """
    Record a ₹200 top-up purchase (+20 AI analyses for the current billing period).
    In production, only call this after Razorpay payment verification.
    """
    now = datetime.utcnow()
    period_start = datetime(now.year, now.month, 1)

    topup = UsageTopup(
        user_id=user_id,
        period_start=period_start,
        ai_analyses_added=TOPUP_AI_ANALYSES,
        amount_paid=TOPUP_PRICE_INR,
        currency="INR",
        payment_reference=payment_reference,
    )
    db.add(topup)
    db.commit()
    db.refresh(topup)

    return {
        "id": str(topup.id),
        "aiAnalysesAdded": topup.ai_analyses_added,
        "amountPaid": topup.amount_paid,
        "currency": topup.currency,
        "periodStart": topup.period_start,
        "createdAt": topup.created_at,
    }


def get_invoices(db: Session, user_id: str):
    """
    Get billing history for user's subscriptions.
    """
    sub_ids = [row[0] for row in db.query(Subscription.id).filter(Subscription.user_id == user_id).all()]
    if not sub_ids:
        return []
    invoices = (
        db.query(Invoice)
        .filter(Invoice.subscription_id.in_(sub_ids))
        .order_by(Invoice.created_at.desc())
        .all()
    )
    return [_invoice_to_api(i) for i in invoices]


def upgrade_plan(db: Session, user_id: str, plan: str, billing_cycle: str):
    """
    Initiate plan upgrade (return mock checkout URL)
    In production, integrate with Razorpay/Stripe
    """
    # Mock checkout URL
    checkout_url = f"https://checkout.lawmate.in/{plan}?user={user_id}&cycle={billing_cycle}"
    return checkout_url


def cancel_subscription(db: Session, user_id: str, reason: str = None):
    """
    Cancel subscription
    """
    # In production, update subscription status in database
    pass


def update_payment_method(db: Session, user_id: str, payment_method: str):
    """
    Update payment method
    """
    # In production, update in payment gateway
    pass


def toggle_auto_renew(db: Session, user_id: str, auto_renew: bool):
    """
    Enable/disable auto-renewal
    """
    # In production, update subscription settings
    pass