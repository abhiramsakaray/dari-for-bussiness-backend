"""
Merchant Analytics API Routes
Analytics and reporting for merchants
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
from app.models.models import (
    Merchant, PaymentSession, Invoice, Subscription, SubscriptionPayment,
    PaymentStatus, AnalyticsSnapshot, InvoiceStatus as DBInvoiceStatus,
    SubscriptionStatus as DBSubscriptionStatus
)
from app.schemas.schemas import (
    AnalyticsOverview, PaymentMetrics, VolumeByToken, VolumeByChain,
    AnalyticsTimeSeries, RevenueTimeSeries, AnalyticsPeriod
)

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/overview", response_model=AnalyticsOverview)
async def get_analytics_overview(
    period: AnalyticsPeriod = AnalyticsPeriod.MONTH,
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
    # TEMP: Show all data (no auth)
    merchant_id = None
    
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
    current_metrics = get_payment_metrics(db, merchant_id, period_start, now)
    
    # Get previous period for comparison
    prev_metrics = get_payment_metrics(db, merchant_id, prev_period_start, period_start)
    
    # Calculate changes
    payments_change = calculate_change(
        prev_metrics.total_payments, 
        current_metrics.total_payments
    )
    volume_change = calculate_change(
        float(prev_metrics.total_volume_usd),
        float(current_metrics.total_volume_usd)
    )
    
    # Get volume breakdowns
    volume_by_token = get_volume_by_token(db, merchant_id, period_start, now)
    volume_by_chain = get_volume_by_chain(db, merchant_id, period_start, now)
    
    # Get invoice metrics
    invoice_metrics = get_invoice_metrics(db, merchant_id, period_start, now)
    
    # Get subscription metrics
    subscription_metrics = get_subscription_metrics(db, merchant_id, period_start, now)
    
    return AnalyticsOverview(
        period_start=period_start,
        period_end=now,
        period=period.value,
        payments=current_metrics,
        volume_by_token=volume_by_token,
        volume_by_chain=volume_by_chain,
        invoices_sent=invoice_metrics["sent"],
        invoices_paid=invoice_metrics["paid"],
        invoice_volume_usd=invoice_metrics["volume"],
        active_subscriptions=subscription_metrics["active"],
        new_subscriptions=subscription_metrics["new"],
        churned_subscriptions=subscription_metrics["churned"],
        subscription_mrr=subscription_metrics["mrr"],
        payments_change_pct=payments_change,
        volume_change_pct=volume_change
    )


@router.get("/revenue")
async def get_revenue_timeseries(
    period: AnalyticsPeriod = AnalyticsPeriod.MONTH,
    db: Session = Depends(get_db)
):
    """
    Get revenue time series data.
    
    Returns daily/weekly/monthly revenue data points for charting.
    """
    # TEMP: Show all data (no auth)
    merchant_id = None
    
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
    data_points = aggregate_revenue_by_interval(payments, interval, period_start, now)
    
    return {
        "period": period.value,
        "interval": interval,
        "period_start": period_start.isoformat(),
        "period_end": now.isoformat(),
        "data": data_points
    }


@router.get("/payments/summary")
async def get_payment_summary(
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db)
):
    """
    Get a summary of payment activity.
    
    Returns counts and amounts by status.
    """
    # TEMP: Show all data (no auth)
    merchant_id = None
    
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
            "total_usd": float(total) if total else 0
        }
    
    return {
        "period_days": days,
        "by_status": summary
    }


@router.get("/top-customers")
async def get_top_customers(
    limit: int = Query(default=10, ge=1, le=50),
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db)
):
    """
    Get top customers by payment volume.
    """
    # TEMP: Show all data (no auth)
    merchant_id = None
    
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
    db: Session = Depends(get_db)
):
    """
    Get checkout conversion metrics.
    
    Returns:
    - Sessions created vs completed
    - Average time to payment
    - Drop-off rates by step
    """
    # TEMP: Show all data (no auth)
    merchant_id = None
    
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
    db: Session = Depends(get_db)
):
    """
    Get analytics by blockchain network.
    """
    # TEMP: Show all data (no auth)
    merchant_id = None
    
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
                "volume_usd": float(d.volume or 0),
                "percentage": round((float(d.volume or 0) / total_volume * 100), 2) if total_volume > 0 else 0
            }
            for d in chain_data
        ]
    }


# ========================
# HELPER FUNCTIONS
# ========================

def get_payment_metrics(
    db: Session, 
    merchant_id: Optional[uuid.UUID], 
    start: datetime, 
    end: datetime
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
    
    query = db.query(func.sum(PaymentSession.amount_fiat)).filter(
        and_(
            PaymentSession.status == PaymentStatus.PAID,
            PaymentSession.created_at >= start,
            PaymentSession.created_at <= end
        )
    )
    if merchant_id is not None:
        query = query.filter(PaymentSession.merchant_id == merchant_id)
    volume = query.scalar() or Decimal("0")
    
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
        total_volume_usd=volume,
        avg_payment_usd=avg_payment,
        conversion_rate=conversion
    )


def get_volume_by_token(
    db: Session,
    merchant_id: Optional[uuid.UUID],
    start: datetime,
    end: datetime
) -> list[VolumeByToken]:
    """Get volume breakdown by token"""
    query = db.query(
        PaymentSession.token,
        func.sum(PaymentSession.amount_fiat).label('volume'),
        func.count(PaymentSession.id).label('count')
    ).filter(
        and_(
            PaymentSession.status == PaymentStatus.PAID,
            PaymentSession.created_at >= start,
            PaymentSession.created_at <= end,
            PaymentSession.token.isnot(None)
        )
    )
    
    if merchant_id is not None:
        query = query.filter(PaymentSession.merchant_id == merchant_id)
    
    data = query.group_by(PaymentSession.token).all()
    
    return [
        VolumeByToken(
            token=d.token,
            volume_usd=Decimal(str(d.volume or 0)),
            payment_count=d.count
        )
        for d in data
    ]


def get_volume_by_chain(
    db: Session,
    merchant_id: Optional[uuid.UUID],
    start: datetime,
    end: datetime
) -> list[VolumeByChain]:
    """Get volume breakdown by chain"""
    query = db.query(
        PaymentSession.chain,
        func.sum(PaymentSession.amount_fiat).label('volume'),
        func.count(PaymentSession.id).label('count')
    ).filter(
        and_(
            PaymentSession.status == PaymentStatus.PAID,
            PaymentSession.created_at >= start,
            PaymentSession.created_at <= end,
            PaymentSession.chain.isnot(None)
        )
    )
    
    if merchant_id is not None:
        query = query.filter(PaymentSession.merchant_id == merchant_id)
    
    data = query.group_by(PaymentSession.chain).all()
    
    return [
        VolumeByChain(
            chain=d.chain,
            volume_usd=Decimal(str(d.volume or 0)),
            payment_count=d.count
        )
        for d in data
    ]


def get_invoice_metrics(
    db: Session,
    merchant_id: Optional[uuid.UUID],
    start: datetime,
    end: datetime
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
    
    query = db.query(func.sum(Invoice.total)).filter(
        and_(
            Invoice.status == DBInvoiceStatus.PAID,
            Invoice.paid_at >= start,
            Invoice.paid_at <= end
        )
    )
    if merchant_id is not None:
        query = query.filter(Invoice.merchant_id == merchant_id)
    volume = query.scalar() or Decimal("0")
    
    return {
        "sent": sent,
        "paid": paid,
        "volume": volume
    }


def get_subscription_metrics(
    db: Session,
    merchant_id: Optional[uuid.UUID],
    start: datetime,
    end: datetime
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
    mrr = db.query(func.sum(SubscriptionPayment.amount)).filter(
        and_(
            SubscriptionPayment.status == PaymentStatus.PAID,
            SubscriptionPayment.paid_at >= start,
            SubscriptionPayment.paid_at <= end
        )
    ).scalar() or Decimal("0")
    
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


def aggregate_revenue_by_interval(
    payments: list,
    interval: str,
    start: datetime,
    end: datetime
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
        
        buckets[key]["volume"] += payment.amount_fiat
        buckets[key]["count"] += 1
    
    # Convert to sorted list
    result = []
    for date, data in sorted(buckets.items()):
        result.append({
            "date": date.isoformat(),
            "volume_usd": float(data["volume"]),
            "payment_count": data["count"]
        })
    
    return result
