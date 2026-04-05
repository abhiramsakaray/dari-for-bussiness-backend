"""
Merchant Analytics API Routes
Analytics and reporting for merchants — includes MRR/ARR, payment tracking,
subscription tracking, and cached query results.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, desc
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional
import uuid

from app.core.database import get_db
from app.core import require_merchant
from app.core.cache import cache, make_cache_key
from app.models.models import (
    Merchant, PaymentSession, Invoice, Subscription, SubscriptionPayment,
    SubscriptionPlan, PaymentEvent,
    PaymentStatus, AnalyticsSnapshot, InvoiceStatus as DBInvoiceStatus,
    SubscriptionStatus as DBSubscriptionStatus, SubscriptionInterval,
)
from app.schemas.schemas import (
    AnalyticsOverview, PaymentMetrics, VolumeByToken, VolumeByChain,
    AnalyticsTimeSeries, RevenueTimeSeries, AnalyticsPeriod,
    MRRARRResponse, MRRTrendPoint, MRRTrendResponse,
    PaymentTrackingResponse, SubscriptionTrackingResponse,
    LocalCurrencyAmount,
)
from app.services.price_service import PriceService
from app.services.currency_service import get_currency_for_country

router = APIRouter(prefix="/analytics", tags=["Analytics"])

_price_svc = PriceService()


def _resolve_currency_context(merchant: Optional[Merchant]) -> tuple[str, str]:
    """Resolve merchant currency and symbol with safe fallbacks."""
    if not merchant:
        return "USD", "$"

    currency = (getattr(merchant, "base_currency", None) or "USD").upper()
    symbol = getattr(merchant, "currency_symbol", None)
    if symbol:
        return currency, symbol

    country = getattr(merchant, "country", None)
    if country:
        c_code, c_symbol, _ = get_currency_for_country(country)
        if c_code == currency:
            return currency, c_symbol

    common_symbols = {
        "USD": "$", "EUR": "€", "GBP": "£", "INR": "₹", "JPY": "¥",
        "AUD": "A$", "CAD": "C$", "SGD": "S$", "AED": "د.إ", "KWD": "KD",
    }
    return currency, common_symbols.get(currency, currency)


async def _convert_amount(amount: Decimal, from_currency: Optional[str], to_currency: str) -> Decimal:
    """Convert fiat amount between currencies with graceful fallback."""
    src = (from_currency or "USD").upper()
    dst = (to_currency or "USD").upper()
    if src == dst:
        return Decimal(str(amount))

    try:
        rate = await _price_svc.get_fiat_rate(src, dst)
        return (Decimal(str(amount)) * rate).quantize(Decimal("0.01"))
    except Exception:
        return Decimal(str(amount))


@router.get("/overview", response_model=AnalyticsOverview)
async def get_analytics_overview(
    period: AnalyticsPeriod = AnalyticsPeriod.MONTH,
    current_user: dict = Depends(require_merchant),
    db: Session = Depends(get_db)
):
    """
    Get analytics overview for the merchant.
    
    Returns key metrics for the selected period:
    - Payment volume and counts
    - Conversion rates
    - Volume by token and chain
    - Invoice and subscription metrics
    - Comparison to previous period
    """
    merchant_id = uuid.UUID(current_user["id"])
    
    # Check cache
    ck = make_cache_key("overview", merchant_id, period.value)
    cached = cache.get(ck, region="analytics")
    if cached is not None:
        return cached
    
    # Get merchant for currency info
    merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    m_currency, m_symbol = _resolve_currency_context(merchant)
    
    now = datetime.utcnow()
    
    # Determine period boundaries
    if period == AnalyticsPeriod.DAY:
        period_start = now - timedelta(days=1)
        prev_period_start = period_start - timedelta(days=1)
    elif period == AnalyticsPeriod.WEEK:
        period_start = now - timedelta(weeks=1)
        prev_period_start = period_start - timedelta(weeks=1)
    elif period == AnalyticsPeriod.MONTH:
        period_start = now - timedelta(days=30)
        prev_period_start = period_start - timedelta(days=30)
    else:  # YEAR
        period_start = now - timedelta(days=365)
        prev_period_start = period_start - timedelta(days=365)
    
    # Get payment metrics for current period
    current_metrics = await get_payment_metrics(db, merchant_id, period_start, now, m_currency, m_symbol)
    
    # Get previous period for comparison
    prev_metrics = await get_payment_metrics(db, merchant_id, prev_period_start, period_start, m_currency, m_symbol)
    
    # Calculate changes
    payments_change = calculate_change(
        prev_metrics.total_payments, 
        current_metrics.total_payments
    )
    volume_change = calculate_change(
        float(prev_metrics.total_volume),
        float(current_metrics.total_volume)
    )
    
    # Get volume breakdowns
    volume_by_token = await get_volume_by_token(db, merchant_id, period_start, now, m_currency)
    volume_by_chain = await get_volume_by_chain(db, merchant_id, period_start, now, m_currency)
    
    # Get invoice metrics
    invoice_metrics = await get_invoice_metrics(db, merchant_id, period_start, now, m_currency)
    
    # Get subscription metrics
    subscription_metrics = await get_subscription_metrics(db, merchant_id, period_start, now, m_currency)
    
    result = AnalyticsOverview(
        period_start=period_start,
        period_end=now,
        period=period.value,
        payments=current_metrics,
        volume_by_token=volume_by_token,
        volume_by_chain=volume_by_chain,
        invoices_sent=invoice_metrics["sent"],
        invoices_paid=invoice_metrics["paid"],
        invoice_volume=invoice_metrics["volume"],
        invoice_volume_usd=invoice_metrics["volume"],
        active_subscriptions=subscription_metrics["active"],
        new_subscriptions=subscription_metrics["new"],
        churned_subscriptions=subscription_metrics["churned"],
        subscription_mrr=subscription_metrics["mrr"],
        payments_change_pct=payments_change,
        volume_change_pct=volume_change,
        currency=m_currency,
        currency_symbol=m_symbol,
    )
    cache.set(ck, result, region="analytics")
    return result


@router.get("/revenue")
async def get_revenue_timeseries(
    period: AnalyticsPeriod = AnalyticsPeriod.MONTH,
    current_user: dict = Depends(require_merchant),
    db: Session = Depends(get_db)
):
    """
    Get revenue time series data.
    
    Returns daily/weekly/monthly revenue data points for charting.
    """
    merchant_id = uuid.UUID(current_user["id"])
    merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    m_currency, m_symbol = _resolve_currency_context(merchant)
    
    now = datetime.utcnow()
    
    # Determine period and aggregation
    if period == AnalyticsPeriod.DAY:
        period_start = now - timedelta(days=1)
        interval = "hour"
    elif period == AnalyticsPeriod.WEEK:
        period_start = now - timedelta(weeks=1)
        interval = "day"
    elif period == AnalyticsPeriod.MONTH:
        period_start = now - timedelta(days=30)
        interval = "day"
    else:  # YEAR
        period_start = now - timedelta(days=365)
        interval = "week"
    
    # Query payments grouped by interval
    query = db.query(PaymentSession).filter(
        and_(
            PaymentSession.status == PaymentStatus.PAID,
            PaymentSession.paid_at >= period_start,
            PaymentSession.paid_at <= now
        )
    )
    
    if merchant_id is not None:
        query = query.filter(PaymentSession.merchant_id == merchant_id)
    
    payments = query.all()
    
    # Aggregate by interval
    data_points = await aggregate_revenue_by_interval(payments, interval, period_start, now, m_currency)
    
    return {
        "period": period.value,
        "interval": interval,
        "currency": m_currency,
        "currency_symbol": m_symbol,
        "period_start": period_start.isoformat(),
        "period_end": now.isoformat(),
        "data": data_points
    }


@router.get("/payments/summary")
async def get_payment_summary(
    days: int = Query(default=30, ge=1, le=365),
    current_user: dict = Depends(require_merchant),
    db: Session = Depends(get_db)
):
    """
    Get a summary of payment activity.
    
    Returns counts and amounts by status.
    """
    merchant_id = uuid.UUID(current_user["id"])
    
    period_start = datetime.utcnow() - timedelta(days=days)
    
    # Get counts by status
    query = db.query(
        PaymentSession.status,
        func.count(PaymentSession.id).label('count'),
        func.sum(PaymentSession.amount_fiat).label('total')
    ).filter(PaymentSession.created_at >= period_start)
    
    if merchant_id is not None:
        query = query.filter(PaymentSession.merchant_id == merchant_id)
    
    status_counts = query.group_by(PaymentSession.status).all()
    
    summary = {}
    for status, count, total in status_counts:
        status_name = status.value if hasattr(status, 'value') else status
        summary[status_name] = {
            "count": count,
            "total": float(total) if total else 0
        }
    
    return {
        "period_days": days,
        "by_status": summary
    }


@router.get("/top-customers")
async def get_top_customers(
    limit: int = Query(default=10, ge=1, le=50),
    days: int = Query(default=30, ge=1, le=365),
    current_user: dict = Depends(require_merchant),
    db: Session = Depends(get_db)
):
    """
    Get top customers by payment volume.
    """
    merchant_id = uuid.UUID(current_user["id"])
    
    period_start = datetime.utcnow() - timedelta(days=days)
    
    # This is a simplified version - would need customer tracking
    # For now, group by metadata if available
    return {
        "message": "Top customers feature requires customer tracking",
        "period_days": days
    }


@router.get("/conversion")
async def get_conversion_metrics(
    days: int = Query(default=30, ge=1, le=365),
    current_user: dict = Depends(require_merchant),
    db: Session = Depends(get_db)
):
    """
    Get checkout conversion metrics.
    
    Returns:
    - Sessions created vs completed
    - Average time to payment
    - Drop-off rates by step
    """
    merchant_id = uuid.UUID(current_user["id"])
    
    period_start = datetime.utcnow() - timedelta(days=days)
    
    # Count sessions by status
    query = db.query(func.count(PaymentSession.id)).filter(
        PaymentSession.created_at >= period_start
    )
    if merchant_id is not None:
        query = query.filter(PaymentSession.merchant_id == merchant_id)
    total_sessions = query.scalar()
    
    query = db.query(func.count(PaymentSession.id)).filter(
        and_(
            PaymentSession.status == PaymentStatus.PAID,
            PaymentSession.created_at >= period_start
        )
    )
    if merchant_id is not None:
        query = query.filter(PaymentSession.merchant_id == merchant_id)
    completed_sessions = query.scalar()
    
    query = db.query(func.count(PaymentSession.id)).filter(
        and_(
            PaymentSession.status == PaymentStatus.EXPIRED,
            PaymentSession.created_at >= period_start
        )
    )
    if merchant_id is not None:
        query = query.filter(PaymentSession.merchant_id == merchant_id)
    expired_sessions = query.scalar()
    
    # Calculate conversion rate
    conversion_rate = 0
    if total_sessions > 0:
        conversion_rate = (completed_sessions / total_sessions) * 100
    
    # Calculate average time to payment
    query = db.query(PaymentSession).filter(
        and_(
            PaymentSession.status == PaymentStatus.PAID,
            PaymentSession.created_at >= period_start,
            PaymentSession.paid_at.isnot(None)
        )
    )
    if merchant_id is not None:
        query = query.filter(PaymentSession.merchant_id == merchant_id)
    completed = query.all()
    
    avg_time_seconds = 0
    if completed:
        times = [(p.paid_at - p.created_at).total_seconds() for p in completed]
        avg_time_seconds = sum(times) / len(times)
    
    return {
        "period_days": days,
        "total_sessions": total_sessions,
        "completed_sessions": completed_sessions,
        "expired_sessions": expired_sessions,
        "conversion_rate": round(conversion_rate, 2),
        "avg_time_to_payment_seconds": round(avg_time_seconds)
    }


@router.get("/chains")
async def get_chain_analytics(
    days: int = Query(default=30, ge=1, le=365),
    current_user: dict = Depends(require_merchant),
    db: Session = Depends(get_db)
):
    """
    Get analytics by blockchain network.
    """
    merchant_id = uuid.UUID(current_user["id"])
    
    period_start = datetime.utcnow() - timedelta(days=days)
    
    # Group by chain
    query = db.query(
        PaymentSession.chain,
        func.count(PaymentSession.id).label('count'),
        func.sum(PaymentSession.amount_fiat).label('volume')
    ).filter(
        and_(
            PaymentSession.status == PaymentStatus.PAID,
            PaymentSession.created_at >= period_start,
            PaymentSession.chain.isnot(None)
        )
    )
    
    if merchant_id is not None:
        query = query.filter(PaymentSession.merchant_id == merchant_id)
    
    chain_data = query.group_by(PaymentSession.chain).all()
    
    total_volume = sum(float(d.volume or 0) for d in chain_data)
    
    return {
        "period_days": days,
        "chains": [
            {
                "chain": d.chain,
                "payment_count": d.count,
                "volume": float(d.volume or 0),
                "percentage": round((float(d.volume or 0) / total_volume * 100), 2) if total_volume > 0 else 0
            }
            for d in chain_data
        ]
    }


# ========================
# HELPER FUNCTIONS
# ========================

async def get_payment_metrics(
    db: Session, 
    merchant_id: Optional[uuid.UUID], 
    start: datetime, 
    end: datetime,
    currency: str = "USD",
    currency_symbol: str = "$",
) -> PaymentMetrics:
    """Calculate payment metrics for a period"""
    
    query = db.query(func.count(PaymentSession.id)).filter(
        and_(
            PaymentSession.created_at >= start,
            PaymentSession.created_at <= end
        )
    )
    if merchant_id is not None:
        query = query.filter(PaymentSession.merchant_id == merchant_id)
    total = query.scalar() or 0
    
    query = db.query(func.count(PaymentSession.id)).filter(
        and_(
            PaymentSession.status == PaymentStatus.PAID,
            PaymentSession.created_at >= start,
            PaymentSession.created_at <= end
        )
    )
    if merchant_id is not None:
        query = query.filter(PaymentSession.merchant_id == merchant_id)
    successful = query.scalar() or 0
    
    query = db.query(func.count(PaymentSession.id)).filter(
        and_(
            PaymentSession.status.in_([PaymentStatus.EXPIRED, PaymentStatus.FAILED]),
            PaymentSession.created_at >= start,
            PaymentSession.created_at <= end
        )
    )
    if merchant_id is not None:
        query = query.filter(PaymentSession.merchant_id == merchant_id)
    failed = query.scalar() or 0
    
    query = db.query(PaymentSession).filter(
        and_(
            PaymentSession.status == PaymentStatus.PAID,
            PaymentSession.created_at >= start,
            PaymentSession.created_at <= end
        )
    )
    if merchant_id is not None:
        query = query.filter(PaymentSession.merchant_id == merchant_id)

    paid_sessions = query.all()
    volume = Decimal("0")
    for session in paid_sessions:
        amount = Decimal(str(session.amount_fiat or 0))
        volume += await _convert_amount(amount, session.fiat_currency, currency)

    volume = volume.quantize(Decimal("0.01"))
    
    # Calculate average
    avg_payment = Decimal("0")
    if successful > 0:
        avg_payment = volume / successful
    
    # Conversion rate
    conversion = Decimal("0")
    if total > 0:
        conversion = Decimal(successful) / Decimal(total) * 100
    
    return PaymentMetrics(
        total_payments=total,
        successful_payments=successful,
        failed_payments=failed,
        total_volume=volume,
        total_volume_usd=volume,
        avg_payment=avg_payment,
        avg_payment_usd=avg_payment,
        conversion_rate=conversion,
        currency=currency,
        currency_symbol=currency_symbol,
    )


async def get_volume_by_token(
    db: Session,
    merchant_id: Optional[uuid.UUID],
    start: datetime,
    end: datetime,
    target_currency: str,
) -> list[VolumeByToken]:
    """Get volume breakdown by token"""
    query = db.query(PaymentSession).filter(
        and_(
            PaymentSession.status == PaymentStatus.PAID,
            PaymentSession.created_at >= start,
            PaymentSession.created_at <= end,
            PaymentSession.token.isnot(None)
        )
    )
    
    if merchant_id is not None:
        query = query.filter(PaymentSession.merchant_id == merchant_id)
    
    data = query.all()

    grouped: dict[str, dict[str, Decimal | int]] = {}
    for row in data:
        token = row.token
        if token not in grouped:
            grouped[token] = {"volume": Decimal("0"), "count": 0}
        amount = Decimal(str(row.amount_fiat or 0))
        converted = await _convert_amount(amount, row.fiat_currency, target_currency)
        grouped[token]["volume"] = Decimal(str(grouped[token]["volume"])) + converted
        grouped[token]["count"] = int(grouped[token]["count"]) + 1
    
    return [
        VolumeByToken(
            token=token,
            volume=Decimal(str(values["volume"])).quantize(Decimal("0.01")),
            volume_usd=Decimal(str(values["volume"])).quantize(Decimal("0.01")),
            payment_count=int(values["count"]),
        )
        for token, values in grouped.items()
    ]


async def get_volume_by_chain(
    db: Session,
    merchant_id: Optional[uuid.UUID],
    start: datetime,
    end: datetime,
    target_currency: str,
) -> list[VolumeByChain]:
    """Get volume breakdown by chain"""
    query = db.query(PaymentSession).filter(
        and_(
            PaymentSession.status == PaymentStatus.PAID,
            PaymentSession.created_at >= start,
            PaymentSession.created_at <= end,
            PaymentSession.chain.isnot(None)
        )
    )
    
    if merchant_id is not None:
        query = query.filter(PaymentSession.merchant_id == merchant_id)
    
    data = query.all()

    grouped: dict[str, dict[str, Decimal | int]] = {}
    for row in data:
        chain = row.chain
        if chain not in grouped:
            grouped[chain] = {"volume": Decimal("0"), "count": 0}
        amount = Decimal(str(row.amount_fiat or 0))
        converted = await _convert_amount(amount, row.fiat_currency, target_currency)
        grouped[chain]["volume"] = Decimal(str(grouped[chain]["volume"])) + converted
        grouped[chain]["count"] = int(grouped[chain]["count"]) + 1
    
    return [
        VolumeByChain(
            chain=chain,
            volume=Decimal(str(values["volume"])).quantize(Decimal("0.01")),
            volume_usd=Decimal(str(values["volume"])).quantize(Decimal("0.01")),
            payment_count=int(values["count"]),
        )
        for chain, values in grouped.items()
    ]


async def get_invoice_metrics(
    db: Session,
    merchant_id: Optional[uuid.UUID],
    start: datetime,
    end: datetime,
    target_currency: str,
) -> dict:
    """Get invoice metrics for a period"""
    query = db.query(func.count(Invoice.id)).filter(
        and_(
            Invoice.sent_at >= start,
            Invoice.sent_at <= end
        )
    )
    if merchant_id is not None:
        query = query.filter(Invoice.merchant_id == merchant_id)
    sent = query.scalar() or 0
    
    query = db.query(func.count(Invoice.id)).filter(
        and_(
            Invoice.status == DBInvoiceStatus.PAID,
            Invoice.paid_at >= start,
            Invoice.paid_at <= end
        )
    )
    if merchant_id is not None:
        query = query.filter(Invoice.merchant_id == merchant_id)
    paid = query.scalar() or 0
    
    query = db.query(Invoice).filter(
        and_(
            Invoice.status == DBInvoiceStatus.PAID,
            Invoice.paid_at >= start,
            Invoice.paid_at <= end
        )
    )
    if merchant_id is not None:
        query = query.filter(Invoice.merchant_id == merchant_id)

    paid_invoices = query.all()
    volume = Decimal("0")
    for inv in paid_invoices:
        amount = Decimal(str(inv.total or 0))
        converted = await _convert_amount(amount, getattr(inv, "fiat_currency", "USD"), target_currency)
        volume += converted

    volume = volume.quantize(Decimal("0.01"))
    
    return {
        "sent": sent,
        "paid": paid,
        "volume": volume
    }


async def get_subscription_metrics(
    db: Session,
    merchant_id: Optional[uuid.UUID],
    start: datetime,
    end: datetime,
    target_currency: str,
) -> dict:
    """Get subscription metrics for a period"""
    # Active subscriptions
    query = db.query(func.count(Subscription.id)).filter(
        Subscription.status.in_([
            DBSubscriptionStatus.ACTIVE,
            DBSubscriptionStatus.TRIALING
        ])
    )
    if merchant_id is not None:
        query = query.filter(Subscription.merchant_id == merchant_id)
    active = query.scalar() or 0
    
    # New subscriptions in period
    query = db.query(func.count(Subscription.id)).filter(
        and_(
            Subscription.created_at >= start,
            Subscription.created_at <= end
        )
    )
    if merchant_id is not None:
        query = query.filter(Subscription.merchant_id == merchant_id)
    new = query.scalar() or 0
    
    # Churned (cancelled) in period
    query = db.query(func.count(Subscription.id)).filter(
        and_(
            Subscription.status == DBSubscriptionStatus.CANCELLED,
            Subscription.cancelled_at >= start,
            Subscription.cancelled_at <= end
        )
    )
    if merchant_id is not None:
        query = query.filter(Subscription.merchant_id == merchant_id)
    churned = query.scalar() or 0
    
    # MRR calculation (simplified)
    payment_query = db.query(SubscriptionPayment).join(
        Subscription,
        SubscriptionPayment.subscription_id == Subscription.id,
    ).filter(
        and_(
            SubscriptionPayment.status == PaymentStatus.PAID,
            SubscriptionPayment.paid_at >= start,
            SubscriptionPayment.paid_at <= end
        )
    )
    if merchant_id is not None:
        payment_query = payment_query.filter(Subscription.merchant_id == merchant_id)

    mrr = Decimal("0")
    for row in payment_query.all():
        amount = Decimal(str(row.amount or 0))
        converted = await _convert_amount(amount, row.fiat_currency, target_currency)
        mrr += converted

    mrr = mrr.quantize(Decimal("0.01"))
    
    return {
        "active": active,
        "new": new,
        "churned": churned,
        "mrr": mrr
    }


def calculate_change(previous: float, current: float) -> Optional[Decimal]:
    """Calculate percentage change"""
    if previous == 0:
        return None
    change = ((current - previous) / previous) * 100
    return Decimal(str(round(change, 2)))


async def aggregate_revenue_by_interval(
    payments: list,
    interval: str,
    start: datetime,
    end: datetime,
    target_currency: str,
) -> list[dict]:
    """Aggregate payments by time interval"""
    # Group payments by interval
    buckets = {}
    
    for payment in payments:
        if interval == "hour":
            key = payment.paid_at.replace(minute=0, second=0, microsecond=0)
        elif interval == "day":
            key = payment.paid_at.replace(hour=0, minute=0, second=0, microsecond=0)
        else:  # week
            # Get start of week
            key = payment.paid_at - timedelta(days=payment.paid_at.weekday())
            key = key.replace(hour=0, minute=0, second=0, microsecond=0)
        
        if key not in buckets:
            buckets[key] = {"volume": Decimal("0"), "count": 0}
        
        converted = await _convert_amount(
            Decimal(str(payment.amount_fiat or 0)),
            payment.fiat_currency,
            target_currency,
        )
        buckets[key]["volume"] += converted
        buckets[key]["count"] += 1
    
    # Convert to sorted list
    result = []
    for date, data in sorted(buckets.items()):
        result.append({
            "date": date.isoformat(),
            "volume": float(data["volume"]),
            "payment_count": data["count"]
        })
    
    return result


# ========================
# MRR / ARR ENDPOINTS
# ========================

def _interval_months(interval: str) -> int:
    """Map SubscriptionInterval to months for MRR normalisation."""
    return {
        "daily": 1,    # daily treated as ~30 days = 1 month
        "weekly": 1,
        "monthly": 1,
        "quarterly": 3,
        "yearly": 12,
    }.get(interval, 1)


def _to_monthly(amount: Decimal, interval: str) -> Decimal:
    """Normalise any billing amount to a monthly equivalent."""
    mapping = {
        "daily": Decimal("30"),
        "weekly": Decimal(str(52 / 12)),
        "monthly": Decimal("1"),
        "quarterly": Decimal("1") / Decimal("3"),
        "yearly": Decimal("1") / Decimal("12"),
    }
    factor = mapping.get(interval, Decimal("1"))
    return (amount * factor).quantize(Decimal("0.01"))


async def _local_amount(amount: float, merchant: Merchant, amount_currency: str = "USD") -> Optional[LocalCurrencyAmount]:
    """Build LocalCurrencyAmount in merchant base currency from any fiat amount."""
    code, symbol = _resolve_currency_context(merchant)

    try:
        source = Decimal(str(amount))
        converted = await _convert_amount(source, amount_currency, code)
        return LocalCurrencyAmount(
            amount_usdc=float(source),
            amount_local=float(converted),
            local_currency=code,
            local_symbol=symbol,
            exchange_rate=float(converted / source) if source != 0 else 1.0,
            display_local=f"{symbol}{float(converted):,.2f}",
        )
    except Exception:
        return None


@router.get("/mrr-arr", response_model=MRRARRResponse)
async def get_mrr_arr(
    current_user: dict = Depends(require_merchant),
    db: Session = Depends(get_db),
):
    """
    Calculate MRR and ARR for the merchant in USD and local currency.
    MRR = sum of all active subscriptions normalised to monthly.
    ARR = MRR * 12.
    """
    merchant_id = uuid.UUID(current_user["id"])

    ck = make_cache_key("mrr_arr", merchant_id)
    cached = cache.get(ck, region="analytics")
    if cached is not None:
        return cached

    merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    m_currency, _ = _resolve_currency_context(merchant)

    # Fetch active subscriptions with their plans
    active_subs = (
        db.query(Subscription, SubscriptionPlan)
        .join(SubscriptionPlan, Subscription.plan_id == SubscriptionPlan.id)
        .filter(
            Subscription.merchant_id == merchant_id,
            Subscription.status.in_([
                DBSubscriptionStatus.ACTIVE,
                DBSubscriptionStatus.TRIALING,
            ]),
        )
        .all()
    )

    mrr = Decimal("0")
    for sub, plan in active_subs:
        plan_amount = await _convert_amount(
            Decimal(str(plan.amount or 0)),
            getattr(plan, "fiat_currency", "USD"),
            m_currency,
        )
        mrr += _to_monthly(plan_amount, plan.interval.value if hasattr(plan.interval, 'value') else plan.interval)

    arr = (mrr * 12).quantize(Decimal("0.01"))

    # Period comparison
    now = datetime.utcnow()
    period_start = now - timedelta(days=30)
    prev_start = period_start - timedelta(days=30)

    new_count = db.query(func.count(Subscription.id)).filter(
        Subscription.merchant_id == merchant_id,
        Subscription.created_at >= period_start,
    ).scalar() or 0

    churned_count = db.query(func.count(Subscription.id)).filter(
        Subscription.merchant_id == merchant_id,
        Subscription.status == DBSubscriptionStatus.CANCELLED,
        Subscription.cancelled_at >= period_start,
    ).scalar() or 0

    # Previous MRR for change %
    prev_paid_rows = db.query(SubscriptionPayment).join(
        Subscription,
        SubscriptionPayment.subscription_id == Subscription.id,
    ).filter(
        Subscription.merchant_id == merchant_id,
        SubscriptionPayment.status == PaymentStatus.PAID,
        SubscriptionPayment.paid_at >= prev_start,
        SubscriptionPayment.paid_at < period_start,
    ).all()

    prev_paid = Decimal("0")
    for row in prev_paid_rows:
        prev_paid += await _convert_amount(
            Decimal(str(row.amount or 0)),
            row.fiat_currency,
            m_currency,
        )

    change_pct = Decimal("0")
    if prev_paid > 0:
        change_pct = ((mrr - prev_paid) / prev_paid * 100).quantize(Decimal("0.01"))

    mrr_local = await _local_amount(float(mrr), merchant, m_currency) if merchant else None
    arr_local = await _local_amount(float(arr), merchant, m_currency) if merchant else None

    result = MRRARRResponse(
        mrr_usd=mrr,
        arr_usd=arr,
        mrr_local=mrr_local,
        arr_local=arr_local,
        active_subscriptions=len(active_subs),
        new_this_period=new_count,
        churned_this_period=churned_count,
        net_revenue_change_pct=change_pct,
    )
    cache.set(ck, result, region="analytics")
    return result


@router.get("/mrr-trend", response_model=MRRTrendResponse)
async def get_mrr_trend(
    months: int = Query(default=6, ge=1, le=24),
    current_user: dict = Depends(require_merchant),
    db: Session = Depends(get_db),
):
    """
    MRR trend over past N months — provides monthly data points for charting.
    """
    merchant_id = uuid.UUID(current_user["id"])

    ck = make_cache_key("mrr_trend", merchant_id, months)
    cached = cache.get(ck, region="analytics")
    if cached is not None:
        return cached

    now = datetime.utcnow()
    merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    m_currency, _ = _resolve_currency_context(merchant)
    points = []

    for i in range(months - 1, -1, -1):
        month_end = (now.replace(day=1) - timedelta(days=1) * 0) if i == 0 else (
            now.replace(day=1) - timedelta(days=30 * i)
        )
        month_start = month_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if i == 0:
            month_end = now
        else:
            # last day of that month
            next_month = month_start + timedelta(days=32)
            month_end = next_month.replace(day=1) - timedelta(seconds=1)

        # Sum subscription payments in that month
        monthly_rows = db.query(SubscriptionPayment).join(
            Subscription,
            SubscriptionPayment.subscription_id == Subscription.id,
        ).filter(
            Subscription.merchant_id == merchant_id,
            SubscriptionPayment.status == PaymentStatus.PAID,
            SubscriptionPayment.paid_at >= month_start,
            SubscriptionPayment.paid_at <= month_end,
        ).all()

        monthly_rev = Decimal("0")
        for row in monthly_rows:
            monthly_rev += await _convert_amount(
                Decimal(str(row.amount or 0)),
                row.fiat_currency,
                m_currency,
            )

        sub_count = db.query(func.count(Subscription.id)).filter(
            Subscription.merchant_id == merchant_id,
            Subscription.created_at <= month_end,
            Subscription.status.in_([DBSubscriptionStatus.ACTIVE, DBSubscriptionStatus.TRIALING]),
        ).scalar() or 0

        new_count = db.query(func.count(Subscription.id)).filter(
            Subscription.merchant_id == merchant_id,
            Subscription.created_at >= month_start,
            Subscription.created_at <= month_end,
        ).scalar() or 0

        churned = db.query(func.count(Subscription.id)).filter(
            Subscription.merchant_id == merchant_id,
            Subscription.status == DBSubscriptionStatus.CANCELLED,
            Subscription.cancelled_at >= month_start,
            Subscription.cancelled_at <= month_end,
        ).scalar() or 0

        points.append(MRRTrendPoint(
            date=month_start.strftime("%Y-%m"),
            mrr_usd=float(monthly_rev),
            subscription_count=sub_count,
            new=new_count,
            churned=churned,
        ))

    result = MRRTrendResponse(points=points, period_months=months)
    cache.set(ck, result, region="analytics")
    return result


# ========================
# PAYMENT TRACKING
# ========================

@router.get("/payments/{session_id}/track", response_model=PaymentTrackingResponse)
async def track_payment(
    session_id: str,
    current_user: dict = Depends(require_merchant),
    db: Session = Depends(get_db),
):
    """
    Detailed payment tracking with event timeline.
    """
    merchant_id = uuid.UUID(current_user["id"])
    session = db.query(PaymentSession).filter(
        PaymentSession.id == session_id,
        PaymentSession.merchant_id == merchant_id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Payment session not found")

    events = (
        db.query(PaymentEvent)
        .filter(PaymentEvent.session_id == session_id)
        .order_by(PaymentEvent.created_at.asc())
        .all()
    )

    return PaymentTrackingResponse(
        session_id=session.id,
        status=session.status.value if hasattr(session.status, 'value') else session.status,
        amount_fiat=float(session.amount_fiat),
        fiat_currency=session.fiat_currency,
        token=session.token,
        chain=session.chain,
        tx_hash=session.tx_hash,
        block_number=session.block_number,
        confirmations=session.confirmations,
        payer_email=session.payer_email,
        payer_name=session.payer_name,
        created_at=session.created_at,
        paid_at=session.paid_at,
        expires_at=session.expires_at,
        events=[
            {
                "event_type": e.event_type,
                "chain": e.chain,
                "tx_hash": e.tx_hash,
                "details": e.details,
                "created_at": e.created_at.isoformat(),
            }
            for e in events
        ],
    )


# ========================
# SUBSCRIPTION TRACKING
# ========================

@router.get("/subscriptions/{subscription_id}/track", response_model=SubscriptionTrackingResponse)
async def track_subscription(
    subscription_id: str,
    current_user: dict = Depends(require_merchant),
    db: Session = Depends(get_db),
):
    """
    Detailed subscription tracking with payment history.
    """
    merchant_id = uuid.UUID(current_user["id"])
    sub = db.query(Subscription).filter(
        Subscription.id == subscription_id,
        Subscription.merchant_id == merchant_id,
    ).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")

    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == sub.plan_id).first()

    payments = (
        db.query(SubscriptionPayment)
        .filter(SubscriptionPayment.subscription_id == subscription_id)
        .order_by(SubscriptionPayment.created_at.desc())
        .all()
    )

    total_paid = sum(float(p.amount) for p in payments if p.status == PaymentStatus.PAID)

    return SubscriptionTrackingResponse(
        id=sub.id,
        plan_name=plan.name if plan else "Unknown",
        customer_email=sub.customer_email,
        customer_name=sub.customer_name,
        status=sub.status.value if hasattr(sub.status, 'value') else sub.status,
        current_period_start=sub.current_period_start,
        current_period_end=sub.current_period_end,
        next_payment_at=sub.next_payment_at,
        last_payment_at=sub.last_payment_at,
        failed_payment_count=sub.failed_payment_count or 0,
        total_paid_usd=total_paid,
        payment_count=len(payments),
        events=[
            {
                "period_start": p.period_start.isoformat(),
                "period_end": p.period_end.isoformat(),
                "amount": float(p.amount),
                "status": p.status.value if hasattr(p.status, 'value') else p.status,
                "paid_at": p.paid_at.isoformat() if p.paid_at else None,
            }
            for p in payments
        ],
    )


# ========================
# CACHE STATS (admin/debug)
# ========================

@router.get("/cache/stats")
async def get_cache_stats(
    current_user: dict = Depends(require_merchant),
):
    """Return cache hit/miss statistics."""
    return cache.stats()
