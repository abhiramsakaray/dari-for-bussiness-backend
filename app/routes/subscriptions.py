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


def _get_subscribe_url(request: Request, plan_id: str) -> str:
    """Generate the public subscribe URL for a plan."""
    if not request:
        return None
    base_url = str(request.base_url).rstrip("/")
    return f"{base_url}/subscribe/{plan_id}"


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
    request: Request,
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
        fiat_currency=(plan_data.fiat_currency or merchant.base_currency).upper(),
        interval=db_interval,
        interval_count=plan_data.interval_count,
        trial_days=plan_data.trial_days,
        trial_type=plan_data.trial_type,
        trial_price=plan_data.trial_price,
        setup_fee=plan_data.setup_fee,
        accepted_tokens=plan_data.accepted_tokens or merchant.accepted_tokens,
        accepted_chains=plan_data.accepted_chains or merchant.accepted_chains,
        max_billing_cycles=plan_data.max_billing_cycles,
        features=plan_data.features,
        plan_metadata=plan_data.metadata
    )
    
    db.add(plan)
    db.commit()
    db.refresh(plan)
    
    return build_plan_response(plan, db, request)


@router.get("/plans", response_model=List[SubscriptionPlanResponse])
async def list_plans(
    request: Request,
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
        
        return [build_plan_response(plan, db, request) for plan in plans]
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
    request: Request,
    db: Session = Depends(get_db)
):
    """Get a specific subscription plan."""
    # TEMP: Show all data (no auth)
    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == plan_id).first()
    
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    
    return build_plan_response(plan, db, request)


@router.patch("/plans/{plan_id}", response_model=SubscriptionPlanResponse)
async def update_plan(
    plan_id: str,
    update_data: SubscriptionPlanUpdate,
    request: Request,
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
    
    return build_plan_response(plan, db, request)


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
                DBSubscriptionStatus.PENDING_PAYMENT,
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
    initial_status = DBSubscriptionStatus.PENDING_PAYMENT
    
    # Allow custom trial days override
    effective_trial_days = plan.trial_days
    if sub_data.custom_trial_days is not None:
        effective_trial_days = sub_data.custom_trial_days
    
    if effective_trial_days > 0 and not sub_data.skip_trial:
        trial_start = now
        trial_end = now + timedelta(days=effective_trial_days)
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
        customer_wallet_address=sub_data.customer_wallet_address,
        customer_chain=sub_data.customer_chain,
        customer_token=sub_data.customer_token,
        subscription_metadata=sub_data.metadata
    )
    
    db.add(subscription)
    
    # If not trialing (or trial is free with setup fee), create first payment record
    if initial_status == DBSubscriptionStatus.PENDING_PAYMENT or (plan.setup_fee and plan.setup_fee > 0):
        first_amount = plan.amount if initial_status == DBSubscriptionStatus.PENDING_PAYMENT else plan.setup_fee
        
        # For reduced_price trials, charge the trial price
        if initial_status == DBSubscriptionStatus.TRIALING and plan.trial_type == "reduced_price" and plan.trial_price is not None:
            first_amount = plan.trial_price
        
        if first_amount and first_amount > 0:
            first_payment = SubscriptionPayment(
                subscription_id=subscription_id,
                period_start=period_start,
                period_end=period_end,
                amount=first_amount,
                fiat_currency=plan.fiat_currency,
                status=PaymentStatus.CREATED
            )
            db.add(first_payment)
    
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
# TRIAL MANAGEMENT
# ========================

@router.post("/{subscription_id}/extend-trial")
async def extend_trial(
    subscription_id: str,
    extra_days: int = Query(..., ge=1, le=90, description="Number of days to extend the trial"),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant)
):
    """
    Extend a subscription's free trial period.
    
    Can only extend trials that are currently active (status = trialing).
    The trial end date and current period end are both extended.
    """
    subscription = db.query(Subscription).filter(
        and_(
            Subscription.id == subscription_id,
            Subscription.merchant_id == uuid.UUID(current_user["id"])
        )
    ).first()
    
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")
    
    if subscription.status != DBSubscriptionStatus.TRIALING:
        raise HTTPException(
            status_code=400,
            detail="Can only extend trial for subscriptions in trialing status"
        )
    
    if not subscription.trial_end:
        raise HTTPException(status_code=400, detail="Subscription has no trial end date")
    
    new_trial_end = subscription.trial_end + timedelta(days=extra_days)
    subscription.trial_end = new_trial_end
    subscription.current_period_end = new_trial_end
    subscription.next_payment_at = new_trial_end
    subscription.updated_at = datetime.utcnow()
    
    db.commit()
    
    return {
        "message": f"Trial extended by {extra_days} days",
        "subscription_id": subscription_id,
        "new_trial_end": new_trial_end.isoformat(),
        "trial_days_remaining": (new_trial_end - datetime.utcnow()).days
    }


@router.post("/{subscription_id}/end-trial")
async def end_trial_early(
    subscription_id: str,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant)
):
    """
    End a trial early and convert to paid subscription immediately.
    
    The subscription moves to active status and the first billing cycle begins.
    """
    subscription = db.query(Subscription).filter(
        and_(
            Subscription.id == subscription_id,
            Subscription.merchant_id == uuid.UUID(current_user["id"])
        )
    ).first()
    
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")
    
    if subscription.status != DBSubscriptionStatus.TRIALING:
        raise HTTPException(
            status_code=400,
            detail="Can only end trial for subscriptions in trialing status"
        )
    
    now = datetime.utcnow()
    plan = subscription.plan
    
    interval_value = plan.interval.value if hasattr(plan.interval, 'value') else plan.interval
    
    subscription.status = DBSubscriptionStatus.ACTIVE
    subscription.trial_converted_at = now
    subscription.current_period_start = now
    subscription.current_period_end = calculate_next_billing_date(now, interval_value, plan.interval_count)
    subscription.next_payment_at = now
    subscription.updated_at = now
    
    # Create first payment record
    first_payment = SubscriptionPayment(
        subscription_id=subscription.id,
        period_start=subscription.current_period_start,
        period_end=subscription.current_period_end,
        amount=plan.amount,
        fiat_currency=plan.fiat_currency,
        status=PaymentStatus.CREATED
    )
    db.add(first_payment)
    
    db.commit()
    
    return {
        "message": "Trial ended, subscription is now active",
        "subscription_id": subscription_id,
        "status": "active",
        "next_payment_at": subscription.next_payment_at.isoformat(),
        "amount": float(plan.amount)
    }


# ========================
# PAYMENT METHOD
# ========================

@router.put("/{subscription_id}/payment-method")
async def update_payment_method(
    subscription_id: str,
    wallet_address: str = Query(..., min_length=10, description="Customer's wallet address"),
    chain: str = Query(..., description="Blockchain network"),
    token: str = Query(default="USDC", description="Token symbol"),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant)
):
    """
    Update the customer's payment method for a subscription.
    
    Sets the wallet address, chain, and token that will be used
    for collecting recurring payments.
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
        raise HTTPException(status_code=400, detail="Cannot update payment method for cancelled subscription")
    
    subscription.customer_wallet_address = wallet_address
    subscription.customer_chain = chain.lower()
    subscription.customer_token = token.upper()
    subscription.updated_at = datetime.utcnow()
    
    db.commit()
    
    return {
        "message": "Payment method updated",
        "subscription_id": subscription_id,
        "wallet_address": wallet_address,
        "chain": chain.lower(),
        "token": token.upper()
    }


# ========================
# SUBSCRIPTION RENEWAL (collect payment for current period)
# ========================

@router.post("/{subscription_id}/collect-payment")
async def collect_subscription_payment(
    subscription_id: str,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant)
):
    """
    Manually trigger payment collection for a subscription's current period.
    
    Creates a payment session for the subscription amount. The customer
    can then pay via the checkout URL. For subscriptions with a saved
    payment method, this generates a payment session tied to their wallet.
    """
    subscription = db.query(Subscription).filter(
        and_(
            Subscription.id == subscription_id,
            Subscription.merchant_id == uuid.UUID(current_user["id"])
        )
    ).first()
    
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")
    
    if subscription.status not in [DBSubscriptionStatus.ACTIVE, DBSubscriptionStatus.PAST_DUE]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot collect payment for subscription with status: {subscription.status.value}"
        )
    
    plan = subscription.plan
    
    # Check if there's already a pending payment for this period
    existing_payment = db.query(SubscriptionPayment).filter(
        and_(
            SubscriptionPayment.subscription_id == subscription_id,
            SubscriptionPayment.period_start == subscription.current_period_start,
            SubscriptionPayment.status.in_([PaymentStatus.CREATED, PaymentStatus.PENDING])
        )
    ).first()
    
    if existing_payment and existing_payment.payment_session_id:
        # Return existing payment session
        return {
            "message": "Payment already pending for this period",
            "subscription_id": subscription_id,
            "payment_id": str(existing_payment.id),
            "payment_session_id": existing_payment.payment_session_id,
            "amount": float(plan.amount),
            "currency": plan.fiat_currency,
        }
    
    # Create a payment session for this subscription period
    from app.models.models import PaymentSession as PSModel
    
    session_id = f"pay_{secrets.token_urlsafe(12)}"
    base_url = str(request.base_url).rstrip("/") if request else ""
    
    payment_session = PSModel(
        id=session_id,
        merchant_id=subscription.merchant_id,
        amount_fiat=plan.amount,
        fiat_currency=plan.fiat_currency,
        amount_token=str(plan.amount),
        amount_usdc=str(plan.amount),
        token=subscription.customer_token or (plan.accepted_tokens[0] if plan.accepted_tokens else "USDC"),
        chain=subscription.customer_chain or (plan.accepted_chains[0] if plan.accepted_chains else "stellar"),
        accepted_tokens=plan.accepted_tokens,
        accepted_chains=plan.accepted_chains,
        status=PaymentStatus.CREATED,
        success_url=f"{base_url}/subscriptions/{subscription_id}",
        cancel_url=f"{base_url}/subscriptions/{subscription_id}",
        order_id=f"sub_{subscription_id}_period_{subscription.current_period_start.strftime('%Y%m%d')}",
        session_metadata={
            "subscription_id": subscription_id,
            "period_start": subscription.current_period_start.isoformat(),
            "period_end": subscription.current_period_end.isoformat(),
            "type": "subscription_payment"
        },
        expires_at=datetime.utcnow() + timedelta(hours=24),
        collect_payer_data=False,
        payer_email=subscription.customer_email,
        payer_name=subscription.customer_name,
    )
    
    # Set merchant wallet if customer has preferred chain
    if subscription.customer_chain:
        from app.models.models import MerchantWallet
        wallet = db.query(MerchantWallet).filter(
            and_(
                MerchantWallet.merchant_id == subscription.merchant_id,
                MerchantWallet.chain == subscription.customer_chain,
                MerchantWallet.is_active == True
            )
        ).first()
        if wallet:
            payment_session.merchant_wallet = wallet.wallet_address
    
    db.add(payment_session)
    
    # Create or update subscription payment record
    if existing_payment:
        existing_payment.payment_session_id = session_id
    else:
        sub_payment = SubscriptionPayment(
            subscription_id=subscription_id,
            payment_session_id=session_id,
            period_start=subscription.current_period_start,
            period_end=subscription.current_period_end,
            amount=plan.amount,
            fiat_currency=plan.fiat_currency,
            status=PaymentStatus.CREATED
        )
        db.add(sub_payment)
    
    db.commit()
    
    checkout_url = f"{base_url}/checkout/{session_id}"
    
    return {
        "message": "Payment session created for subscription",
        "subscription_id": subscription_id,
        "payment_session_id": session_id,
        "checkout_url": checkout_url,
        "amount": float(plan.amount),
        "currency": plan.fiat_currency,
        "expires_at": payment_session.expires_at.isoformat()
    }


@router.post("/{subscription_id}/renew")
async def renew_subscription(
    subscription_id: str,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant)
):
    """
    Manually advance a subscription to the next billing period.
    
    Use this after a payment has been confirmed to move the subscription
    to the next cycle. Automatically done by the billing service in production.
    """
    subscription = db.query(Subscription).filter(
        and_(
            Subscription.id == subscription_id,
            Subscription.merchant_id == uuid.UUID(current_user["id"])
        )
    ).first()
    
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")
    
    if subscription.status not in [DBSubscriptionStatus.ACTIVE, DBSubscriptionStatus.PAST_DUE]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot renew subscription with status: {subscription.status.value}"
        )
    
    # Check if max billing cycles reached
    plan = subscription.plan
    if plan.max_billing_cycles and subscription.total_payments_collected >= plan.max_billing_cycles:
        subscription.status = DBSubscriptionStatus.CANCELLED
        subscription.cancelled_at = datetime.utcnow()
        subscription.cancel_reason = "Max billing cycles reached"
        db.commit()
        return {
            "message": "Subscription completed — max billing cycles reached",
            "subscription_id": subscription_id,
            "total_payments_collected": subscription.total_payments_collected
        }
    
    # Check for pending cancellation
    if subscription.cancel_at and subscription.cancel_at <= datetime.utcnow():
        subscription.status = DBSubscriptionStatus.CANCELLED
        db.commit()
        return {
            "message": "Subscription cancelled at period end",
            "subscription_id": subscription_id
        }
    
    now = datetime.utcnow()
    interval_value = plan.interval.value if hasattr(plan.interval, 'value') else plan.interval
    
    subscription.current_period_start = now
    subscription.current_period_end = calculate_next_billing_date(now, interval_value, plan.interval_count)
    subscription.next_payment_at = subscription.current_period_end
    subscription.last_payment_at = now
    subscription.total_payments_collected = (subscription.total_payments_collected or 0) + 1
    subscription.total_revenue = Decimal(str(subscription.total_revenue or 0)) + plan.amount
    subscription.failed_payment_count = 0
    subscription.status = DBSubscriptionStatus.ACTIVE
    subscription.updated_at = now
    
    db.commit()
    db.refresh(subscription)
    
    return {
        "message": "Subscription renewed",
        "subscription_id": subscription_id,
        "current_period_start": subscription.current_period_start.isoformat(),
        "current_period_end": subscription.current_period_end.isoformat(),
        "total_payments": subscription.total_payments_collected
    }


# ========================
# HELPERS
# ========================

def build_plan_response(plan: SubscriptionPlan, db: Session, request: Request = None) -> SubscriptionPlanResponse:
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
            trial_type=getattr(plan, 'trial_type', 'free') or 'free',
            trial_price=getattr(plan, 'trial_price', None),
            setup_fee=getattr(plan, 'setup_fee', Decimal("0")) or Decimal("0"),
            accepted_tokens=plan.accepted_tokens or [],
            accepted_chains=plan.accepted_chains or [],
            is_active=plan.is_active,
            max_billing_cycles=getattr(plan, 'max_billing_cycles', None),
            features=plan.features,
            subscriber_count=subscriber_count or 0,
            subscribe_url=_get_subscribe_url(request, plan.id) if request else None,
            created_at=plan.created_at
        )
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error building plan response for plan {plan.id}: {e}", exc_info=True)
        return SubscriptionPlanResponse(
            id=plan.id,
            name=plan.name,
            description=plan.description,
            amount=plan.amount,
            fiat_currency=plan.fiat_currency,
            interval=plan.interval.value if hasattr(plan.interval, 'value') else plan.interval,
            interval_count=plan.interval_count,
            trial_days=plan.trial_days,
            trial_type=getattr(plan, 'trial_type', 'free') or 'free',
            trial_price=getattr(plan, 'trial_price', None),
            setup_fee=getattr(plan, 'setup_fee', Decimal("0")) or Decimal("0"),
            accepted_tokens=plan.accepted_tokens or [],
            accepted_chains=plan.accepted_chains or [],
            is_active=plan.is_active,
            max_billing_cycles=getattr(plan, 'max_billing_cycles', None),
            features=plan.features,
            subscriber_count=0,
            subscribe_url=_get_subscribe_url(request, plan.id) if request else None,
            created_at=plan.created_at
        )


def build_subscription_response(subscription: Subscription, request: Request) -> RecurringSubscriptionResponse:
    """Build RecurringSubscriptionResponse from model"""
    # Get plan details
    plan = subscription.plan
    plan_name = plan.name if plan else "Unknown"
    
    # Generate payment URL if needed
    next_payment_url = None
    next_payment_amount = None
    if subscription.status in [DBSubscriptionStatus.ACTIVE, DBSubscriptionStatus.PAST_DUE]:
        base_url = str(request.base_url).rstrip("/")
        next_payment_url = f"{base_url}/subscriptions/{subscription.id}/collect-payment"
        next_payment_amount = plan.amount if plan else None
    
    # Trial info
    is_in_trial = subscription.status == DBSubscriptionStatus.TRIALING
    trial_days_remaining = None
    trial_type = None
    if is_in_trial and subscription.trial_end:
        remaining = (subscription.trial_end - datetime.utcnow()).days
        trial_days_remaining = max(remaining, 0)
        trial_type = getattr(plan, 'trial_type', 'free') if plan else 'free'
    
    has_payment_method = bool(subscription.customer_wallet_address)
    
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
        trial_type=trial_type,
        is_in_trial=is_in_trial,
        trial_days_remaining=trial_days_remaining,
        total_payments_collected=subscription.total_payments_collected or 0,
        total_revenue=subscription.total_revenue,
        next_payment_at=subscription.next_payment_at,
        next_payment_url=next_payment_url,
        next_payment_amount=next_payment_amount,
        customer_wallet_address=subscription.customer_wallet_address,
        customer_chain=subscription.customer_chain,
        customer_token=subscription.customer_token,
        has_payment_method=has_payment_method,
        cancel_at=subscription.cancel_at,
        cancelled_at=subscription.cancelled_at,
        created_at=subscription.created_at
    )
