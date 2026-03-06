"""
Subscription Management Routes
Manage subscription tiers, upgrades, and usage tracking
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List
import logging

from app.core import get_db, get_current_user
from app.models import Merchant, MerchantSubscription, SubscriptionTier, SubscriptionStatus
from app.schemas import (
    SubscriptionPlanInfo,
    SubscriptionResponse,
    SubscriptionUpgradeRequest,
    SubscriptionUpgradeResponse,
    SubscriptionUsageResponse,
    LocalCurrencyAmount,
)
from app.services.currency_service import get_currency_for_country, build_local_amount

router = APIRouter(prefix="/subscription", tags=["Subscription"])
logger = logging.getLogger(__name__)

# ============= SUBSCRIPTION PLAN DEFINITIONS =============

SUBSCRIPTION_PLANS = {
    "free": {
        "name": "Free",
        "monthly_price": 0,
        "transaction_fee_min": 1.0,
        "transaction_fee_max": 1.5,
        "monthly_volume_limit": 1000,
        "payment_link_limit": 2,
        "invoice_limit": 5,
        "team_member_limit": 1,
        "features": [
            "Payment links",
            "Basic checkout page",
            "Stablecoin payments",
            "Simple dashboard",
            "Basic analytics",
            "Manual payouts",
        ],
    },
    "growth": {
        "name": "Growth",
        "monthly_price": 29,
        "transaction_fee_min": 0.8,
        "transaction_fee_max": 1.0,
        "monthly_volume_limit": 50000,
        "payment_link_limit": None,  # unlimited
        "invoice_limit": None,
        "team_member_limit": 3,
        "features": [
            "All Free features",
            "Recurring payments",
            "Subscription billing",
            "Custom payment pages",
            "Full API access",
            "Webhooks",
            "CSV exports",
            "Custom checkout branding",
        ],
    },
    "business": {
        "name": "Business",
        "monthly_price": 99,
        "transaction_fee_min": 0.5,
        "transaction_fee_max": 0.8,
        "monthly_volume_limit": 500000,
        "payment_link_limit": None,
        "invoice_limit": None,
        "team_member_limit": 10,
        "features": [
            "All Growth features",
            "Multi-chain payments",
            "Multi-wallet settlement",
            "Automatic routing",
            "Advanced analytics",
            "Fraud monitoring",
            "Smart payment retries",
            "Advanced webhooks",
            "Multi-currency settlements",
            "Automated reconciliation",
        ],
    },
    "enterprise": {
        "name": "Enterprise",
        "monthly_price": 300,  # Starting price
        "transaction_fee_min": 0.2,
        "transaction_fee_max": 0.5,
        "monthly_volume_limit": None,  # unlimited
        "payment_link_limit": None,
        "invoice_limit": None,
        "team_member_limit": None,  # unlimited
        "features": [
            "All Business features",
            "Dedicated blockchain nodes",
            "Custom chain integrations",
            "Private deployment",
            "Fully white-labeled gateway",
            "SLA guarantees",
            "Compliance integrations",
            "Dedicated account manager",
            "Priority support",
        ],
    },
}


# ============= GET ALL PLANS =============

@router.get("/plans", response_model=List[SubscriptionPlanInfo])
async def get_subscription_plans():
    """Get all available subscription plans with pricing and features."""
    plans = []
    for tier, plan_info in SUBSCRIPTION_PLANS.items():
        plans.append(
            SubscriptionPlanInfo(
                tier=tier,
                name=plan_info["name"],
                monthly_price=plan_info["monthly_price"],
                transaction_fee_min=plan_info["transaction_fee_min"],
                transaction_fee_max=plan_info["transaction_fee_max"],
                monthly_volume_limit=plan_info["monthly_volume_limit"],
                payment_link_limit=plan_info["payment_link_limit"],
                invoice_limit=plan_info["invoice_limit"],
                team_member_limit=plan_info["team_member_limit"] or 999,
                features=plan_info["features"],
            )
        )
    return plans


# ============= GET CURRENT SUBSCRIPTION =============

@router.get("/current", response_model=SubscriptionResponse)
async def get_current_subscription(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get merchant's current subscription details."""
    merchant = db.query(Merchant).filter(Merchant.id == current_user["id"]).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    subscription = (
        db.query(MerchantSubscription)
        .filter(MerchantSubscription.merchant_id == merchant.id)
        .first()
    )

    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")

    currency_code, currency_symbol, _ = get_currency_for_country(merchant.country)

    monthly_price = float(subscription.monthly_price)
    current_volume = float(subscription.current_volume)
    volume_limit = float(subscription.monthly_volume_limit) if subscription.monthly_volume_limit else None

    price_local = await build_local_amount(monthly_price, currency_code, currency_symbol)
    volume_local = await build_local_amount(current_volume, currency_code, currency_symbol)
    vol_limit_local = await build_local_amount(volume_limit, currency_code, currency_symbol) if volume_limit else None

    return SubscriptionResponse(
        tier=subscription.tier,
        status=subscription.status,
        monthly_price=monthly_price,
        transaction_fee_percent=float(subscription.transaction_fee_percent),
        monthly_volume_limit=volume_limit,
        payment_link_limit=subscription.payment_link_limit,
        invoice_limit=subscription.invoice_limit,
        team_member_limit=subscription.team_member_limit,
        current_volume=current_volume,
        current_payment_links=subscription.current_payment_links,
        current_invoices=subscription.current_invoices,
        current_period_start=subscription.current_period_start,
        current_period_end=subscription.current_period_end,
        trial_ends_at=subscription.trial_ends_at,
        monthly_price_local=LocalCurrencyAmount(**price_local),
        current_volume_local=LocalCurrencyAmount(**volume_local),
        volume_limit_local=LocalCurrencyAmount(**vol_limit_local) if vol_limit_local else None,
    )


# ============= GET USAGE =============

@router.get("/usage", response_model=SubscriptionUsageResponse)
async def get_subscription_usage(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current billing period usage and limits."""
    merchant = db.query(Merchant).filter(Merchant.id == current_user["id"]).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    subscription = (
        db.query(MerchantSubscription)
        .filter(MerchantSubscription.merchant_id == merchant.id)
        .first()
    )

    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")

    # Calculate usage percentage
    volume_used_percent = None
    if subscription.monthly_volume_limit:
        volume_used_percent = (
            float(subscription.current_volume) / float(subscription.monthly_volume_limit) * 100
        )

    # Calculate days remaining
    days_remaining = (subscription.current_period_end - datetime.utcnow()).days

    currency_code, currency_symbol, _ = get_currency_for_country(merchant.country)
    current_volume = float(subscription.current_volume)
    volume_limit = float(subscription.monthly_volume_limit) if subscription.monthly_volume_limit else None

    vol_local = await build_local_amount(current_volume, currency_code, currency_symbol)
    vol_limit_local = await build_local_amount(volume_limit, currency_code, currency_symbol) if volume_limit else None

    return SubscriptionUsageResponse(
        tier=subscription.tier,
        current_volume=current_volume,
        volume_limit=volume_limit,
        volume_used_percent=volume_used_percent,
        payment_links_used=subscription.current_payment_links,
        payment_links_limit=subscription.payment_link_limit,
        invoices_used=subscription.current_invoices,
        invoices_limit=subscription.invoice_limit,
        team_members_used=1,  # TODO: Count actual team members
        team_members_limit=subscription.team_member_limit,
        period_end=subscription.current_period_end,
        days_remaining=max(0, days_remaining),
        current_volume_local=LocalCurrencyAmount(**vol_local),
        volume_limit_local=LocalCurrencyAmount(**vol_limit_local) if vol_limit_local else None,
    )


# ============= UPGRADE/DOWNGRADE SUBSCRIPTION =============

@router.post("/upgrade", response_model=SubscriptionUpgradeResponse)
async def upgrade_subscription(
    upgrade_request: SubscriptionUpgradeRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upgrade or downgrade subscription tier."""
    merchant = db.query(Merchant).filter(Merchant.id == current_user["id"]).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    subscription = (
        db.query(MerchantSubscription)
        .filter(MerchantSubscription.merchant_id == merchant.id)
        .first()
    )

    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")

    try:
        new_tier = upgrade_request.get_tier()
    except ValueError:
        raise HTTPException(status_code=400, detail="Either 'tier' or 'plan' must be provided")
    if new_tier not in SUBSCRIPTION_PLANS:
        raise HTTPException(status_code=400, detail=f"Invalid subscription tier '{new_tier}'. Must be one of: free, growth, business, enterprise")

    # Check if it's the same tier
    if subscription.tier == new_tier:
        raise HTTPException(
            status_code=400,
            detail="You are already on this plan",
        )

    # Get plan details
    plan = SUBSCRIPTION_PLANS[new_tier]

    # Update subscription
    subscription.tier = SubscriptionTier(new_tier)
    subscription.monthly_price = Decimal(str(plan["monthly_price"]))
    subscription.transaction_fee_percent = Decimal(
        str((plan["transaction_fee_min"] + plan["transaction_fee_max"]) / 2)
    )
    subscription.monthly_volume_limit = (
        Decimal(str(plan["monthly_volume_limit"]))
        if plan["monthly_volume_limit"]
        else None
    )
    subscription.payment_link_limit = plan["payment_link_limit"]
    subscription.invoice_limit = plan["invoice_limit"]
    subscription.team_member_limit = plan["team_member_limit"] or 999

    # Update merchant tier
    merchant.subscription_tier = new_tier

    # Reset usage counters if upgrading mid-period (optional)
    # subscription.current_volume = Decimal("0")
    # subscription.current_payment_links = 0
    # subscription.current_invoices = 0

    db.commit()
    db.refresh(subscription)

    logger.info(f"Merchant {merchant.id} changed subscription to {new_tier}")

    return SubscriptionUpgradeResponse(
        message=f"Successfully changed to {plan['name']} plan",
        new_tier=new_tier,
        new_monthly_price=float(subscription.monthly_price),
        effective_date=datetime.utcnow(),
        prorated_amount=None,  # TODO: Calculate proration
    )


# ============= CANCEL SUBSCRIPTION =============

@router.post("/cancel")
async def cancel_subscription(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cancel subscription (downgrade to free at end of billing period)."""
    merchant = db.query(Merchant).filter(Merchant.id == current_user["id"]).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    subscription = (
        db.query(MerchantSubscription)
        .filter(MerchantSubscription.merchant_id == merchant.id)
        .first()
    )

    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")

    if subscription.tier == SubscriptionTier.FREE:
        raise HTTPException(
            status_code=400,
            detail="Cannot cancel free plan",
        )

    # Mark as cancelled (will downgrade to free at period end)
    subscription.status = SubscriptionStatus.CANCELLED
    subscription.cancelled_at = datetime.utcnow()

    db.commit()

    logger.info(
        f"Merchant {merchant.id} cancelled subscription. Will downgrade at {subscription.current_period_end}"
    )

    return {
        "message": "Subscription cancelled successfully",
        "current_tier": subscription.tier,
        "downgrade_date": subscription.current_period_end,
        "access_until": subscription.current_period_end,
    }


# ============= REACTIVATE SUBSCRIPTION =============

@router.post("/reactivate")
async def reactivate_subscription(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Reactivate a cancelled subscription."""
    merchant = db.query(Merchant).filter(Merchant.id == current_user["id"]).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    subscription = (
        db.query(MerchantSubscription)
        .filter(MerchantSubscription.merchant_id == merchant.id)
        .first()
    )

    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")

    if subscription.status != SubscriptionStatus.CANCELLED:
        raise HTTPException(
            status_code=400,
            detail="Subscription is not cancelled",
        )

    # Reactivate
    subscription.status = SubscriptionStatus.ACTIVE
    subscription.cancelled_at = None

    db.commit()

    logger.info(f"Merchant {merchant.id} reactivated subscription")

    return {
        "message": "Subscription reactivated successfully",
        "tier": subscription.tier,
        "status": "active",
        "current_period_end": subscription.current_period_end,
    }
