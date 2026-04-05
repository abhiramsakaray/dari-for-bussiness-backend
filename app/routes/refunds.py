"""
Refunds API Routes
Process refunds for completed payments

Handles:
- Full and partial refunds
- Wallet balance checking before processing
- Settlement status detection (in-platform vs settled to external wallet/bank)
- Queued refunds when merchant has insufficient funds
- Force refund via external wallet when platform balance is low
"""
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, status
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
import secrets
import uuid
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, List

from app.core.database import get_db
from app.core import require_merchant
from app.models.models import (
    Merchant, Refund, PaymentSession, PaymentStatus, Withdrawal,
    RefundStatus as DBRefundStatus
)
from app.schemas.schemas import (
    RefundCreate, RefundResponse, RefundList, RefundStatus, RefundEligibility
)

router = APIRouter(prefix="/refunds", tags=["Refunds"])
logger = logging.getLogger(__name__)

# How long a queued refund stays before auto-cancellation (7 days)
QUEUED_REFUND_EXPIRY_DAYS = 7

# Token → Merchant balance column mapping
BALANCE_COLUMNS = {
    "USDC": "balance_usdc",
    "USDT": "balance_usdt",
    "PYUSD": "balance_pyusd",
}


def generate_refund_id() -> str:
    """Generate a unique refund ID"""
    return f"ref_{secrets.token_urlsafe(12)}"


def _get_merchant_balance(merchant: Merchant, token: str) -> Decimal:
    """Get the merchant's platform balance for a given token."""
    col = BALANCE_COLUMNS.get(token.upper())
    if not col:
        return Decimal("0")
    return Decimal(str(getattr(merchant, col, 0) or 0))


def _get_pending_withdrawals(db: Session, merchant_id, token: str) -> Decimal:
    """Get total pending/processing withdrawals for a token."""
    result = db.query(func.coalesce(func.sum(Withdrawal.amount), 0)).filter(
        Withdrawal.merchant_id == merchant_id,
        Withdrawal.token == token.upper(),
        Withdrawal.status.in_(["pending", "processing"]),
    ).scalar()
    return Decimal(str(result))


def _get_settlement_status(db: Session, merchant: Merchant, token: str) -> str:
    """
    Determine where the merchant's funds currently are:
    - in_platform: All funds still in Dari platform balance
    - settled_external: Funds have been withdrawn to external wallet/bank
    - partially_settled: Some funds withdrawn, some still in platform
    """
    balance = _get_merchant_balance(merchant, token)
    
    # Check if merchant has made any completed withdrawals
    completed_withdrawals = db.query(func.coalesce(func.sum(Withdrawal.amount), 0)).filter(
        Withdrawal.merchant_id == merchant.id,
        Withdrawal.token == token.upper(),
        Withdrawal.status == "completed",
    ).scalar()
    completed_withdrawals = Decimal(str(completed_withdrawals))
    
    if completed_withdrawals == 0:
        return "in_platform"
    elif balance <= 0:
        return "settled_external"
    else:
        return "partially_settled"


@router.get("/eligibility/{payment_session_id}", response_model=RefundEligibility)
async def check_refund_eligibility(
    payment_session_id: str,
    amount: Optional[Decimal] = Query(None, description="Refund amount to check (full refund if omitted)"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant)
):
    """
    Check if a refund can be issued for a payment.
    
    Returns detailed info about:
    - Whether sufficient platform balance exists
    - Settlement status (are funds still in platform or withdrawn?)
    - Available options (queue, force external wallet)
    """
    merchant_uuid = uuid.UUID(current_user["id"])
    merchant = db.query(Merchant).filter(Merchant.id == merchant_uuid).first()
    
    payment = db.query(PaymentSession).filter(
        and_(
            PaymentSession.id == payment_session_id,
            PaymentSession.merchant_id == merchant_uuid
        )
    ).first()
    
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    
    # Calculate already refunded
    existing_refunds = db.query(Refund).filter(
        and_(
            Refund.payment_session_id == payment.id,
            Refund.status.in_([
                DBRefundStatus.PENDING, DBRefundStatus.PROCESSING,
                DBRefundStatus.COMPLETED, DBRefundStatus.QUEUED
            ])
        )
    ).all()
    total_refunded = sum(Decimal(str(r.amount)) for r in existing_refunds)
    
    # Use amount_token (the crypto amount) for refund calculations
    payment_amount = Decimal(str(payment.amount_token or payment.amount_usdc or 0))
    max_refundable = payment_amount - total_refunded
    
    refund_amount = amount if amount else max_refundable
    
    # Check basic eligibility
    if payment.status not in [PaymentStatus.PAID, PaymentStatus.PARTIALLY_REFUNDED]:
        return RefundEligibility(
            eligible=False,
            payment_session_id=payment_session_id,
            max_refundable=max_refundable,
            already_refunded=total_refunded,
            merchant_balance=Decimal("0"),
            sufficient_balance=False,
            settlement_status="unknown",
            message=f"Cannot refund payment with status: {payment.status.value}"
        )
    
    if max_refundable <= 0:
        return RefundEligibility(
            eligible=False,
            payment_session_id=payment_session_id,
            max_refundable=Decimal("0"),
            already_refunded=total_refunded,
            merchant_balance=Decimal("0"),
            sufficient_balance=False,
            settlement_status="unknown",
            message="Payment has already been fully refunded"
        )
    
    token = payment.token or "USDC"
    balance = _get_merchant_balance(merchant, token)
    pending_withdrawals = _get_pending_withdrawals(db, merchant.id, token)
    available_balance = balance - pending_withdrawals
    settlement = _get_settlement_status(db, merchant, token)
    sufficient = available_balance >= refund_amount
    
    if sufficient:
        message = "Refund can be processed from platform balance"
    elif settlement == "settled_external":
        message = "Funds have been withdrawn to external wallet. Use force=true to refund from external wallet, or queue_if_insufficient=true to queue until funds are deposited."
    elif settlement == "partially_settled":
        message = f"Insufficient platform balance ({available_balance} {token} available, {refund_amount} {token} needed). Some funds have been withdrawn. Use force=true or queue_if_insufficient=true."
    else:
        message = f"Insufficient platform balance ({available_balance} {token} available, {refund_amount} {token} needed). Use queue_if_insufficient=true to queue until funds are available."
    
    return RefundEligibility(
        eligible=sufficient or True,  # Can always attempt with force/queue
        payment_session_id=payment_session_id,
        max_refundable=max_refundable,
        already_refunded=total_refunded,
        merchant_balance=available_balance,
        sufficient_balance=sufficient,
        settlement_status=settlement,
        message=message,
        can_queue=not sufficient,
        can_force_external=not sufficient and settlement in ["settled_external", "partially_settled"]
    )


@router.post("", response_model=RefundResponse)
async def create_refund(
    refund_data: RefundCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant)
):
    """
    Create a refund for a completed payment.
    
    Refunds can be:
    - **Full refund**: Returns entire payment amount
    - **Partial refund**: Returns specified amount
    
    **Balance handling:**
    - If merchant has sufficient platform balance → refund is processed immediately
    - If insufficient balance and `queue_if_insufficient=true` → refund is queued (auto-expires in 7 days)
    - If insufficient balance and `force=true` → refund marked for external wallet processing
    - If insufficient balance with neither flag → returns error with balance details
    
    The refund will be processed asynchronously and sent to the customer's
    provided wallet address.
    """
    merchant_uuid = uuid.UUID(current_user["id"])
    merchant = db.query(Merchant).filter(Merchant.id == merchant_uuid).first()
    
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")
    
    # Find the payment session
    payment = db.query(PaymentSession).filter(
        and_(
            PaymentSession.id == refund_data.payment_session_id,
            PaymentSession.merchant_id == merchant_uuid
        )
    ).first()
    
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    
    # Verify payment was successful
    if payment.status not in [PaymentStatus.PAID, PaymentStatus.PARTIALLY_REFUNDED]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot refund payment with status: {payment.status.value}"
        )
    
    # Check if already fully refunded
    existing_refunds = db.query(Refund).filter(
        and_(
            Refund.payment_session_id == payment.id,
            Refund.status.in_([
                DBRefundStatus.PENDING, DBRefundStatus.PROCESSING,
                DBRefundStatus.COMPLETED, DBRefundStatus.QUEUED
            ])
        )
    ).all()
    
    total_refunded = sum(Decimal(str(r.amount)) for r in existing_refunds)
    payment_amount = Decimal(str(payment.amount_token or payment.amount_usdc or 0))
    
    # Determine refund amount
    if refund_data.amount:
        refund_amount = refund_data.amount
    else:
        # Full refund
        refund_amount = payment_amount - total_refunded
    
    if refund_amount <= 0:
        raise HTTPException(
            status_code=400,
            detail="Payment has already been fully refunded"
        )
    
    if refund_amount > (payment_amount - total_refunded):
        raise HTTPException(
            status_code=400,
            detail=f"Refund amount exceeds available balance. Max refundable: {payment_amount - total_refunded}"
        )
    
    # Validate we have token and chain info
    if not payment.token or not payment.chain:
        raise HTTPException(
            status_code=400,
            detail="Payment missing token or chain information"
        )
    
    token = payment.token
    
    # ── Check merchant's platform balance ──
    balance = _get_merchant_balance(merchant, token)
    pending_withdrawals = _get_pending_withdrawals(db, merchant.id, token)
    available_balance = balance - pending_withdrawals
    settlement = _get_settlement_status(db, merchant, token)
    
    refund_id = generate_refund_id()
    refund_status = DBRefundStatus.PENDING
    refund_source = "platform_balance"
    failure_reason = None
    queued_until = None
    
    if available_balance < refund_amount:
        # Insufficient funds scenario
        if refund_data.queue_if_insufficient:
            # Queue the refund — will be processed when balance is available
            refund_status = DBRefundStatus.QUEUED
            queued_until = datetime.utcnow() + timedelta(days=QUEUED_REFUND_EXPIRY_DAYS)
            logger.info(
                f"Refund {refund_id} queued due to insufficient funds. "
                f"Available: {available_balance} {token}, Needed: {refund_amount} {token}. "
                f"Queued until: {queued_until.isoformat()}"
            )
        elif refund_data.force:
            # Force refund from external wallet
            refund_source = "external_wallet"
            refund_status = DBRefundStatus.PENDING
            logger.info(
                f"Refund {refund_id} forced via external wallet. "
                f"Settlement status: {settlement}"
            )
        else:
            # Reject with detailed error
            detail = (
                f"Insufficient platform balance to process refund. "
                f"Available: {available_balance} {token}, Needed: {refund_amount} {token}. "
                f"Settlement status: {settlement}. "
            )
            if settlement in ["settled_external", "partially_settled"]:
                detail += (
                    "Funds have been withdrawn to external wallet. "
                    "Options: (1) Set force=true to process from external wallet, "
                    "(2) Set queue_if_insufficient=true to queue until funds are deposited, "
                    "(3) Deposit funds back to platform first."
                )
            else:
                detail += (
                    "Options: (1) Set queue_if_insufficient=true to queue until funds are available, "
                    "(2) Deposit more funds to your platform balance."
                )
            raise HTTPException(status_code=400, detail=detail)
    
    refund = Refund(
        id=refund_id,
        payment_session_id=payment.id,
        merchant_id=merchant_uuid,
        amount=refund_amount,
        token=payment.token,
        chain=payment.chain,
        refund_address=refund_data.refund_address,
        status=refund_status,
        reason=refund_data.reason,
        refund_source=refund_source,
        merchant_balance_at_request=available_balance,
        settlement_status=settlement,
        insufficient_funds_at=datetime.utcnow() if available_balance < refund_amount else None,
        queued_until=queued_until,
        failure_reason=failure_reason
    )
    
    db.add(refund)
    
    # Only update payment status for non-queued refunds
    if refund_status != DBRefundStatus.QUEUED:
        remaining = payment_amount - total_refunded - refund_amount
        if remaining <= 0:
            payment.status = PaymentStatus.REFUNDED
        else:
            payment.status = PaymentStatus.PARTIALLY_REFUNDED
        
        # Deduct from merchant balance if using platform balance
        if refund_source == "platform_balance" and available_balance >= refund_amount:
            col = BALANCE_COLUMNS.get(token.upper())
            if col:
                current_bal = Decimal(str(getattr(merchant, col, 0) or 0))
                setattr(merchant, col, current_bal - refund_amount)
    
    db.commit()
    db.refresh(refund)
    
    # TODO: Process refund in background (send crypto on-chain)
    # background_tasks.add_task(process_refund, refund.id)
    
    return build_refund_response(refund)


@router.get("", response_model=RefundList)
async def list_refunds(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    refund_status: Optional[RefundStatus] = Query(None, alias="status"),
    payment_session_id: Optional[str] = None,
    current_user: dict = Depends(require_merchant),
    db: Session = Depends(get_db)
):
    """
    List all refunds for the merchant.
    
    Supports filtering by status and payment session.
    """
    try:
        merchant_uuid = uuid.UUID(current_user["id"])
        logger.info(f"Fetching refunds for merchant {merchant_uuid}, page={page}, page_size={page_size}, status={status}")
        
        # Filter by merchant_id for security
        query = db.query(Refund).filter(Refund.merchant_id == merchant_uuid)
        
        if refund_status:
            query = query.filter(Refund.status == refund_status.value)
        
        if payment_session_id:
            query = query.filter(Refund.payment_session_id == payment_session_id)
        
        total = query.count()
        
        refunds = query.order_by(Refund.created_at.desc())\
            .offset((page - 1) * page_size)\
            .limit(page_size)\
            .all()
        
        refund_list = [build_refund_response(r) for r in refunds]
        
        logger.info(f"Found {len(refund_list)} refunds (total: {total}) for merchant {merchant_uuid}")
        
        return RefundList(
            refunds=refund_list,
            total=total
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching refunds: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch refunds: {str(e)}"
        )


@router.get("/{refund_id}", response_model=RefundResponse)
async def get_refund(
    refund_id: str,
    current_user: dict = Depends(require_merchant),
    db: Session = Depends(get_db)
):
    """Get a specific refund by ID."""
    # Filter by merchant_id for security
    refund = db.query(Refund).filter(
        and_(
            Refund.id == refund_id,
            Refund.merchant_id == uuid.UUID(current_user["id"])
        )
    ).first()
    
    if not refund:
        raise HTTPException(status_code=404, detail="Refund not found")
    
    return build_refund_response(refund)


@router.post("/{refund_id}/cancel")
async def cancel_refund(
    refund_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant)
):
    """
    Cancel a pending or queued refund.
    
    Can only cancel refunds that haven't started processing.
    """
    refund = db.query(Refund).filter(
        and_(
            Refund.id == refund_id,
            Refund.merchant_id == uuid.UUID(current_user["id"])
        )
    ).first()
    
    if not refund:
        raise HTTPException(status_code=404, detail="Refund not found")
    
    if refund.status not in [DBRefundStatus.PENDING, DBRefundStatus.QUEUED, DBRefundStatus.INSUFFICIENT_FUNDS]:
        raise HTTPException(
            status_code=400,
            detail="Can only cancel pending, queued, or insufficient_funds refunds"
        )
    
    refund.status = DBRefundStatus.FAILED
    db.commit()
    
    # Revert payment status if needed
    payment = db.query(PaymentSession).filter(
        PaymentSession.id == refund.payment_session_id
    ).first()
    
    if payment and payment.status in [PaymentStatus.REFUNDED, PaymentStatus.PARTIALLY_REFUNDED]:
        # Check if there are other successful refunds
        other_refunds = db.query(Refund).filter(
            and_(
                Refund.payment_session_id == payment.id,
                Refund.id != refund.id,
                Refund.status == DBRefundStatus.COMPLETED
            )
        ).first()
        
        if other_refunds:
            payment.status = PaymentStatus.PARTIALLY_REFUNDED
        else:
            payment.status = PaymentStatus.PAID
        
        db.commit()
    
    return {"message": "Refund cancelled", "id": refund_id}


@router.post("/{refund_id}/retry")
async def retry_refund(
    refund_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant)
):
    """
    Retry a failed or queued refund.
    
    Re-checks merchant balance before attempting. If the refund was queued
    and balance is now sufficient, it will be promoted to pending.
    """
    merchant_uuid = uuid.UUID(current_user["id"])
    merchant = db.query(Merchant).filter(Merchant.id == merchant_uuid).first()
    
    refund = db.query(Refund).filter(
        and_(
            Refund.id == refund_id,
            Refund.merchant_id == merchant_uuid
        )
    ).first()
    
    if not refund:
        raise HTTPException(status_code=404, detail="Refund not found")
    
    if refund.status not in [DBRefundStatus.FAILED, DBRefundStatus.QUEUED, DBRefundStatus.INSUFFICIENT_FUNDS]:
        raise HTTPException(
            status_code=400,
            detail="Can only retry failed, queued, or insufficient_funds refunds"
        )
    
    # Re-check balance for platform_balance refunds
    if refund.refund_source == "platform_balance":
        balance = _get_merchant_balance(merchant, refund.token)
        pending_withdrawals = _get_pending_withdrawals(db, merchant.id, refund.token)
        available = balance - pending_withdrawals
        
        if available < Decimal(str(refund.amount)):
            raise HTTPException(
                status_code=400,
                detail=f"Still insufficient balance. Available: {available} {refund.token}, Needed: {refund.amount} {refund.token}"
            )
        
        # Deduct balance
        col = BALANCE_COLUMNS.get(refund.token.upper())
        if col:
            current_bal = Decimal(str(getattr(merchant, col, 0) or 0))
            setattr(merchant, col, current_bal - Decimal(str(refund.amount)))
    
    refund.status = DBRefundStatus.PENDING
    refund.failure_reason = None
    
    # Update payment status
    payment = db.query(PaymentSession).filter(
        PaymentSession.id == refund.payment_session_id
    ).first()
    if payment:
        payment_amount = Decimal(str(payment.amount_token or payment.amount_usdc or 0))
        existing_refunds = db.query(Refund).filter(
            and_(
                Refund.payment_session_id == payment.id,
                Refund.status.in_([DBRefundStatus.PENDING, DBRefundStatus.PROCESSING, DBRefundStatus.COMPLETED]),
                Refund.id != refund.id
            )
        ).all()
        total_refunded = sum(Decimal(str(r.amount)) for r in existing_refunds) + Decimal(str(refund.amount))
        if total_refunded >= payment_amount:
            payment.status = PaymentStatus.REFUNDED
        else:
            payment.status = PaymentStatus.PARTIALLY_REFUNDED
    
    db.commit()
    
    # TODO: Process refund in background
    # background_tasks.add_task(process_refund, refund.id)
    
    return {"message": "Refund queued for retry", "id": refund_id}


@router.post("/process-queued")
async def process_queued_refunds(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant)
):
    """
    Attempt to process all queued refunds for this merchant.
    
    Checks current balance and processes any queued refunds that can now
    be fulfilled. Expired queued refunds are automatically cancelled.
    """
    merchant_uuid = uuid.UUID(current_user["id"])
    merchant = db.query(Merchant).filter(Merchant.id == merchant_uuid).first()
    
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")
    
    # Get all queued refunds
    queued_refunds = db.query(Refund).filter(
        and_(
            Refund.merchant_id == merchant_uuid,
            Refund.status == DBRefundStatus.QUEUED
        )
    ).order_by(Refund.created_at.asc()).all()
    
    if not queued_refunds:
        return {"message": "No queued refunds", "processed": 0, "expired": 0}
    
    processed = 0
    expired = 0
    still_queued = 0
    now = datetime.utcnow()
    
    for refund in queued_refunds:
        # Check if expired
        if refund.queued_until and refund.queued_until < now:
            refund.status = DBRefundStatus.FAILED
            refund.failure_reason = "Queued refund expired — merchant did not deposit sufficient funds"
            expired += 1
            continue
        
        # Check balance
        token = refund.token
        balance = _get_merchant_balance(merchant, token)
        pending_withdrawals = _get_pending_withdrawals(db, merchant.id, token)
        available = balance - pending_withdrawals
        
        if available >= Decimal(str(refund.amount)):
            # Promote to pending
            refund.status = DBRefundStatus.PENDING
            refund.failure_reason = None
            
            # Deduct from balance
            col = BALANCE_COLUMNS.get(token.upper())
            if col:
                current_bal = Decimal(str(getattr(merchant, col, 0) or 0))
                setattr(merchant, col, current_bal - Decimal(str(refund.amount)))
            
            # Update payment status
            payment = db.query(PaymentSession).filter(
                PaymentSession.id == refund.payment_session_id
            ).first()
            if payment:
                payment_amount = Decimal(str(payment.amount_token or payment.amount_usdc or 0))
                all_refunds = db.query(Refund).filter(
                    and_(
                        Refund.payment_session_id == payment.id,
                        Refund.status.in_([DBRefundStatus.PENDING, DBRefundStatus.PROCESSING, DBRefundStatus.COMPLETED])
                    )
                ).all()
                total_refunded = sum(Decimal(str(r.amount)) for r in all_refunds) + Decimal(str(refund.amount))
                if total_refunded >= payment_amount:
                    payment.status = PaymentStatus.REFUNDED
                else:
                    payment.status = PaymentStatus.PARTIALLY_REFUNDED
            
            processed += 1
            # TODO: background_tasks.add_task(process_refund, refund.id)
        else:
            still_queued += 1
    
    db.commit()
    
    return {
        "message": f"Processed {processed} queued refunds",
        "processed": processed,
        "expired": expired,
        "still_queued": still_queued
    }


def build_refund_response(refund: Refund) -> RefundResponse:
    """Build RefundResponse from model"""
    return RefundResponse(
        id=refund.id,
        payment_session_id=refund.payment_session_id,
        amount=refund.amount,
        token=refund.token,
        chain=refund.chain,
        refund_address=refund.refund_address,
        status=refund.status.value if hasattr(refund.status, 'value') else refund.status,
        tx_hash=refund.tx_hash,
        reason=refund.reason,
        refund_source=refund.refund_source,
        settlement_status=refund.settlement_status,
        merchant_balance_at_request=refund.merchant_balance_at_request,
        failure_reason=refund.failure_reason,
        queued_until=refund.queued_until,
        created_at=refund.created_at,
        processed_at=refund.processed_at,
        completed_at=refund.completed_at
    )
