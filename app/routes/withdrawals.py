"""
Withdrawal Routes

Endpoints for merchants to withdraw funds to external wallets.
Supports all chains (Stellar, Ethereum, Polygon, Base, Tron) and tokens (USDC, USDT, PYUSD).
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Optional
import logging

from app.core import get_db, require_merchant
from app.models import Merchant, Withdrawal, WithdrawalLimit, MerchantWallet
from app.schemas import (
    WithdrawalRequest,
    WithdrawalResponse,
    WithdrawalListResponse,
    WithdrawalBalanceResponse,
    WithdrawalBalanceItem,
    WithdrawalLimitInfo,
    LocalCurrencyAmount,
)
from app.services.currency_service import get_currency_for_country, build_local_amount

router = APIRouter(prefix="/withdrawals", tags=["Withdrawals"])
logger = logging.getLogger(__name__)

SUPPORTED_TOKENS = {"USDC", "USDT", "PYUSD"}
SUPPORTED_CHAINS = {"stellar", "ethereum", "polygon", "base", "tron"}

# Token → Merchant balance column mapping
BALANCE_COLUMNS = {
    "USDC": "balance_usdc",
    "USDT": "balance_usdt",
    "PYUSD": "balance_pyusd",
}


def _withdrawal_to_response(w: Withdrawal, local: dict = None) -> WithdrawalResponse:
    """Convert a Withdrawal model to response schema with optional local currency."""
    resp = WithdrawalResponse(
        id=str(w.id),
        merchant_id=str(w.merchant_id),
        amount=float(w.amount),
        token=w.token,
        chain=w.chain,
        destination_address=w.destination_address,
        destination_memo=w.destination_memo,
        status=w.status,
        tx_hash=w.tx_hash,
        network_fee=float(w.network_fee) if w.network_fee else None,
        platform_fee=float(w.platform_fee) if w.platform_fee else None,
        submitted_at=w.submitted_at,
        confirmed_at=w.confirmed_at,
        failed_reason=w.failed_reason,
        notes=w.notes,
        created_at=w.created_at,
        updated_at=w.updated_at,
    )
    if local:
        resp.amount_local = LocalCurrencyAmount(**local["amount"]) if local.get("amount") else None
        resp.fee_local = LocalCurrencyAmount(**local["fee"]) if local.get("fee") else None
    return resp


async def _build_withdrawal_local(w: Withdrawal, currency_code: str, currency_symbol: str) -> dict:
    """Build local currency dicts for a withdrawal."""
    amount_local = await build_local_amount(float(w.amount), currency_code, currency_symbol)
    fee_val = float(w.platform_fee) if w.platform_fee else 0.0
    fee_local = await build_local_amount(fee_val, currency_code, currency_symbol) if fee_val > 0 else None
    return {"amount": amount_local, "fee": fee_local}


def _get_merchant_balance(merchant: Merchant, token: str) -> Decimal:
    """Get the merchant's balance for a given token."""
    col = BALANCE_COLUMNS.get(token.upper())
    if not col:
        return Decimal("0")
    return getattr(merchant, col, Decimal("0")) or Decimal("0")


def _get_pending_amount(db: Session, merchant_id, token: str) -> Decimal:
    """Sum of pending/processing withdrawals for a token."""
    result = db.query(func.coalesce(func.sum(Withdrawal.amount), 0)).filter(
        Withdrawal.merchant_id == merchant_id,
        Withdrawal.token == token.upper(),
        Withdrawal.status.in_(["pending", "processing"]),
    ).scalar()
    return Decimal(str(result))


@router.get("/balance", response_model=WithdrawalBalanceResponse)
async def get_withdrawal_balance(
    current_user: dict = Depends(require_merchant),
    db: Session = Depends(get_db),
):
    """
    Get available balances for withdrawal.
    
    Shows current balance, pending withdrawal amounts, and net available for each token.
    All amounts returned in both USDC and merchant's local currency.
    """
    merchant = db.query(Merchant).filter(Merchant.id == current_user["id"]).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    currency_code, currency_symbol, _ = get_currency_for_country(merchant.country)

    balances = []
    total_usd = 0.0

    for token in SUPPORTED_TOKENS:
        available = float(_get_merchant_balance(merchant, token))
        pending = float(_get_pending_amount(db, merchant.id, token))
        net = max(available - pending, 0.0)
        total_usd += net

        avail_local = await build_local_amount(available, currency_code, currency_symbol)
        net_local = await build_local_amount(net, currency_code, currency_symbol)

        balances.append(WithdrawalBalanceItem(
            token=token,
            available=available,
            pending_withdrawals=pending,
            net_available=net,
            available_local=LocalCurrencyAmount(**avail_local),
            net_available_local=LocalCurrencyAmount(**net_local),
        ))

    total_local = await build_local_amount(total_usd, currency_code, currency_symbol)

    return WithdrawalBalanceResponse(
        balances=balances,
        total_available_usd=total_usd,
        total_available_local=LocalCurrencyAmount(**total_local),
        local_currency=currency_code,
        local_symbol=currency_symbol,
    )


@router.get("/limits", response_model=WithdrawalLimitInfo)
async def get_withdrawal_limits(
    current_user: dict = Depends(require_merchant),
    db: Session = Depends(get_db),
):
    """
    Get withdrawal limits based on the merchant's subscription tier.
    
    Includes daily limits, fees, cooldown, and current daily usage.
    """
    merchant = db.query(Merchant).filter(Merchant.id == current_user["id"]).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    currency_code, currency_symbol, _ = get_currency_for_country(merchant.country)
    tier = merchant.subscription_tier or "free"
    limits = db.query(WithdrawalLimit).filter(WithdrawalLimit.tier == tier).first()

    # Fallback defaults if no limit row
    if not limits:
        limits_data = {
            "daily_limit": 100.0,
            "min_withdrawal": 5.0,
            "max_per_transaction": 50.0,
            "withdrawal_fee_percent": 1.0,
            "withdrawal_fee_flat": 1.0,
            "cooldown_minutes": 60,
            "requires_2fa": False,
        }
    else:
        limits_data = {
            "daily_limit": float(limits.daily_limit),
            "min_withdrawal": float(limits.min_withdrawal),
            "max_per_transaction": float(limits.max_per_transaction),
            "withdrawal_fee_percent": float(limits.withdrawal_fee_percent),
            "withdrawal_fee_flat": float(limits.withdrawal_fee_flat),
            "cooldown_minutes": limits.cooldown_minutes,
            "requires_2fa": limits.requires_2fa,
        }

    # Calculate daily usage
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    daily_used = float(
        db.query(func.coalesce(func.sum(Withdrawal.amount), 0)).filter(
            Withdrawal.merchant_id == merchant.id,
            Withdrawal.status.in_(["pending", "processing", "completed"]),
            Withdrawal.created_at >= today_start,
        ).scalar()
    )

    return WithdrawalLimitInfo(
        tier=tier,
        daily_used=daily_used,
        daily_remaining=max(limits_data["daily_limit"] - daily_used, 0.0),
        daily_limit_local=LocalCurrencyAmount(**(await build_local_amount(limits_data["daily_limit"], currency_code, currency_symbol))),
        daily_used_local=LocalCurrencyAmount(**(await build_local_amount(daily_used, currency_code, currency_symbol))),
        daily_remaining_local=LocalCurrencyAmount(**(await build_local_amount(max(limits_data["daily_limit"] - daily_used, 0.0), currency_code, currency_symbol))),
        **limits_data,
    )


@router.post("", response_model=WithdrawalResponse, status_code=status.HTTP_201_CREATED)
async def create_withdrawal(
    request_body: WithdrawalRequest,
    request: Request,
    current_user: dict = Depends(require_merchant),
    db: Session = Depends(get_db),
):
    """
    Create a new withdrawal request.
    
    Validates balance, limits, cooldown, and destination wallet before creating.
    The withdrawal will be processed asynchronously.
    """
    merchant = db.query(Merchant).filter(Merchant.id == current_user["id"]).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    token = request_body.token.upper()
    chain = request_body.chain.lower()
    amount = Decimal(str(request_body.amount))

    # --- Validate token & chain ---
    if token not in SUPPORTED_TOKENS:
        raise HTTPException(status_code=400, detail=f"Unsupported token: {token}. Supported: {', '.join(SUPPORTED_TOKENS)}")
    if chain not in SUPPORTED_CHAINS:
        raise HTTPException(status_code=400, detail=f"Unsupported chain: {chain}. Supported: {', '.join(SUPPORTED_CHAINS)}")

    # --- Validate destination address ---
    dest = request_body.destination_address.strip()
    if not dest:
        raise HTTPException(status_code=400, detail="Destination address is required")

    # --- Get limits ---
    tier = merchant.subscription_tier or "free"
    limits = db.query(WithdrawalLimit).filter(WithdrawalLimit.tier == tier).first()
    min_withdrawal = Decimal(str(limits.min_withdrawal)) if limits else Decimal("5")
    max_per_tx = Decimal(str(limits.max_per_transaction)) if limits else Decimal("50")
    daily_limit = Decimal(str(limits.daily_limit)) if limits else Decimal("100")
    fee_percent = Decimal(str(limits.withdrawal_fee_percent)) if limits else Decimal("1")
    fee_flat = Decimal(str(limits.withdrawal_fee_flat)) if limits else Decimal("1")
    cooldown = limits.cooldown_minutes if limits else 60

    # --- Amount limits ---
    if amount < min_withdrawal:
        raise HTTPException(status_code=400, detail=f"Minimum withdrawal is {min_withdrawal} {token}")
    if amount > max_per_tx:
        raise HTTPException(status_code=400, detail=f"Maximum per transaction is {max_per_tx} {token}")

    # --- Daily limit check ---
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    daily_used = Decimal(str(
        db.query(func.coalesce(func.sum(Withdrawal.amount), 0)).filter(
            Withdrawal.merchant_id == merchant.id,
            Withdrawal.status.in_(["pending", "processing", "completed"]),
            Withdrawal.created_at >= today_start,
        ).scalar()
    ))
    if daily_used + amount > daily_limit:
        remaining = max(daily_limit - daily_used, Decimal("0"))
        raise HTTPException(
            status_code=400,
            detail=f"Daily withdrawal limit exceeded. Daily limit: {daily_limit}, Used: {daily_used}, Remaining: {remaining}"
        )

    # --- Cooldown check ---
    if cooldown > 0:
        last_withdrawal = db.query(Withdrawal).filter(
            Withdrawal.merchant_id == merchant.id,
            Withdrawal.status.in_(["pending", "processing", "completed"]),
        ).order_by(Withdrawal.created_at.desc()).first()

        if last_withdrawal:
            cooldown_end = last_withdrawal.created_at + timedelta(minutes=cooldown)
            if datetime.utcnow() < cooldown_end:
                wait = int((cooldown_end - datetime.utcnow()).total_seconds() / 60) + 1
                raise HTTPException(
                    status_code=429,
                    detail=f"Withdrawal cooldown active. Please wait {wait} more minute(s)."
                )

    # --- Balance check ---
    available = _get_merchant_balance(merchant, token)
    pending = _get_pending_amount(db, merchant.id, token)
    net_available = available - pending

    # Calculate platform fee
    platform_fee = (amount * fee_percent / Decimal("100")) + fee_flat
    total_deduction = amount + platform_fee

    if total_deduction > net_available:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient balance. Available: {net_available} {token}, Required (amount + fee): {total_deduction} {token}"
        )

    # --- Create withdrawal ---
    client_ip = request.client.host if request.client else None

    withdrawal = Withdrawal(
        merchant_id=merchant.id,
        amount=amount,
        token=token,
        chain=chain,
        destination_address=dest,
        destination_memo=request_body.destination_memo,
        status="pending",
        platform_fee=platform_fee,
        notes=request_body.notes,
        ip_address=client_ip,
    )

    db.add(withdrawal)
    db.commit()
    db.refresh(withdrawal)

    logger.info(
        f"Withdrawal created: {withdrawal.id} | merchant={merchant.id} | "
        f"{amount} {token} on {chain} → {dest}"
    )

    currency_code, currency_symbol, _ = get_currency_for_country(merchant.country)
    local = await _build_withdrawal_local(withdrawal, currency_code, currency_symbol)
    return _withdrawal_to_response(withdrawal, local=local)


@router.get("", response_model=WithdrawalListResponse)
async def list_withdrawals(
    current_user: dict = Depends(require_merchant),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    chain: Optional[str] = Query(None, description="Filter by chain"),
    token: Optional[str] = Query(None, description="Filter by token"),
):
    """
    List all withdrawals for the current merchant.
    
    Supports pagination and filtering by status, chain, and token.
    All amounts returned in both USDC and merchant's local currency.
    """
    merchant = db.query(Merchant).filter(Merchant.id == current_user["id"]).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    currency_code, currency_symbol, _ = get_currency_for_country(merchant.country)

    query = db.query(Withdrawal).filter(Withdrawal.merchant_id == current_user["id"])

    if status_filter:
        query = query.filter(Withdrawal.status == status_filter.lower())
    if chain:
        query = query.filter(Withdrawal.chain == chain.lower())
    if token:
        query = query.filter(Withdrawal.token == token.upper())

    total = query.count()
    withdrawals = (
        query.order_by(Withdrawal.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    items = []
    for w in withdrawals:
        local = await _build_withdrawal_local(w, currency_code, currency_symbol)
        items.append(_withdrawal_to_response(w, local=local))

    return WithdrawalListResponse(
        withdrawals=items,
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/{withdrawal_id}", response_model=WithdrawalResponse)
async def get_withdrawal(
    withdrawal_id: str,
    current_user: dict = Depends(require_merchant),
    db: Session = Depends(get_db),
):
    """Get details of a specific withdrawal."""
    merchant = db.query(Merchant).filter(Merchant.id == current_user["id"]).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    withdrawal = db.query(Withdrawal).filter(
        Withdrawal.id == withdrawal_id,
        Withdrawal.merchant_id == current_user["id"],
    ).first()

    if not withdrawal:
        raise HTTPException(status_code=404, detail="Withdrawal not found")

    currency_code, currency_symbol, _ = get_currency_for_country(merchant.country)
    local = await _build_withdrawal_local(withdrawal, currency_code, currency_symbol)
    return _withdrawal_to_response(withdrawal, local=local)


@router.post("/{withdrawal_id}/cancel", response_model=WithdrawalResponse)
async def cancel_withdrawal(
    withdrawal_id: str,
    current_user: dict = Depends(require_merchant),
    db: Session = Depends(get_db),
):
    """
    Cancel a pending withdrawal.
    
    Only withdrawals with status 'pending' can be cancelled.
    Processing or completed withdrawals cannot be reversed.
    """
    merchant = db.query(Merchant).filter(Merchant.id == current_user["id"]).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    withdrawal = db.query(Withdrawal).filter(
        Withdrawal.id == withdrawal_id,
        Withdrawal.merchant_id == current_user["id"],
    ).first()

    if not withdrawal:
        raise HTTPException(status_code=404, detail="Withdrawal not found")

    if withdrawal.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel withdrawal with status '{withdrawal.status}'. Only pending withdrawals can be cancelled."
        )

    withdrawal.status = "cancelled"
    withdrawal.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(withdrawal)

    logger.info(f"Withdrawal cancelled: {withdrawal.id} by merchant {current_user['id']}")

    currency_code, currency_symbol, _ = get_currency_for_country(merchant.country)
    local = await _build_withdrawal_local(withdrawal, currency_code, currency_symbol)
    return _withdrawal_to_response(withdrawal, local=local)
