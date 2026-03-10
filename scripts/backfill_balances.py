"""
Backfill merchant balances from historically paid payment sessions.

Run this once to fix balances for payments that were confirmed before
the balance-crediting logic was added.

Usage:
    python -m scripts.backfill_balances
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decimal import Decimal
from collections import defaultdict
from sqlalchemy import func
from app.core.database import SessionLocal
from app.models.models import Merchant, PaymentSession, PaymentStatus

BALANCE_COLUMNS = {
    "USDC": "balance_usdc",
    "USDT": "balance_usdt",
    "PYUSD": "balance_pyusd",
}


def backfill():
    db = SessionLocal()
    try:
        # Get all paid sessions grouped by merchant + token
        paid_sessions = (
            db.query(PaymentSession)
            .filter(PaymentSession.status == PaymentStatus.PAID)
            .all()
        )

        # Aggregate amounts per merchant per token
        totals = defaultdict(lambda: defaultdict(Decimal))
        for s in paid_sessions:
            token = (s.token or "USDC").upper()
            amount_str = s.amount_token or s.amount_usdc or "0"
            try:
                amount = Decimal(str(amount_str))
            except Exception:
                amount = Decimal("0")
            totals[str(s.merchant_id)][token] += amount

        print(f"Found {len(paid_sessions)} paid sessions across {len(totals)} merchants\n")

        updated = 0
        for merchant_id, token_totals in totals.items():
            merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
            if not merchant:
                print(f"  ⚠ Merchant {merchant_id} not found, skipping")
                continue

            print(f"Merchant: {merchant.name} ({merchant_id})")
            for token, total in token_totals.items():
                col = BALANCE_COLUMNS.get(token)
                if not col:
                    print(f"  ⚠ Unknown token {token}, skipping")
                    continue
                current = getattr(merchant, col, None) or Decimal("0")
                if current >= total:
                    print(f"  {token}: already {current} >= computed {total}, skipping")
                    continue
                print(f"  {token}: {current} → {total}")
                setattr(merchant, col, total)
                updated += 1

        if updated > 0:
            db.commit()
            print(f"\n✅ Updated {updated} balance fields")
        else:
            print("\n✅ All balances already up to date")

    finally:
        db.close()


if __name__ == "__main__":
    backfill()
