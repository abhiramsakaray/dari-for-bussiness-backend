"""
Immutable Ledger Service

Records every financial event as a double-entry ledger row.
Each entry is chained via sha256(prev_hash + entry_data) to ensure
immutability — any tampering breaks the hash chain.

Entry types:
  - DEBIT / CREDIT: Payment received / disbursed
  - CONVERSION: Currency exchange event
  - SETTLEMENT: Funds settled to merchant
  - FEE: Platform fee deducted
  - REFUND_DEBIT / REFUND_CREDIT: Refund entries
"""

import hashlib
import json
import logging
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.models import LedgerEntry, LedgerEntryType

logger = logging.getLogger(__name__)


def _compute_hash(prev_hash: Optional[str], entry_data: dict) -> str:
    """Compute sha256 chain hash for a ledger entry."""
    canonical = json.dumps(entry_data, sort_keys=True, default=str)
    payload = f"{prev_hash or 'GENESIS'}:{canonical}"
    return hashlib.sha256(payload.encode()).hexdigest()


def _get_last_hash(merchant_id: str, db: Session) -> Optional[str]:
    """Get the hash of the most recent ledger entry for a merchant."""
    last = (
        db.query(LedgerEntry.entry_hash)
        .filter(LedgerEntry.merchant_id == merchant_id)
        .order_by(desc(LedgerEntry.created_at))
        .first()
    )
    return last[0] if last else None


def record_entry(
    db: Session,
    *,
    merchant_id: str,
    entry_type: LedgerEntryType,
    amount: Decimal,
    currency: str,
    direction: str,  # "debit" or "credit"
    session_id: Optional[str] = None,
    counter_amount: Optional[Decimal] = None,
    counter_currency: Optional[str] = None,
    exchange_rate: Optional[Decimal] = None,
    reference_type: Optional[str] = None,
    reference_id: Optional[str] = None,
    description: Optional[str] = None,
    balance_after: Optional[Decimal] = None,
) -> LedgerEntry:
    """
    Record an immutable ledger entry.

    The entry is hash-chained to the previous entry for the same merchant.
    """
    prev_hash = _get_last_hash(merchant_id, db)

    entry_data = {
        "merchant_id": str(merchant_id),
        "entry_type": entry_type.value,
        "amount": str(amount),
        "currency": currency,
        "direction": direction,
        "session_id": session_id,
        "counter_amount": str(counter_amount) if counter_amount else None,
        "counter_currency": counter_currency,
        "exchange_rate": str(exchange_rate) if exchange_rate else None,
        "reference_type": reference_type,
        "reference_id": reference_id,
    }

    entry_hash = _compute_hash(prev_hash, entry_data)

    entry = LedgerEntry(
        merchant_id=merchant_id,
        session_id=session_id,
        entry_type=entry_type,
        amount=amount,
        currency=currency,
        direction=direction,
        counter_amount=counter_amount,
        counter_currency=counter_currency,
        exchange_rate=exchange_rate,
        reference_type=reference_type,
        reference_id=reference_id,
        description=description,
        balance_after=balance_after,
        entry_hash=entry_hash,
        prev_hash=prev_hash,
    )

    db.add(entry)
    db.flush()

    logger.info(
        "Ledger %s: %s %s %s (session=%s, hash=%s…)",
        direction,
        entry_type.value,
        amount,
        currency,
        session_id,
        entry_hash[:12],
    )

    return entry


def record_payment_received(
    db: Session,
    *,
    merchant_id: str,
    session_id: str,
    token_amount: Decimal,
    token_symbol: str,
    fiat_amount: Optional[Decimal] = None,
    fiat_currency: Optional[str] = None,
    exchange_rate: Optional[Decimal] = None,
    balance_after: Optional[Decimal] = None,
) -> LedgerEntry:
    """Convenience: record a payment credit to the merchant."""
    return record_entry(
        db,
        merchant_id=merchant_id,
        session_id=session_id,
        entry_type=LedgerEntryType.CREDIT,
        amount=token_amount,
        currency=token_symbol,
        direction="credit",
        counter_amount=fiat_amount,
        counter_currency=fiat_currency,
        exchange_rate=exchange_rate,
        reference_type="payment",
        reference_id=session_id,
        description=f"Payment received: {token_amount} {token_symbol}",
        balance_after=balance_after,
    )


def record_fee(
    db: Session,
    *,
    merchant_id: str,
    session_id: str,
    fee_amount: Decimal,
    currency: str,
    description: str = "Platform fee",
) -> LedgerEntry:
    """Record a platform fee deduction."""
    return record_entry(
        db,
        merchant_id=merchant_id,
        session_id=session_id,
        entry_type=LedgerEntryType.FEE,
        amount=fee_amount,
        currency=currency,
        direction="debit",
        reference_type="fee",
        reference_id=session_id,
        description=description,
    )


def record_refund(
    db: Session,
    *,
    merchant_id: str,
    session_id: str,
    refund_id: str,
    amount: Decimal,
    currency: str,
) -> tuple[LedgerEntry, LedgerEntry]:
    """Record a refund as a debit from merchant + credit to payer."""
    debit = record_entry(
        db,
        merchant_id=merchant_id,
        session_id=session_id,
        entry_type=LedgerEntryType.REFUND_DEBIT,
        amount=amount,
        currency=currency,
        direction="debit",
        reference_type="refund",
        reference_id=refund_id,
        description=f"Refund debit: {amount} {currency}",
    )
    credit = record_entry(
        db,
        merchant_id=merchant_id,
        session_id=session_id,
        entry_type=LedgerEntryType.REFUND_CREDIT,
        amount=amount,
        currency=currency,
        direction="credit",
        reference_type="refund",
        reference_id=refund_id,
        description=f"Refund credit to payer: {amount} {currency}",
    )
    return debit, credit


def record_conversion(
    db: Session,
    *,
    merchant_id: str,
    session_id: Optional[str] = None,
    from_amount: Decimal,
    from_currency: str,
    to_amount: Decimal,
    to_currency: str,
    exchange_rate: Decimal,
) -> LedgerEntry:
    """Record a currency conversion event."""
    return record_entry(
        db,
        merchant_id=merchant_id,
        session_id=session_id,
        entry_type=LedgerEntryType.CONVERSION,
        amount=from_amount,
        currency=from_currency,
        direction="debit",
        counter_amount=to_amount,
        counter_currency=to_currency,
        exchange_rate=exchange_rate,
        reference_type="conversion",
        description=f"Converted {from_amount} {from_currency} → {to_amount} {to_currency}",
    )


def verify_chain_integrity(merchant_id: str, db: Session) -> tuple[bool, int]:
    """
    Verify the hash chain integrity for a merchant's ledger.

    Returns (is_valid, entries_checked).
    """
    entries = (
        db.query(LedgerEntry)
        .filter(LedgerEntry.merchant_id == merchant_id)
        .order_by(LedgerEntry.created_at)
        .all()
    )

    prev_hash = None
    for i, entry in enumerate(entries):
        if entry.prev_hash != prev_hash:
            logger.error(
                "Ledger integrity violation at entry %s (index %d)",
                entry.id, i,
            )
            return False, i

        entry_data = {
            "merchant_id": str(entry.merchant_id),
            "entry_type": entry.entry_type.value,
            "amount": str(entry.amount),
            "currency": entry.currency,
            "direction": entry.direction,
            "session_id": entry.session_id,
            "counter_amount": str(entry.counter_amount) if entry.counter_amount else None,
            "counter_currency": entry.counter_currency,
            "exchange_rate": str(entry.exchange_rate) if entry.exchange_rate else None,
            "reference_type": entry.reference_type,
            "reference_id": entry.reference_id,
        }

        expected_hash = _compute_hash(prev_hash, entry_data)
        if entry.entry_hash != expected_hash:
            logger.error(
                "Ledger hash mismatch at entry %s (index %d)",
                entry.id, i,
            )
            return False, i

        prev_hash = entry.entry_hash

    return True, len(entries)
