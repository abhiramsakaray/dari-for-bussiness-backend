"""
Promo Code / Coupon Management Routes

Merchant APIs:
  POST   /api/business/promo/create       – Create coupon
  GET    /api/business/promo/list          – List coupons
  PUT    /api/business/promo/{coupon_id}   – Edit coupon
  DELETE /api/business/promo/{coupon_id}   – Delete coupon (soft)
  PATCH  /api/business/promo/{coupon_id}/status – Enable/disable
  GET    /api/business/promo/{coupon_id}/analytics – Usage analytics

Customer / Checkout API:
  POST   /api/payment/apply-coupon         – Validate & apply coupon
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from datetime import datetime
from decimal import Decimal
from typing import Optional
import uuid
import logging
import time

from app.core.database import get_db
from app.core.security import require_merchant
from app.models.models import Merchant, PromoCode, PromoCodeUsage, PaymentSession, PaymentStatus
from app.schemas.schemas import (
    PromoCodeCreate,
    PromoCodeUpdate,
    PromoCodeStatusUpdate,
    PromoCodeResponse,
    PromoCodeList,
    ApplyCouponRequest,
    ApplyCouponResponse,
    PromoCodeAnalyticsResponse,
)
from app.services.promo_service import (
    validate_and_calculate_discount,
    record_coupon_usage,
    get_promo_analytics,
)

logger = logging.getLogger(__name__)

# ════════════════════════════════════════
#  Merchant-facing promo management
# ════════════════════════════════════════

merchant_promo_router = APIRouter(
    prefix="/api/business/promo",
    tags=["Promo Codes"],
)


def _promo_to_response(promo: PromoCode) -> PromoCodeResponse:
    return PromoCodeResponse(
        id=str(promo.id),
        code=promo.code,
        type=promo.type,
        discount_value=promo.discount_value,
        max_discount_amount=promo.max_discount_amount,
        min_order_amount=promo.min_order_amount or Decimal("0"),
        usage_limit_total=promo.usage_limit_total,
        usage_limit_per_user=promo.usage_limit_per_user,
        used_count=promo.used_count or 0,
        start_date=promo.start_date,
        expiry_date=promo.expiry_date,
        status=promo.status,
        created_at=promo.created_at,
        updated_at=promo.updated_at,
    )


# ── Create ──
@merchant_promo_router.post("/create", response_model=PromoCodeResponse)
async def create_promo_code(
    data: PromoCodeCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant),
):
    merchant_id = uuid.UUID(current_user["id"])

    # Ensure code uniqueness within this merchant
    existing = (
        db.query(PromoCode)
        .filter(
            PromoCode.merchant_id == merchant_id,
            PromoCode.code == data.code,
            PromoCode.status != "deleted",
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Coupon code already exists")

    if data.expiry_date <= data.start_date:
        raise HTTPException(status_code=400, detail="Expiry date must be after start date")

    promo = PromoCode(
        merchant_id=merchant_id,
        code=data.code,
        type=data.type.value,
        discount_value=data.discount_value,
        max_discount_amount=data.max_discount_amount,
        min_order_amount=data.min_order_amount,
        usage_limit_total=data.usage_limit_total,
        usage_limit_per_user=data.usage_limit_per_user,
        start_date=data.start_date,
        expiry_date=data.expiry_date,
        status="active",
    )
    db.add(promo)
    db.commit()
    db.refresh(promo)

    logger.info(f"Promo code created: {promo.code} for merchant {merchant_id}")
    return _promo_to_response(promo)


# ── List ──
@merchant_promo_router.get("/list", response_model=PromoCodeList)
async def list_promo_codes(
    status: Optional[str] = Query(None, description="Filter by status: active, inactive"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant),
):
    merchant_id = uuid.UUID(current_user["id"])

    query = db.query(PromoCode).filter(
        PromoCode.merchant_id == merchant_id,
        PromoCode.status != "deleted",
    )
    if status:
        query = query.filter(PromoCode.status == status)

    total = query.count()
    promos = (
        query.order_by(PromoCode.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return PromoCodeList(
        promo_codes=[_promo_to_response(p) for p in promos],
        total=total,
    )


# ── Edit ──
@merchant_promo_router.put("/{coupon_id}", response_model=PromoCodeResponse)
async def update_promo_code(
    coupon_id: str,
    data: PromoCodeUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant),
):
    merchant_id = uuid.UUID(current_user["id"])
    promo = _get_merchant_promo(db, merchant_id, coupon_id)

    if data.discount_value is not None:
        promo.discount_value = data.discount_value
    if data.max_discount_amount is not None:
        promo.max_discount_amount = data.max_discount_amount
    if data.min_order_amount is not None:
        promo.min_order_amount = data.min_order_amount
    if data.usage_limit_total is not None:
        promo.usage_limit_total = data.usage_limit_total
    if data.usage_limit_per_user is not None:
        promo.usage_limit_per_user = data.usage_limit_per_user
    if data.expiry_date is not None:
        promo.expiry_date = data.expiry_date
    if data.status is not None:
        promo.status = data.status.value

    promo.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(promo)

    return _promo_to_response(promo)


# ── Delete (soft) ──
@merchant_promo_router.delete("/{coupon_id}")
async def delete_promo_code(
    coupon_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant),
):
    merchant_id = uuid.UUID(current_user["id"])
    promo = _get_merchant_promo(db, merchant_id, coupon_id)

    promo.status = "deleted"
    promo.updated_at = datetime.utcnow()
    db.commit()

    return {"message": "Coupon deleted successfully"}


# ── Enable / Disable ──
@merchant_promo_router.patch("/{coupon_id}/status", response_model=PromoCodeResponse)
async def toggle_promo_status(
    coupon_id: str,
    data: PromoCodeStatusUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant),
):
    merchant_id = uuid.UUID(current_user["id"])
    promo = _get_merchant_promo(db, merchant_id, coupon_id)

    promo.status = data.status.value
    promo.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(promo)

    return _promo_to_response(promo)


# ── Analytics ──
@merchant_promo_router.get("/{coupon_id}/analytics", response_model=PromoCodeAnalyticsResponse)
async def promo_analytics(
    coupon_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant),
):
    merchant_id = uuid.UUID(current_user["id"])
    promo = _get_merchant_promo(db, merchant_id, coupon_id)

    analytics = get_promo_analytics(db, promo)
    return PromoCodeAnalyticsResponse(**analytics)


# ── Helper ──
def _get_merchant_promo(db: Session, merchant_id, coupon_id: str) -> PromoCode:
    try:
        cid = uuid.UUID(coupon_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid coupon ID")

    promo = (
        db.query(PromoCode)
        .filter(
            PromoCode.id == cid,
            PromoCode.merchant_id == merchant_id,
            PromoCode.status != "deleted",
        )
        .first()
    )
    if not promo:
        raise HTTPException(status_code=404, detail="Coupon not found")
    return promo


# ════════════════════════════════════════
#  Checkout / Payment coupon application
# ════════════════════════════════════════

payment_coupon_router = APIRouter(
    prefix="/api/payment",
    tags=["Payment Coupons"],
)

# Simple in-memory rate limiter for coupon endpoint
_coupon_rate_limit: dict[str, list[float]] = {}
_RATE_LIMIT_WINDOW = 60  # seconds
_RATE_LIMIT_MAX = 10  # max attempts per window


def _check_rate_limit(key: str) -> None:
    """Raise 429 if the key exceeds the rate limit."""
    now = time.time()
    timestamps = _coupon_rate_limit.get(key, [])
    # Prune old entries
    timestamps = [t for t in timestamps if now - t < _RATE_LIMIT_WINDOW]
    if len(timestamps) >= _RATE_LIMIT_MAX:
        raise HTTPException(status_code=429, detail="Too many coupon attempts. Please try again later.")
    timestamps.append(now)
    _coupon_rate_limit[key] = timestamps


@payment_coupon_router.post("/apply-coupon", response_model=ApplyCouponResponse)
async def apply_coupon(
    data: ApplyCouponRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    # Rate-limit by client IP + merchant to prevent brute-force
    client_ip = request.client.host if request.client else "unknown"
    rate_key = f"{client_ip}:{data.merchant_id}"
    _check_rate_limit(rate_key)

    result = validate_and_calculate_discount(
        db=db,
        merchant_id=data.merchant_id,
        coupon_code=data.coupon_code,
        order_amount=data.order_amount,
        customer_id=data.customer_id,
    )

    # If coupon is valid, store coupon info on the payment session
    if result["coupon_valid"] and data.payment_link_id:
        session = db.query(PaymentSession).filter(
            PaymentSession.id == data.payment_link_id,
            PaymentSession.merchant_id == data.merchant_id,
        ).first()
        if session and session.status != PaymentStatus.PAID:
            session.coupon_code = result["coupon_code"]
            session.discount_amount = result["discount_amount"]
            db.commit()

    return ApplyCouponResponse(
        coupon_valid=result["coupon_valid"],
        discount_amount=result["discount_amount"],
        final_amount=result["final_amount"],
        coupon_code=result["coupon_code"],
        discount_type=result["discount_type"],
        message=result["message"],
    )


@payment_coupon_router.post("/complete-coupon-payment")
async def complete_coupon_payment(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Auto-complete a payment session when a 100% discount coupon
    makes the final amount zero. No blockchain payment needed.
    """
    body = await request.json()
    session_id = body.get("session_id", "").strip()
    coupon_code = body.get("coupon_code", "").strip().upper()

    if not session_id or not coupon_code:
        raise HTTPException(status_code=400, detail="session_id and coupon_code are required")

    # Rate-limit
    client_ip = request.client.host if request.client else "unknown"
    rate_key = f"{client_ip}:complete:{session_id}"
    _check_rate_limit(rate_key)

    session = db.query(PaymentSession).filter(PaymentSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Payment session not found")
    if session.status == PaymentStatus.PAID:
        return {"status": "already_paid", "message": "Payment already completed"}
    if session.status == PaymentStatus.EXPIRED:
        raise HTTPException(status_code=400, detail="Payment session expired")

    # Re-validate the coupon server-side (never trust the client)
    order_amount = session.amount_fiat
    result = validate_and_calculate_discount(
        db=db,
        merchant_id=str(session.merchant_id),
        coupon_code=coupon_code,
        order_amount=order_amount,
    )

    if not result["coupon_valid"]:
        raise HTTPException(status_code=400, detail=result["message"])

    final_amount = result["final_amount"]
    if final_amount > 0:
        raise HTTPException(
            status_code=400,
            detail="Coupon does not cover full amount. Blockchain payment still required.",
        )

    # Mark session as paid (100% coupon)
    session.status = PaymentStatus.PAID
    session.paid_at = datetime.utcnow()
    session.coupon_code = result["coupon_code"]
    session.discount_amount = result["discount_amount"]
    session.tx_hash = f"coupon:{result['coupon_code']}"
    db.commit()

    # Update merchant subscription volume (full original amount counts)
    try:
        from app.services.payment_utils import update_merchant_volume
        update_merchant_volume(db, session.merchant_id, order_amount)
    except Exception as ve:
        logger.error(f"Error updating volume for coupon payment {session_id}: {ve}")

    # Record coupon usage
    record_coupon_usage(
        db=db,
        promo_code_id=result["promo_code_id"],
        merchant_id=str(session.merchant_id),
        customer_id=session.payer_email or "anonymous",
        payment_id=session.id,
        discount_applied=result["discount_amount"],
    )

    logger.info(f"Payment {session_id} auto-completed via 100% coupon {coupon_code}")

    return {
        "status": "paid",
        "message": "Payment completed with coupon (100% discount)",
        "session_id": session_id,
        "coupon_code": result["coupon_code"],
    }
