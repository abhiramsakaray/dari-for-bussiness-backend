"""
AML & Compliance Service

Provides:
  - OFAC / sanctions list screening
  - High-risk jurisdiction detection
  - Transaction threshold alerts (CTR / SAR)
  - Velocity checks (suspicious activity patterns)
  - Compliance screening audit logging
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.config import settings
from app.models.models import (
    ComplianceScreening,
    PaymentSession,
    PaymentStatus,
)

logger = logging.getLogger(__name__)

# ── OFAC Sanctioned Countries (SDN) ──
SANCTIONED_COUNTRIES = {
    "north korea", "iran", "syria", "cuba", "crimea",
    "donetsk", "luhansk",
}

# ── High-Risk Jurisdictions (FATF grey/black list) ──
HIGH_RISK_JURISDICTIONS = {
    "myanmar", "afghanistan", "yemen", "south sudan",
    "libya", "somalia", "democratic republic of the congo",
    "venezuela", "pakistan", "nigeria", "haiti",
    "cayman islands", "panama",
}

# ── Sanctioned wallet prefixes (example patterns) ──
SANCTIONED_WALLET_PREFIXES: set[str] = set()


class ComplianceResult:
    """Result of a compliance screening."""

    def __init__(self):
        self.passed = True
        self.blocked = False
        self.flags: list[str] = []
        self.risk_level = "low"  # low, medium, high, critical
        self.details: dict = {}

    def flag(self, reason: str, level: str = "medium"):
        self.flags.append(reason)
        self.passed = False
        if _severity_rank(level) > _severity_rank(self.risk_level):
            self.risk_level = level

    def block(self, reason: str):
        self.flags.append(reason)
        self.passed = False
        self.blocked = True
        self.risk_level = "critical"


def _severity_rank(level: str) -> int:
    return {"low": 0, "medium": 1, "high": 2, "critical": 3}.get(level, 0)


# ── Screening Functions ──

def screen_country(country: Optional[str]) -> ComplianceResult:
    """Screen a country against OFAC sanctions and high-risk lists."""
    result = ComplianceResult()
    if not country:
        return result

    normalized = country.strip().lower()

    if normalized in SANCTIONED_COUNTRIES:
        result.block(f"sanctioned_country:{country}")
        result.details["sanctioned_country"] = country
        logger.warning("COMPLIANCE BLOCK: Sanctioned country %s", country)

    elif normalized in HIGH_RISK_JURISDICTIONS:
        result.flag(f"high_risk_jurisdiction:{country}", "high")
        result.details["high_risk_jurisdiction"] = country

    return result


def screen_transaction_amount(
    amount_usd: float,
    merchant_id: str,
    db: Session,
) -> ComplianceResult:
    """Check transaction thresholds for CTR / SAR reporting."""
    result = ComplianceResult()

    # Currency Transaction Report threshold (>$10k)
    if amount_usd >= settings.AML_THRESHOLD_USD:
        result.flag("ctr_threshold_exceeded", "high")
        result.details["amount_usd"] = amount_usd
        result.details["threshold"] = settings.AML_THRESHOLD_USD
        logger.info(
            "CTR threshold: $%.2f for merchant %s", amount_usd, merchant_id
        )

    # Enhanced Due Diligence threshold
    elif amount_usd >= settings.AML_HIGH_RISK_THRESHOLD_USD:
        result.flag("edd_threshold", "medium")

    # Structuring detection — multiple txns just below threshold in 24h
    window_start = datetime.utcnow() - timedelta(hours=24)
    recent_total = (
        db.query(func.sum(PaymentSession.amount_fiat))
        .filter(
            PaymentSession.merchant_id == merchant_id,
            PaymentSession.created_at >= window_start,
            PaymentSession.status.in_([
                PaymentStatus.PAID,
                PaymentStatus.CONFIRMED,
                PaymentStatus.PENDING,
                PaymentStatus.PROCESSING,
            ]),
        )
        .scalar()
    )
    if recent_total and float(recent_total) + amount_usd >= settings.AML_THRESHOLD_USD * 0.8:
        result.flag("potential_structuring", "high")
        result.details["24h_cumulative"] = float(recent_total) + amount_usd

    return result


def velocity_check(
    merchant_id: str,
    payer_email: Optional[str],
    client_ip: Optional[str],
    db: Session,
) -> ComplianceResult:
    """Detect suspicious velocity patterns."""
    result = ComplianceResult()
    window = datetime.utcnow() - timedelta(hours=1)

    # Merchant velocity: >50 transactions in 1 hour
    merchant_count = (
        db.query(func.count(PaymentSession.id))
        .filter(
            PaymentSession.merchant_id == merchant_id,
            PaymentSession.created_at >= window,
        )
        .scalar()
    )
    if merchant_count and merchant_count > 50:
        result.flag("high_velocity_merchant", "high")
        result.details["merchant_txn_1h"] = merchant_count

    # Same payer email: >10 transactions in 1 hour
    if payer_email:
        email_count = (
            db.query(func.count(PaymentSession.id))
            .filter(
                PaymentSession.payer_email == payer_email,
                PaymentSession.created_at >= window,
            )
            .scalar()
        )
        if email_count and email_count > 10:
            result.flag("high_velocity_payer", "high")
            result.details["payer_txn_1h"] = email_count

    return result


def screen_wallet_address(wallet_address: Optional[str]) -> ComplianceResult:
    """Screen a wallet address against known sanctioned patterns."""
    result = ComplianceResult()
    if not wallet_address:
        return result

    for prefix in SANCTIONED_WALLET_PREFIXES:
        if wallet_address.lower().startswith(prefix.lower()):
            result.block(f"sanctioned_wallet_prefix:{prefix}")
            break

    return result


# ── Aggregate screening ──

def run_compliance_screening(
    session: PaymentSession,
    db: Session,
    *,
    client_ip: Optional[str] = None,
) -> ComplianceResult:
    """
    Run all compliance checks for a payment session.

    Returns a merged ComplianceResult.  Results are also persisted
    to the compliance_screenings table.
    """
    if not settings.AML_ENABLED:
        return ComplianceResult()

    final = ComplianceResult()

    # 1. Country screening (payer + merchant)
    for label, country in [
        ("payer", getattr(session, "payer_country", None)),
        ("merchant", getattr(session.merchant, "country", None) if session.merchant else None),
    ]:
        cr = screen_country(country)
        _merge(final, cr)

    # 2. Amount thresholds
    amount_usd = float(session.amount_fiat) if session.amount_fiat else 0
    cr = screen_transaction_amount(amount_usd, str(session.merchant_id), db)
    _merge(final, cr)

    # 3. Velocity
    cr = velocity_check(
        str(session.merchant_id),
        session.payer_email,
        client_ip,
        db,
    )
    _merge(final, cr)

    # 4. Wallet screening
    cr = screen_wallet_address(session.merchant_wallet or session.deposit_address)
    _merge(final, cr)

    # Persist screening result
    screening = ComplianceScreening(
        session_id=session.id,
        merchant_id=session.merchant_id,
        screening_type="full_screening",
        result="block" if final.blocked else ("flag" if final.flags else "pass"),
        risk_level=final.risk_level,
        entity_type="payment_session",
        entity_value=session.id,
        country=session.payer_country,
        details={
            "flags": final.flags,
            "risk_level": final.risk_level,
            **final.details,
        },
    )
    db.add(screening)
    db.flush()

    return final


def _merge(target: ComplianceResult, source: ComplianceResult):
    """Merge source screening results into target."""
    target.flags.extend(source.flags)
    target.details.update(source.details)
    if source.blocked:
        target.blocked = True
        target.passed = False
    if not source.passed:
        target.passed = False
    if _severity_rank(source.risk_level) > _severity_rank(target.risk_level):
        target.risk_level = source.risk_level
