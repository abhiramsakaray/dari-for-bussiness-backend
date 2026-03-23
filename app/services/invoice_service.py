"""
Invoice Service
Auto-creates invoices from confirmed payments and subscriptions.
Includes multi-currency display (payer currency, stablecoin, merchant currency).
"""

import logging
import secrets
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.models import (
    Invoice, InvoiceStatus, PaymentSession, Merchant,
)

logger = logging.getLogger(__name__)


def generate_invoice_id() -> str:
    """Generate a cryptographically secure invoice ID."""
    return f"inv_{secrets.token_urlsafe(16)}"


def generate_invoice_number(merchant_id: str, db: Session) -> str:
    """Generate sequential invoice number for merchant."""
    count = db.query(Invoice).filter(
        Invoice.merchant_id == merchant_id
    ).count()
    return f"INV-{count + 1:04d}"


def create_invoice_from_payment(
    session: PaymentSession,
    db: Session,
) -> Optional[Invoice]:
    """
    Auto-create an Invoice from a confirmed PaymentSession.

    Maps all multi-currency fields so the invoice shows:
    - Payer's local currency amount (what the customer saw)
    - Stablecoin amount and type (what was transferred on-chain)
    - Merchant's local currency amount (what the merchant recognises)
    """
    try:
        # Don't duplicate — check if invoice already exists for this session
        existing = db.query(Invoice).filter(
            Invoice.payment_session_id == session.id
        ).first()
        if existing:
            logger.info(f"Invoice already exists for session {session.id}: {existing.id}")
            return existing

        merchant = session.merchant
        if not merchant:
            merchant = db.query(Merchant).filter(
                Merchant.id == session.merchant_id
            ).first()

        invoice_id = generate_invoice_id()
        invoice_number = generate_invoice_number(str(session.merchant_id), db)

        # Build line items from the payment
        token_symbol = session.token or "USDC"
        amount_fiat = float(session.amount_fiat) if session.amount_fiat else 0.0
        amount_token = session.amount_token or session.amount_usdc or "0"

        line_items = [{
            "description": f"Payment — Order {session.order_id or session.id}",
            "quantity": 1,
            "unit_price": amount_fiat,
            "total": amount_fiat,
        }]

        # Determine fiat currency (prefer merchant's base, fallback to session)
        fiat_currency = session.fiat_currency or (merchant.base_currency if merchant else "USD")

        invoice = Invoice(
            id=invoice_id,
            invoice_number=invoice_number,
            merchant_id=session.merchant_id,
            customer_email=session.payer_email or "unknown@customer.com",
            customer_name=session.payer_name,
            description=f"Payment for order {session.order_id or session.id}",
            line_items=line_items,
            subtotal=Decimal(str(amount_fiat)),
            tax=Decimal("0"),
            discount=session.discount_amount or Decimal("0"),
            total=Decimal(str(amount_fiat)) - (session.discount_amount or Decimal("0")),
            fiat_currency=fiat_currency,
            status=InvoiceStatus.PAID,
            due_date=datetime.utcnow(),
            issue_date=datetime.utcnow(),
            paid_at=session.paid_at or datetime.utcnow(),
            payment_session_id=session.id,
            amount_paid=Decimal(str(amount_fiat)),
            # Multi-currency fields
            tx_hash=session.tx_hash,
            chain=session.chain,
            token_symbol=token_symbol,
            token_amount=amount_token,
            payer_currency=session.payer_currency,
            payer_amount_local=session.payer_amount_local,
            merchant_currency=session.merchant_currency or (merchant.base_currency if merchant else None),
            merchant_amount_local=session.merchant_amount_local,
            # Merchant info for export
            notes=f"Auto-generated invoice for payment {session.id}",
            terms="Payment received via Dari for Business",
        )

        db.add(invoice)
        db.commit()
        db.refresh(invoice)

        logger.info(
            f"✅ Auto-created invoice {invoice_number} for session {session.id} "
            f"| {token_symbol} on {session.chain} | tx={session.tx_hash or 'N/A'}"
        )
        return invoice

    except Exception as e:
        logger.error(f"Failed to auto-create invoice for session {session.id}: {e}")
        db.rollback()
        return None


def create_invoice_from_subscription_payment(
    subscription,
    payment_record,
    db: Session,
) -> Optional[Invoice]:
    """
    Auto-create an Invoice from a subscription payment.
    """
    try:
        existing = db.query(Invoice).filter(
            Invoice.payment_session_id == payment_record.payment_session_id
        ).first() if payment_record.payment_session_id else None

        if existing:
            return existing

        merchant = db.query(Merchant).filter(
            Merchant.id == subscription.merchant_id
        ).first()

        invoice_id = generate_invoice_id()
        invoice_number = generate_invoice_number(str(subscription.merchant_id), db)

        plan = subscription.plan
        amount = float(payment_record.amount) if payment_record.amount else 0.0

        line_items = [{
            "description": f"Subscription: {plan.name if plan else 'N/A'} — "
                           f"{payment_record.period_start.strftime('%Y-%m-%d')} to "
                           f"{payment_record.period_end.strftime('%Y-%m-%d')}",
            "quantity": 1,
            "unit_price": amount,
            "total": amount,
        }]

        fiat_currency = payment_record.fiat_currency or (merchant.base_currency if merchant else "USD")

        invoice = Invoice(
            id=invoice_id,
            invoice_number=invoice_number,
            merchant_id=subscription.merchant_id,
            customer_email=subscription.customer_email,
            customer_name=subscription.customer_name,
            description=f"Subscription payment — {plan.name if plan else 'Subscription'}",
            line_items=line_items,
            subtotal=Decimal(str(amount)),
            tax=Decimal("0"),
            discount=Decimal("0"),
            total=Decimal(str(amount)),
            fiat_currency=fiat_currency,
            status=InvoiceStatus.PAID,
            due_date=datetime.utcnow(),
            issue_date=datetime.utcnow(),
            paid_at=payment_record.paid_at or datetime.utcnow(),
            payment_session_id=payment_record.payment_session_id,
            amount_paid=Decimal(str(amount)),
            token_symbol=subscription.customer_token or "USDC",
            chain=subscription.customer_chain,
            notes=f"Auto-generated for subscription {subscription.id}",
            terms="Recurring payment via Dari for Business",
        )

        db.add(invoice)
        db.commit()
        db.refresh(invoice)

        logger.info(f"✅ Auto-created subscription invoice {invoice_number} for sub {subscription.id}")
        return invoice

    except Exception as e:
        logger.error(f"Failed to auto-create subscription invoice: {e}")
        db.rollback()
        return None
