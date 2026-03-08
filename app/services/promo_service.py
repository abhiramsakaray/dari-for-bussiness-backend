"""
Promo Code / Coupon Service
Handles coupon validation, discount calculation, and usage tracking.
"""
from datetime import datetime
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.models import PromoCode, PromoCodeUsage


def validate_and_calculate_discount(
    db: Session,
    merchant_id: str,
    coupon_code: str,
    order_amount: Decimal,
    customer_id: str | None = None,
) -> dict:
    """
    Validate a coupon code and calculate the discount.
    Returns dict with coupon_valid, discount_amount, final_amount, message, etc.
    """
    coupon_code = coupon_code.strip().upper()

    # 1. Coupon exists for this merchant
    promo = (
        db.query(PromoCode)
        .filter(
            PromoCode.merchant_id == merchant_id,
            PromoCode.code == coupon_code,
            PromoCode.status != "deleted",
        )
        .first()
    )

    if not promo:
        return _fail(order_amount, "Invalid coupon code")

    # 2. Coupon is active
    if promo.status != "active":
        return _fail(order_amount, "Coupon is not active")

    # 3. Date validity
    now = datetime.utcnow()
    if now < promo.start_date:
        return _fail(order_amount, "Coupon is not yet valid")
    if now > promo.expiry_date:
        return _fail(order_amount, "Coupon expired")

    # 4. Minimum order amount
    if order_amount < (promo.min_order_amount or 0):
        return _fail(
            order_amount,
            f"Minimum order amount is {promo.min_order_amount}",
        )

    # 5. Total usage limit
    if promo.usage_limit_total is not None and promo.used_count >= promo.usage_limit_total:
        return _fail(order_amount, "Coupon usage limit reached")

    # 6. Per-user usage limit
    if customer_id and promo.usage_limit_per_user is not None:
        user_usage = (
            db.query(func.count(PromoCodeUsage.id))
            .filter(
                PromoCodeUsage.promo_code_id == promo.id,
                PromoCodeUsage.customer_id == customer_id,
            )
            .scalar()
        )
        if user_usage >= promo.usage_limit_per_user:
            return _fail(order_amount, "Coupon already used")

    # Calculate discount
    discount = _calculate_discount(promo, order_amount)
    final_amount = order_amount - discount

    return {
        "coupon_valid": True,
        "discount_amount": discount,
        "final_amount": max(final_amount, Decimal("0")),
        "coupon_code": promo.code,
        "discount_type": promo.type,
        "promo_code_id": str(promo.id),
        "message": "Coupon applied successfully",
    }


def record_coupon_usage(
    db: Session,
    promo_code_id: str,
    merchant_id: str,
    customer_id: str,
    payment_id: str | None,
    discount_applied: Decimal,
) -> None:
    """Record coupon usage after successful payment and increment used_count."""
    usage = PromoCodeUsage(
        promo_code_id=promo_code_id,
        merchant_id=merchant_id,
        customer_id=customer_id,
        payment_id=payment_id,
        discount_applied=discount_applied,
    )
    db.add(usage)

    promo = db.query(PromoCode).filter(PromoCode.id == promo_code_id).first()
    if promo:
        promo.used_count = (promo.used_count or 0) + 1

    db.commit()


def get_promo_analytics(db: Session, promo: PromoCode) -> dict:
    """Compute analytics for a single promo code."""
    total_discount = (
        db.query(func.coalesce(func.sum(PromoCodeUsage.discount_applied), 0))
        .filter(PromoCodeUsage.promo_code_id == promo.id)
        .scalar()
    )

    # Revenue generated = sum of payments where this coupon was used
    from app.models.models import PaymentSession, PaymentStatus

    payment_ids = (
        db.query(PromoCodeUsage.payment_id)
        .filter(
            PromoCodeUsage.promo_code_id == promo.id,
            PromoCodeUsage.payment_id.isnot(None),
        )
        .all()
    )
    payment_id_list = [p[0] for p in payment_ids]

    revenue = Decimal("0")
    total_sessions = 0
    if payment_id_list:
        result = (
            db.query(
                func.coalesce(func.sum(PaymentSession.amount_fiat), 0),
                func.count(PaymentSession.id),
            )
            .filter(
                PaymentSession.id.in_(payment_id_list),
                PaymentSession.status == PaymentStatus.PAID,
            )
            .first()
        )
        revenue = result[0] or Decimal("0")
        total_sessions = result[1] or 0

    conversion_rate = None
    if promo.used_count and promo.used_count > 0 and total_sessions > 0:
        conversion_rate = round(Decimal(total_sessions) / Decimal(promo.used_count) * 100, 2)

    return {
        "promo_code_id": str(promo.id),
        "code": promo.code,
        "total_used": promo.used_count or 0,
        "total_discount_given": Decimal(str(total_discount)),
        "revenue_generated": revenue,
        "conversion_rate": conversion_rate,
    }


# ── helpers ──

def _calculate_discount(promo: PromoCode, order_amount: Decimal) -> Decimal:
    if promo.type == "percentage":
        discount = order_amount * (promo.discount_value / Decimal("100"))
        if promo.max_discount_amount is not None:
            discount = min(discount, promo.max_discount_amount)
    else:
        discount = promo.discount_value
    return min(discount, order_amount)


def _fail(order_amount: Decimal, message: str) -> dict:
    return {
        "coupon_valid": False,
        "discount_amount": Decimal("0"),
        "final_amount": order_amount,
        "coupon_code": None,
        "discount_type": None,
        "message": message,
    }
