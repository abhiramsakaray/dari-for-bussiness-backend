"""
Billing Routes - Alias for Subscription Management
Provides /billing/* endpoints that map to subscription functionality
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List

from app.core import get_db, get_current_user
from app.schemas import SubscriptionPlanInfo, SubscriptionResponse, SubscriptionUsageResponse, SubscriptionUpgradeRequest, SubscriptionUpgradeResponse
from app.routes.subscription_management import (
    get_current_subscription,
    get_subscription_usage,
    get_subscription_plans,
    upgrade_subscription,
)

router = APIRouter(prefix="/billing", tags=["Billing"])


@router.get("/info", response_model=SubscriptionResponse)
async def get_billing_info(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get current billing/subscription information.
    Alias for GET /subscription/current
    """
    return await get_current_subscription(current_user, db)


@router.get("/usage", response_model=SubscriptionUsageResponse)
async def get_billing_usage(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get current billing period usage statistics.
    Alias for GET /subscription/usage
    """
    return await get_subscription_usage(current_user, db)


@router.get("/plans", response_model=List[SubscriptionPlanInfo])
async def get_billing_plans():
    """
    Get available billing/subscription plans.
    Alias for GET /subscription/plans
    """
    return await get_subscription_plans()


@router.post("/change-plan", response_model=SubscriptionUpgradeResponse)
async def change_billing_plan(
    upgrade_request: SubscriptionUpgradeRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Change subscription plan (upgrade or downgrade).
    Alias for POST /subscription/upgrade
    """
    return await upgrade_subscription(upgrade_request, current_user, db)
