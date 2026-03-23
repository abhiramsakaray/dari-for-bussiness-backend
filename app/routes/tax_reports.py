"""
Tax & Compliance Reporting Routes

Provides tax-ready reports for merchants:
  - Summary report (revenue, tax, refunds, breakdowns)
  - Transaction-level report (exportable as CSV for accounting)
  - Subscription revenue report (MRR, ARR)

Security:
  - All endpoints require merchant authentication
  - Input dates are validated to prevent injection
  - CSV export is sanitized (no formula injection)
"""

import csv
import io
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, case

from app.core.database import get_db
from app.core import require_merchant
from app.models.models import (
    Merchant, PaymentSession, PaymentStatus, Invoice, InvoiceStatus,
    Subscription, SubscriptionPayment, Refund,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tax-reports", tags=["Tax & Compliance"])


def _parse_date(date_str: str, name: str) -> datetime:
    """Safely parse a date string. Prevents injection."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        raise HTTPException(400, f"Invalid {name} format. Use YYYY-MM-DD.")


def _sanitize_csv_value(value) -> str:
    """
    Sanitize a value for CSV export.
    Prevents CSV formula injection (=, +, -, @, |, \\t, \\r, \\n).
    """
    s = str(value) if value is not None else ""
    if s and s[0] in ("=", "+", "-", "@", "|", "\t", "\r", "\n"):
        s = "'" + s  # Prefix with single quote to neutralize formula
    return s


@router.get("/summary")
async def tax_summary(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant),
):
    """
    Tax summary report for a date range.

    Returns total revenue, tax collected, refunds, net revenue,
    and breakdowns by token, chain, and payment type.
    """
    merchant_id = current_user["id"]
    start = _parse_date(start_date, "start_date")
    end = _parse_date(end_date, "end_date") + timedelta(days=1)  # Inclusive

    if end <= start:
        raise HTTPException(400, "end_date must be after start_date")

    # ── Payments ──
    paid_statuses = [PaymentStatus.PAID, PaymentStatus.CONFIRMED]

    payments = db.query(PaymentSession).filter(
        and_(
            PaymentSession.merchant_id == merchant_id,
            PaymentSession.status.in_(paid_statuses),
            PaymentSession.paid_at >= start,
            PaymentSession.paid_at < end,
        )
    ).all()

    total_revenue_usd = sum(float(p.amount_fiat or 0) for p in payments)
    total_payments = len(payments)

    # Breakdowns
    by_token = {}
    by_chain = {}
    for p in payments:
        token = p.token or "USDC"
        chain = p.chain or "stellar"
        by_token[token] = by_token.get(token, 0) + float(p.amount_fiat or 0)
        by_chain[chain] = by_chain.get(chain, 0) + float(p.amount_fiat or 0)

    # ── Invoices (tax collected) ──
    invoices = db.query(Invoice).filter(
        and_(
            Invoice.merchant_id == merchant_id,
            Invoice.status == InvoiceStatus.PAID,
            Invoice.paid_at >= start,
            Invoice.paid_at < end,
        )
    ).all()

    total_tax_collected = sum(float(i.tax or 0) for i in invoices)
    total_discounts = sum(float(i.discount or 0) for i in invoices)

    # ── Refunds ──
    from app.models.models import RefundStatus
    refunds = db.query(Refund).filter(
        and_(
            Refund.merchant_id == merchant_id,
            Refund.status == RefundStatus.COMPLETED,
            Refund.completed_at >= start,
            Refund.completed_at < end,
        )
    ).all()

    total_refunds = len(refunds)
    total_refund_amount = sum(float(r.amount or 0) for r in refunds)

    # ── Subscription Revenue ──
    sub_payments = db.query(SubscriptionPayment).filter(
        and_(
            SubscriptionPayment.subscription.has(
                Subscription.merchant_id == merchant_id
            ),
            SubscriptionPayment.status.in_(paid_statuses),
            SubscriptionPayment.paid_at >= start,
            SubscriptionPayment.paid_at < end,
        )
    ).all()

    subscription_revenue = sum(float(sp.amount or 0) for sp in sub_payments)

    # ── Net ──
    net_revenue = total_revenue_usd - total_refund_amount

    # ── Merchant local currency info ──
    merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    merchant_currency = merchant.base_currency if merchant else "USD"

    return {
        "period": {"start": start_date, "end": end_date},
        "currency": merchant_currency,
        "summary": {
            "total_revenue": round(total_revenue_usd, 2),
            "total_payments": total_payments,
            "total_tax_collected": round(total_tax_collected, 2),
            "total_discounts_given": round(total_discounts, 2),
            "total_refunds": total_refunds,
            "total_refund_amount": round(total_refund_amount, 2),
            "net_revenue": round(net_revenue, 2),
            "subscription_revenue": round(subscription_revenue, 2),
            "one_time_revenue": round(total_revenue_usd - subscription_revenue, 2),
        },
        "breakdown_by_token": {k: round(v, 2) for k, v in by_token.items()},
        "breakdown_by_chain": {k: round(v, 2) for k, v in by_chain.items()},
    }


@router.get("/transactions")
async def tax_transactions(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    format: str = Query("json", description="Output format: json or csv"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant),
):
    """
    Transaction-level report for tax filing.

    Each row includes full multi-currency details:
    - Payer's local currency and amount (what the customer saw)
    - Stablecoin type and amount (what moved on-chain)
    - Merchant's local currency and amount (settlement value)
    - Blockchain, transaction hash

    Export as CSV for direct import into accounting software (Tally, QuickBooks, Xero, etc.)
    """
    merchant_id = current_user["id"]
    start = _parse_date(start_date, "start_date")
    end = _parse_date(end_date, "end_date") + timedelta(days=1)

    if end <= start:
        raise HTTPException(400, "end_date must be after start_date")

    paid_statuses = [PaymentStatus.PAID, PaymentStatus.CONFIRMED]

    payments = db.query(PaymentSession).filter(
        and_(
            PaymentSession.merchant_id == merchant_id,
            PaymentSession.status.in_(paid_statuses),
            PaymentSession.paid_at >= start,
            PaymentSession.paid_at < end,
        )
    ).order_by(PaymentSession.paid_at).all()

    rows = []
    for p in payments:
        # Try to find associated invoice
        invoice = db.query(Invoice).filter(
            Invoice.payment_session_id == p.id
        ).first()

        rows.append({
            "date": p.paid_at.strftime("%Y-%m-%d") if p.paid_at else "",
            "session_id": p.id,
            "order_id": p.order_id or "",
            "invoice_number": invoice.invoice_number if invoice else "",
            "customer_email": p.payer_email or "",
            "customer_name": p.payer_name or "",
            "payer_country": p.payer_country or "",
            "fiat_currency": p.fiat_currency or "USD",
            "fiat_amount": float(p.amount_fiat or 0),
            "payer_currency": p.payer_currency or "",
            "payer_amount": float(p.payer_amount_local or 0) if p.payer_amount_local else None,
            "stablecoin": p.token or "USDC",
            "stablecoin_amount": p.amount_token or p.amount_usdc or "",
            "merchant_currency": p.merchant_currency or "",
            "merchant_amount": float(p.merchant_amount_local or 0) if p.merchant_amount_local else None,
            "chain": p.chain or "stellar",
            "tx_hash": p.tx_hash or "",
            "is_cross_border": p.is_cross_border or False,
            "tax": float(invoice.tax or 0) if invoice else 0,
            "discount": float(invoice.discount or 0) if invoice else 0,
        })

    if format.lower() == "csv":
        return _generate_csv_response(rows, f"transactions_{start_date}_to_{end_date}.csv")

    return {
        "period": {"start": start_date, "end": end_date},
        "total_transactions": len(rows),
        "transactions": rows,
    }


@router.get("/subscription-revenue")
async def subscription_revenue_report(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant),
):
    """
    Subscription-specific revenue report.
    Includes MRR, ARR, churn, and per-subscription payment history.
    """
    merchant_id = current_user["id"]
    start = _parse_date(start_date, "start_date")
    end = _parse_date(end_date, "end_date") + timedelta(days=1)

    # Active subscriptions
    active_subs = db.query(Subscription).filter(
        and_(
            Subscription.merchant_id == merchant_id,
            Subscription.status == "active",
        )
    ).all()

    # Churned in period
    from app.models.models import SubscriptionStatus
    churned_subs = db.query(Subscription).filter(
        and_(
            Subscription.merchant_id == merchant_id,
            Subscription.status == SubscriptionStatus.CANCELLED,
            Subscription.cancelled_at >= start,
            Subscription.cancelled_at < end,
        )
    ).all()

    # New subs in period
    new_subs = db.query(Subscription).filter(
        and_(
            Subscription.merchant_id == merchant_id,
            Subscription.created_at >= start,
            Subscription.created_at < end,
        )
    ).all()

    # Payments in period
    paid_statuses = [PaymentStatus.PAID, PaymentStatus.CONFIRMED]
    sub_payments = db.query(SubscriptionPayment).filter(
        and_(
            SubscriptionPayment.subscription.has(
                Subscription.merchant_id == merchant_id
            ),
            SubscriptionPayment.status.in_(paid_statuses),
            SubscriptionPayment.paid_at >= start,
            SubscriptionPayment.paid_at < end,
        )
    ).all()

    total_sub_revenue = sum(float(sp.amount or 0) for sp in sub_payments)

    # Calculate MRR (sum of active plan amounts)
    mrr = Decimal("0")
    for sub in active_subs:
        if sub.plan:
            # Normalize to monthly
            plan = sub.plan
            monthly_amount = float(plan.amount or 0)
            interval = plan.interval.value if hasattr(plan.interval, 'value') else str(plan.interval)
            interval_count = plan.interval_count or 1

            if interval == "weekly":
                monthly_amount = monthly_amount * (4.33 / interval_count)
            elif interval == "monthly":
                monthly_amount = monthly_amount / interval_count
            elif interval == "yearly":
                monthly_amount = monthly_amount / (12 * interval_count)

            mrr += Decimal(str(round(monthly_amount, 2)))

    arr = mrr * 12

    # Per-subscription breakdown
    sub_details = []
    for sub in active_subs[:50]:  # Limit to 50
        payments_for_sub = [sp for sp in sub_payments if sp.subscription_id == sub.id]
        sub_details.append({
            "subscription_id": sub.id,
            "customer_email": sub.customer_email,
            "plan_name": sub.plan.name if sub.plan else "N/A",
            "status": sub.status.value if hasattr(sub.status, 'value') else str(sub.status),
            "payments_in_period": len(payments_for_sub),
            "revenue_in_period": sum(float(sp.amount or 0) for sp in payments_for_sub),
            "total_lifetime_revenue": float(sub.total_revenue or 0),
            "created_at": sub.created_at.isoformat() if sub.created_at else "",
        })

    return {
        "period": {"start": start_date, "end": end_date},
        "metrics": {
            "mrr": float(mrr),
            "arr": float(arr),
            "total_revenue_in_period": round(total_sub_revenue, 2),
            "active_subscriptions": len(active_subs),
            "new_subscriptions": len(new_subs),
            "churned_subscriptions": len(churned_subs),
            "churn_rate": round(len(churned_subs) / max(len(active_subs), 1) * 100, 2),
        },
        "subscriptions": sub_details,
    }


def _generate_csv_response(rows: list, filename: str) -> StreamingResponse:
    """Generate a sanitized CSV streaming response."""
    output = io.StringIO()
    if not rows:
        output.write("No transactions found\n")
    else:
        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
        writer.writeheader()
        for row in rows:
            sanitized = {k: _sanitize_csv_value(v) for k, v in row.items()}
            writer.writerow(sanitized)

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
