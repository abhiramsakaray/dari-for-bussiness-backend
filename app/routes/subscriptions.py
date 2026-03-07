"""
Subscriptions API Routes
Recurring payment management for merchants
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
import secrets
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, List

from app.core.database import get_db
from app.core import require_merchant
from app.models.models import (
    Merchant, SubscriptionPlan, Subscription, SubscriptionPayment,
    SubscriptionStatus as DBSubscriptionStatus,
    SubscriptionInterval as DBSubscriptionInterval,
    PaymentStatus
)
from app.schemas.schemas import (
    SubscriptionPlanCreate, SubscriptionPlanUpdate, SubscriptionPlanResponse,
    SubscriptionCreate, RecurringSubscriptionResponse, SubscriptionList, SubscriptionCancel,
    SubscriptionStatus, SubscriptionInterval
)

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])


def generate_plan_id() -> str:
    """Generate a unique plan ID"""
    return f"plan_{secrets.token_urlsafe(12)}"


def generate_subscription_id() -> str:
    """Generate a unique subscription ID"""
    return f"sub_{secrets.token_urlsafe(12)}"


def calculate_next_billing_date(current_date: datetime, interval: str, interval_count: int = 1) -> datetime:
    """Calculate the next billing date based on interval"""
    if interval == "daily":
        return current_date + timedelta(days=interval_count)
    elif interval == "weekly":
        return current_date + timedelta(weeks=interval_count)
    elif interval == "monthly":
        # Add months (approximately)
        days = 30 * interval_count
        return current_date + timedelta(days=days)
    elif interval == "quarterly":
        return current_date + timedelta(days=90 * interval_count)
    elif interval == "yearly":
        return current_date + timedelta(days=365 * interval_count)
    return current_date + timedelta(days=30)


# ========================
# SUBSCRIPTION PLANS
# ========================

@router.post("/plans", response_model=SubscriptionPlanResponse)
async def create_plan(
    plan_data: SubscriptionPlanCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant)
):
    """
    Create a new subscription plan.
    
    Plans define the pricing and billing cycle for subscriptions.
    Multiple customers can subscribe to the same plan.
    """
    merchant = db.query(Merchant).filter(Merchant.id == uuid.UUID(current_user["id"])).first()
    plan_id = generate_plan_id()
    
    # Convert interval enum to DB enum
    db_interval = DBSubscriptionInterval(plan_data.interval.value)
    
    plan = SubscriptionPlan(
        id=plan_id,
        merchant_id=merchant.id,
        name=plan_data.name,
        description=plan_data.description,
        amount=plan_data.amount,
        fiat_currency=plan_data.fiat_currency.upper(),
        interval=db_interval,
        interval_count=plan_data.interval_count,
        trial_days=plan_data.trial_days,
        accepted_tokens=plan_data.accepted_tokens or merchant.accepted_tokens,
        accepted_chains=plan_data.accepted_chains or merchant.accepted_chains,
        features=plan_data.features,
        plan_metadata=plan_data.metadata
    )
    
    db.add(plan)
    db.commit()
    db.refresh(plan)
    
    return build_plan_response(plan, db)


@router.get("/plans", response_model=List[SubscriptionPlanResponse])
async def list_plans(
    is_active: Optional[bool] = True,
    db: Session = Depends(get_db)
):
    """List all subscription plans for the merchant."""
    try:
        # TEMP: Show all data (no auth)
        query = db.query(SubscriptionPlan)
        
        if is_active is not None:
            query = query.filter(SubscriptionPlan.is_active == is_active)
        
        plans = query.order_by(SubscriptionPlan.created_at.desc()).all()
        
        return [build_plan_response(plan, db) for plan in plans]
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error listing subscription plans: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list subscription plans: {str(e)}"
        )


@router.get("/plans/{plan_id}", response_model=SubscriptionPlanResponse)
async def get_plan(
    plan_id: str,
    db: Session = Depends(get_db)
):
    """Get a specific subscription plan."""
    # TEMP: Show all data (no auth)
    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == plan_id).first()
    
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    
    return build_plan_response(plan, db)


@router.patch("/plans/{plan_id}", response_model=SubscriptionPlanResponse)
async def update_plan(
    plan_id: str,
    update_data: SubscriptionPlanUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant)
):
    """
    Update a subscription plan.
    
    Note: Price changes only affect new subscriptions, not existing ones.
    """
    plan = db.query(SubscriptionPlan).filter(
        and_(
            SubscriptionPlan.id == plan_id,
            SubscriptionPlan.merchant_id == uuid.UUID(current_user["id"])
        )
    ).first()
    
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    
    update_fields = update_data.model_dump(exclude_unset=True)
    
    for field, value in update_fields.items():
        setattr(plan, field, value)
    
    plan.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(plan)
    
    return build_plan_response(plan, db)


@router.delete("/plans/{plan_id}")
async def archive_plan(
    plan_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant)
):
    """
    Archive a subscription plan.
    
    Archived plans cannot accept new subscriptions but existing ones continue.
    """
    plan = db.query(SubscriptionPlan).filter(
        and_(
            SubscriptionPlan.id == plan_id,
            SubscriptionPlan.merchant_id == uuid.UUID(current_user["id"])
        )
    ).first()
    
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    
    plan.is_active = False
    plan.updated_at = datetime.utcnow()
    db.commit()
    
    return {"message": "Plan archived", "id": plan_id}


# ========================
# SUBSCRIPTIONS
# ========================

@router.post("", response_model=RecurringSubscriptionResponse)
async def create_subscription(
    sub_data: SubscriptionCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant)
):
    """
    Create a new subscription for a customer.
    
    This enrolls a customer in a subscription plan.
    The first payment is collected immediately unless a trial period applies.
    """
    # Verify plan exists and belongs to merchant
    plan = db.query(SubscriptionPlan).filter(
        and_(
            SubscriptionPlan.id == sub_data.plan_id,
            SubscriptionPlan.merchant_id == uuid.UUID(current_user["id"]),
            SubscriptionPlan.is_active == True
        )
    ).first()
    
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found or inactive")
    
    # Check for existing active subscription
    existing = db.query(Subscription).filter(
        and_(
            Subscription.plan_id == plan.id,
            Subscription.customer_email == sub_data.customer_email,
            Subscription.status.in_([
                DBSubscriptionStatus.ACTIVE,
                DBSubscriptionStatus.TRIALING,
                DBSubscriptionStatus.PAST_DUE
            ])
        )
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=400,
            detail="Customer already has an active subscription to this plan"
        )
    
    subscription_id = generate_subscription_id()
    now = datetime.utcnow()
    
    # Determine trial period
    trial_start = None
    trial_end = None
    initial_status = DBSubscriptionStatus.ACTIVE
    
    if plan.trial_days > 0 and not sub_data.skip_trial:
        trial_start = now
        trial_end = now + timedelta(days=plan.trial_days)
        initial_status = DBSubscriptionStatus.TRIALING
        period_start = trial_start
        period_end = trial_end
    else:
        period_start = now
        interval_value = plan.interval.value if hasattr(plan.interval, 'value') else plan.interval
        period_end = calculate_next_billing_date(now, interval_value, plan.interval_count)
    
    subscription = Subscription(
        id=subscription_id,
        plan_id=plan.id,
        merchant_id=uuid.UUID(current_user["id"]),
        customer_email=sub_data.customer_email,
        customer_name=sub_data.customer_name,
        customer_id=sub_data.customer_id,
        status=initial_status,
        current_period_start=period_start,
        current_period_end=period_end,
        billing_anchor=now,
        trial_start=trial_start,
        trial_end=trial_end,
        next_payment_at=period_end if initial_status == DBSubscriptionStatus.TRIALING else now,
        subscription_metadata=sub_data.metadata
    )
    
    db.add(subscription)
    db.commit()
    db.refresh(subscription)
    
    return build_subscription_response(subscription, request)


@router.get("", response_model=SubscriptionList)
async def list_subscriptions(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: Optional[SubscriptionStatus] = None,
    plan_id: Optional[str] = None,
    customer_email: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    List all subscriptions for the merchant.
    
    Supports filtering by status, plan, and customer.
    """
    # TEMP: Show all data (no auth)
    query = db.query(Subscription)
    
    if status:
        query = query.filter(Subscription.status == status.value)
    
    if plan_id:
        query = query.filter(Subscription.plan_id == plan_id)
    
    if customer_email:
        query = query.filter(Subscription.customer_email.ilike(f"%{customer_email}%"))
    
    total = query.count()
    
    subscriptions = query.order_by(Subscription.created_at.desc())\
        .offset((page - 1) * page_size)\
        .limit(page_size)\
        .all()
    
    return SubscriptionList(
        subscriptions=[build_subscription_response(sub, request) for sub in subscriptions],
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/{subscription_id}", response_model=RecurringSubscriptionResponse)
async def get_subscription(
    subscription_id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Get a specific subscription."""
    # TEMP: Show all data (no auth)
    subscription = db.query(Subscription).filter(Subscription.id == subscription_id).first()
    
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")
    
    return build_subscription_response(subscription, request)


@router.post("/{subscription_id}/cancel")
async def cancel_subscription(
    subscription_id: str,
    cancel_data: SubscriptionCancel,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant)
):
    """
    Cancel a subscription.
    
    Options:
    - Cancel immediately: Ends subscription right away
    - Cancel at period end: Subscription continues until current period ends
    """
    subscription = db.query(Subscription).filter(
        and_(
            Subscription.id == subscription_id,
            Subscription.merchant_id == uuid.UUID(current_user["id"])
        )
    ).first()
    
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")
    
    if subscription.status == DBSubscriptionStatus.CANCELLED:
        raise HTTPException(status_code=400, detail="Subscription already cancelled")
    
    subscription.cancelled_at = datetime.utcnow()
    subscription.cancel_reason = cancel_data.reason
    
    if cancel_data.cancel_immediately:
        subscription.status = DBSubscriptionStatus.CANCELLED
        subscription.cancel_at = datetime.utcnow()
    else:
        # Cancel at end of current period
        subscription.cancel_at = subscription.current_period_end
    
    subscription.updated_at = datetime.utcnow()
    db.commit()
    
    return {
        "message": "Subscription cancelled",
        "subscription_id": subscription_id,
        "cancels_at": subscription.cancel_at.isoformat()
    }


@router.post("/{subscription_id}/pause")
async def pause_subscription(
    subscription_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant)
):
    """
    Pause a subscription.
    
    Paused subscriptions stop billing but can be resumed later.
    """
    subscription = db.query(Subscription).filter(
        and_(
            Subscription.id == subscription_id,
            Subscription.merchant_id == uuid.UUID(current_user["id"])
        )
    ).first()
    
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")
    
    if subscription.status not in [DBSubscriptionStatus.ACTIVE, DBSubscriptionStatus.TRIALING]:
        raise HTTPException(
            status_code=400,
            detail="Can only pause active or trialing subscriptions"
        )
    
    subscription.status = DBSubscriptionStatus.PAUSED
    subscription.updated_at = datetime.utcnow()
    db.commit()
    
    return {"message": "Subscription paused", "subscription_id": subscription_id}


@router.post("/{subscription_id}/resume")
async def resume_subscription(
    subscription_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant)
):
    """
    Resume a paused subscription.
    
    Billing resumes with a new period starting now.
    """
    subscription = db.query(Subscription).filter(
        and_(
            Subscription.id == subscription_id,
            Subscription.merchant_id == uuid.UUID(current_user["id"])
        )
    ).first()
    
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")
    
    if subscription.status != DBSubscriptionStatus.PAUSED:
        raise HTTPException(
            status_code=400,
            detail="Can only resume paused subscriptions"
        )
    
    # Start new billing period
    now = datetime.utcnow()
    plan = subscription.plan
    
    interval_value = plan.interval.value if hasattr(plan.interval, 'value') else plan.interval
    subscription.current_period_start = now
    subscription.current_period_end = calculate_next_billing_date(
        now, interval_value, plan.interval_count
    )
    subscription.status = DBSubscriptionStatus.ACTIVE
    subscription.next_payment_at = now
    subscription.updated_at = now
    
    db.commit()
    db.refresh(subscription)
    
    return build_subscription_response(subscription, request)


@router.get("/{subscription_id}/payments")
async def list_subscription_payments(
    subscription_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """List all payments for a subscription."""
    # TEMP: Show all data (no auth)
    subscription = db.query(Subscription).filter(Subscription.id == subscription_id).first()
    
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")
    
    query = db.query(SubscriptionPayment).filter(
        SubscriptionPayment.subscription_id == subscription_id
    )
    
    total = query.count()
    
    payments = query.order_by(SubscriptionPayment.created_at.desc())\
        .offset((page - 1) * page_size)\
        .limit(page_size)\
        .all()
    
    return {
        "subscription_id": subscription_id,
        "payments": [
            {
                "id": str(p.id),
                "period_start": p.period_start.isoformat(),
                "period_end": p.period_end.isoformat(),
                "amount": float(p.amount),
                "currency": p.fiat_currency,
                "status": p.status.value if hasattr(p.status, 'value') else p.status,
                "paid_at": p.paid_at.isoformat() if p.paid_at else None,
                "payment_session_id": p.payment_session_id
            }
            for p in payments
        ],
        "total": total,
        "page": page,
        "page_size": page_size
    }


# ========================
# HELPERS
# ========================

def build_plan_response(plan: SubscriptionPlan, db: Session) -> SubscriptionPlanResponse:
    """Build SubscriptionPlanResponse from model"""
    try:
        # Count active subscribers
        subscriber_count = db.query(func.count(Subscription.id)).filter(
            and_(
                Subscription.plan_id == plan.id,
                Subscription.status.in_([
                    DBSubscriptionStatus.ACTIVE,
                    DBSubscriptionStatus.TRIALING,
                    DBSubscriptionStatus.PAUSED
                ])
            )
        ).scalar()
        
        return SubscriptionPlanResponse(
            id=plan.id,
            name=plan.name,
            description=plan.description,
            amount=plan.amount,
            fiat_currency=plan.fiat_currency,
            interval=plan.interval.value if hasattr(plan.interval, 'value') else plan.interval,
            interval_count=plan.interval_count,
            trial_days=plan.trial_days,
            accepted_tokens=plan.accepted_tokens or [],
            accepted_chains=plan.accepted_chains or [],
            is_active=plan.is_active,
            features=plan.features,
            subscriber_count=subscriber_count or 0,
            created_at=plan.created_at
        )
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error building plan response for plan {plan.id}: {e}", exc_info=True)
        # Return with default values if there's an error counting subscribers
        return SubscriptionPlanResponse(
            id=plan.id,
            name=plan.name,
            description=plan.description,
            amount=plan.amount,
            fiat_currency=plan.fiat_currency,
            interval=plan.interval.value if hasattr(plan.interval, 'value') else plan.interval,
            interval_count=plan.interval_count,
            trial_days=plan.trial_days,
            accepted_tokens=plan.accepted_tokens or [],
            accepted_chains=plan.accepted_chains or [],
            is_active=plan.is_active,
            features=plan.features,
            subscriber_count=0,
            created_at=plan.created_at
        )


def build_subscription_response(subscription: Subscription, request: Request) -> RecurringSubscriptionResponse:
    """Build RecurringSubscriptionResponse from model"""""
    # Get plan name
    plan_name = subscription.plan.name if subscription.plan else "Unknown"
    
    # Generate payment URL if needed
    next_payment_url = None
    if subscription.status in [DBSubscriptionStatus.ACTIVE, DBSubscriptionStatus.PAST_DUE]:
        base_url = str(request.base_url).rstrip("/")
        next_payment_url = f"{base_url}/subscription/{subscription.id}/pay"
    
    return RecurringSubscriptionResponse(
        id=subscription.id,
        plan_id=subscription.plan_id,
        plan_name=plan_name,
        customer_email=subscription.customer_email,
        customer_name=subscription.customer_name,
        customer_id=subscription.customer_id,
        status=subscription.status.value if hasattr(subscription.status, 'value') else subscription.status,
        current_period_start=subscription.current_period_start,
        current_period_end=subscription.current_period_end,
        trial_start=subscription.trial_start,
        trial_end=subscription.trial_end,
        next_payment_at=subscription.next_payment_at,
        next_payment_url=next_payment_url,
        cancel_at=subscription.cancel_at,
        cancelled_at=subscription.cancelled_at,
        created_at=subscription.created_at
    )
