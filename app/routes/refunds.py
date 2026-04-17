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
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, status, Request
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, update
import secrets
import uuid
import logging
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_DOWN
from typing import Optional, List
import asyncio

from app.core.database import get_db
from app.core.security import require_merchant, require_replay_protection
from app.core.audit_logger import AuditLogger
from app.models.models import (
    Merchant, Refund, PaymentSession, PaymentStatus, Withdrawal,
    RefundStatus as DBRefundStatus, Subscription, SubscriptionPayment
)
from app.schemas.schemas import (
    RefundCreate, RefundResponse, RefundList, RefundStatus, RefundEligibility,
    CustomerTransaction, CustomerTransactionList
)
from app.services.refund_processor import process_refund_on_chain, process_all_pending_refunds

router = APIRouter(
    prefix="/refunds", 
    tags=["Refunds"]
)
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


@router.get("/customer/transactions", response_model=CustomerTransactionList)
async def get_customer_transactions(
    email: Optional[str] = Query(None, description="Customer email"),
    phone: Optional[str] = Query(None, description="Customer phone number"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant),
):
    """
    Search customer by email or phone and get all their transactions.
    
    Returns all payments and subscriptions for the customer with refund eligibility info.
    """
    logger.info(f"[ENDPOINT] get_customer_transactions called with email={email}, phone={phone}")
    logger.info(f"[ENDPOINT] current_user={current_user}")
    
    if not email and not phone:
        raise HTTPException(status_code=400, detail="Email or phone number required")
    
    merchant_uuid = uuid.UUID(current_user["id"])
    merchant = db.query(Merchant).filter(Merchant.id == merchant_uuid).first()
    
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")
    
    # Search parameters
    search_email = email.lower() if email else None
    search_phone = phone.lower() if phone else None
    
    transactions = []
    customer_name = None
    total_value = Decimal("0")
    
    # Get payment sessions
    payment_query = db.query(PaymentSession).filter(
        PaymentSession.merchant_id == merchant_uuid
    )
    
    if search_email:
        payment_query = payment_query.filter(
            func.lower(PaymentSession.payer_email) == search_email
        )
    
    payments = payment_query.all()
    
    for payment in payments:
        if payment.payer_email:
            customer_name = payment.payer_name
        
        # Get refund info
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
        refundable = payment_amount - total_refunded if payment.status in [PaymentStatus.PAID, PaymentStatus.PARTIALLY_REFUNDED] else Decimal("0")
        
        transactions.append(CustomerTransaction(
            id=payment.id,
            type=payment.session_metadata.get("type", "payment") if payment.session_metadata else "payment",
            email=payment.payer_email or search_email or "",
            name=payment.payer_name,
            amount_fiat=payment.amount_fiat,
            amount_token=Decimal(str(payment.amount_token or 0)),
            fiat_currency=payment.fiat_currency,
            token=payment.token,
            chain=payment.chain,
            wallet_address=payment.deposit_address or payment.merchant_wallet,
            status=payment.status.value,
            paid_at=payment.paid_at,
            created_at=payment.created_at,
            tx_hash=payment.tx_hash,
            refundable_amount=refundable,
            already_refunded=total_refunded,
            metadata=payment.session_metadata
        ))
        
        total_value += payment.amount_fiat
    
    # Get subscriptions
    sub_query = db.query(Subscription).filter(
        Subscription.merchant_id == merchant_uuid
    )
    
    if search_email:
        sub_query = sub_query.filter(
            func.lower(Subscription.customer_email) == search_email
        )
    
    subscriptions = sub_query.all()
    
    for sub in subscriptions:
        customer_name = sub.customer_name or customer_name
        
        # Get subscription payments for refund info
        sub_payments = db.query(SubscriptionPayment).filter(
            SubscriptionPayment.subscription_id == sub.id,
            SubscriptionPayment.status == PaymentStatus.PAID
        ).all()
        
        for sub_payment in sub_payments:
            # Get refunds for this subscription payment
            existing_refunds = db.query(Refund).filter(
                and_(
                    Refund.id == sub_payment.payment_session_id,
                    Refund.status.in_([
                        DBRefundStatus.PENDING, DBRefundStatus.PROCESSING,
                        DBRefundStatus.COMPLETED, DBRefundStatus.QUEUED
                    ])
                )
            ).all()
            total_refunded = sum(Decimal(str(r.amount)) for r in existing_refunds)
            refundable = sub_payment.amount - total_refunded
            
            transactions.append(CustomerTransaction(
                id=sub_payment.payment_session_id or f"sub_pay_{sub_payment.id}",
                type="subscription_payment",
                email=sub.customer_email,
                name=sub.customer_name,
                amount_fiat=sub_payment.amount,
                amount_token=sub_payment.amount,
                fiat_currency=sub_payment.fiat_currency or "USD",
                token="USDC",
                chain="stellar",
                wallet_address=None,
                status=sub_payment.status.value,
                paid_at=sub_payment.created_at,
                created_at=sub_payment.created_at,
                tx_hash=None,
                refundable_amount=refundable if not total_refunded else Decimal("0"),
                already_refunded=total_refunded,
                metadata={"subscription_id": str(sub.id), "plan_id": str(sub.plan_id)}
            ))
            
            total_value += sub_payment.amount
    
    if not transactions and not search_email:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    # Sort by date descending
    transactions.sort(key=lambda x: x.created_at, reverse=True)
    
    return CustomerTransactionList(
        customer_email=search_email or search_phone or "",
        customer_name=customer_name,
        total_transaction_value=total_value,
        total_transactions=len(transactions),
        transactions=transactions
    )


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
    
    # Determine payment type from metadata
    payment_type = "payment"
    if payment.session_metadata:
        payment_type = payment.session_metadata.get("type", "payment")
    
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
            message=f"Cannot refund payment with status: {payment.status.value}",
            payer_wallet=payment.deposit_address or payment.merchant_wallet,
            payer_email=payment.payer_email,
            payer_name=payment.payer_name,
            amount_fiat=payment.amount_fiat,
            amount_token=Decimal(str(payment.amount_token or 0)),
            fiat_currency=payment.fiat_currency,
            token=payment.token,
            chain=payment.chain,
            payment_type=payment_type,
            created_at=payment.created_at
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
            message="Payment has already been fully refunded",
            payer_wallet=payment.deposit_address or payment.merchant_wallet,
            payer_email=payment.payer_email,
            payer_name=payment.payer_name,
            amount_fiat=payment.amount_fiat,
            amount_token=Decimal(str(payment.amount_token or 0)),
            fiat_currency=payment.fiat_currency,
            token=payment.token,
            chain=payment.chain,
            payment_type=payment_type,
            created_at=payment.created_at
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
        can_force_external=not sufficient and settlement in ["settled_external", "partially_settled"],
        payer_wallet=payment.deposit_address or payment.merchant_wallet,
        payer_email=payment.payer_email,
        payer_name=payment.payer_name,
        amount_fiat=payment.amount_fiat,
        amount_token=Decimal(str(payment.amount_token or 0)),
        fiat_currency=payment.fiat_currency,
        token=payment.token,
        chain=payment.chain,
        payment_type=payment_type,
        created_at=payment.created_at
    )


@router.post("", response_model=RefundResponse)
async def create_refund(
    refund_data: RefundCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant),
    _: bool = Depends(require_replay_protection)
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
        # Audit log: Failed refund attempt
        AuditLogger.log_from_request(
            db, request, current_user,
            action="refund_create_failed",
            resource_type="refund",
            details={"reason": "payment_not_found", "payment_id": refund_data.payment_session_id},
            status="failure"
        )
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
        
        # Atomic balance deduction using SQL UPDATE with WHERE guard
        # This prevents race conditions: the UPDATE only succeeds if
        # balance >= refund_amount at the moment of execution.
        if refund_source == "platform_balance":
            col = BALANCE_COLUMNS.get(token.upper())
            if col:
                balance_column = getattr(Merchant, col)
                result = db.execute(
                    update(Merchant)
                    .where(
                        Merchant.id == merchant_uuid,
                        balance_column >= refund_amount,
                    )
                    .values(**{col: balance_column - refund_amount})
                )
                if result.rowcount == 0:
                    # Another concurrent request drained the balance
                    db.rollback()
                    raise HTTPException(
                        status_code=400,
                        detail="Insufficient funds (concurrent modification detected). Please retry."
                    )
    
    db.commit()
    db.refresh(refund)
    
    # Process refund in background (send crypto on-chain)
    if refund_status != DBRefundStatus.QUEUED:
        background_tasks.add_task(process_refund, refund.id, str(merchant_uuid))
    
    # Audit log: Refund created
    AuditLogger.log_from_request(
        db, request, current_user,
        action="refund_created",
        resource_type="refund",
        resource_id=refund.id,
        details={
            "payment_session_id": payment.id,
            "amount": str(refund_amount),
            "token": token,
            "chain": payment.chain,
            "status": refund_status.value,
            "refund_source": refund_source,
            "queued": refund_status == DBRefundStatus.QUEUED
        },
        status="success"
    )
    
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
        from sqlalchemy.orm import joinedload
        
        merchant_uuid = uuid.UUID(current_user["id"])
        logger.info(f"Fetching refunds for merchant {merchant_uuid}, page={page}, page_size={page_size}, status={refund_status}")
        
        # Filter by merchant_id for security
        query = db.query(Refund).filter(Refund.merchant_id == merchant_uuid)
        
        # Eager load relationships to prevent N+1 queries
        query = query.options(
            joinedload(Refund.payment_session),
            joinedload(Refund.merchant)
        )
        
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
    current_user: dict = Depends(require_merchant),
    _: bool = Depends(require_replay_protection)
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
    current_user: dict = Depends(require_merchant),
    _: bool = Depends(require_replay_protection)
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
        
        # Atomic balance deduction using SQL UPDATE with WHERE guard
        # This prevents race conditions: the UPDATE only succeeds if
        # balance >= refund_amount at the moment of execution.
        col = BALANCE_COLUMNS.get(refund.token.upper())
        if col:
            balance_column = getattr(Merchant, col)
            result = db.execute(
                update(Merchant)
                .where(
                    Merchant.id == merchant_uuid,
                    balance_column >= Decimal(str(refund.amount))
                )
                .values(**{col: balance_column - Decimal(str(refund.amount))})
            )
            if result.rowcount == 0:
                # Another concurrent request drained the balance
                db.rollback()
                raise HTTPException(
                    status_code=400,
                    detail="Insufficient funds (concurrent modification detected). Please retry."
                )
    
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


@router.post("/{refund_id}/force-retry")
async def force_retry_refund(
    refund_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant),
    _: bool = Depends(require_replay_protection)
):
    """
    Force retry a COMPLETED refund that failed on-chain.
    
    Use this when a refund shows COMPLETED in the database but the transaction
    never actually went through on the blockchain. This will:
    1. Clear the fake/incomplete tx_hash
    2. Reset status back to PENDING
    3. Trigger reprocessing on-chain
    
    This is useful for recovery when blockchain transactions fail despite 
    being marked as successful.
    """
    merchant_uuid = uuid.UUID(current_user["id"])
    
    refund = db.query(Refund).filter(
        and_(
            Refund.id == refund_id,
            Refund.merchant_id == merchant_uuid
        )
    ).first()
    
    if not refund:
        raise HTTPException(status_code=404, detail="Refund not found")
    
    if refund.status != DBRefundStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Can only force-retry COMPLETED refunds. Current status: {refund.status.value}"
        )
    
    # Clear the failed transaction hash
    old_tx_hash = refund.tx_hash
    refund.tx_hash = None
    refund.status = DBRefundStatus.PENDING
    refund.failure_reason = f"Force retry after on-chain failure (was: {old_tx_hash})"
    
    logger.info(
        f"Force retrying refund {refund_id}: "
        f"Cleared tx_hash '{old_tx_hash}', reset to PENDING"
    )
    
    db.commit()
    
    return {
        "message": "Refund queued for force retry",
        "id": refund_id,
        "previous_tx_hash": old_tx_hash,
        "new_status": "PENDING"
    }


@router.patch("/{refund_id}/update-address")
async def update_refund_address(
    refund_id: str,
    refund_address: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant),
    _: bool = Depends(require_replay_protection)
):
    """
    Update refund address for a FAILED refund and reset to PENDING.
    
    This is used when a refund was created without a recipient address.
    Updates the address and resets the refund to PENDING status so it can
    be reprocessed on-chain.
    
    Query params:
    - refund_address: The blockchain address to refund to
    """
    merchant_uuid = uuid.UUID(current_user["id"])
    
    if not refund_address or refund_address.strip() == "":
        raise HTTPException(status_code=400, detail="refund_address is required")
    
    refund = db.query(Refund).filter(
        and_(
            Refund.id == refund_id,
            Refund.merchant_id == merchant_uuid
        )
    ).first()
    
    if not refund:
        raise HTTPException(status_code=404, detail="Refund not found")
    
    if refund.status != DBRefundStatus.FAILED:
        raise HTTPException(
            status_code=400, 
            detail=f"Can only update address for FAILED refunds. Current status: {refund.status.value}"
        )
    
    old_address = refund.refund_address
    refund.refund_address = refund_address.strip()
    refund.status = DBRefundStatus.PENDING
    refund.failure_reason = f"Address updated from '{old_address or '(empty)'}' to '{refund_address}', reset to PENDING"
    refund.processed_at = None  # Clear processed_at so it gets reprocessed
    
    logger.info(
        f"Updated refund {refund_id} address: "
        f"'{old_address or '(empty)'}' → '{refund_address}', status → PENDING"
    )
    
    db.commit()
    
    return {
        "message": "Refund address updated and reset to PENDING",
        "id": refund_id,
        "previous_address": old_address or "(empty)",
        "new_address": refund_address,
        "new_status": "PENDING"
    }


@router.post("/process-queued")
async def process_queued_refunds(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant),
    _: bool = Depends(require_replay_protection)
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
            
            # Atomic balance deduction using SQL UPDATE with WHERE guard
            col = BALANCE_COLUMNS.get(token.upper())
            if col:
                balance_column = getattr(Merchant, col)
                result = db.execute(
                    update(Merchant)
                    .where(
                        Merchant.id == merchant_uuid,
                        balance_column >= Decimal(str(refund.amount))
                    )
                    .values(**{col: balance_column - Decimal(str(refund.amount))})
                )
                if result.rowcount == 0:
                    # Concurrent modification detected
                    db.rollback()
                    raise HTTPException(
                        status_code=400,
                        detail="Insufficient funds (concurrent modification). Please retry."
                    )
            
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


@router.post("/process-pending")
async def process_pending_refunds(
    current_user: dict = Depends(require_merchant),
    background_tasks: BackgroundTasks = None,
):
    """
    Process all PENDING refunds immediately.
    
    Sends all refunds in PENDING status to the blockchain.
    Returns statistics about the processing.
    """
    merchant_id = current_user["id"]
    logger.info(f"[ENDPOINT] process_pending_refunds called by merchant {merchant_id}")
    
    # Run processing in background
    if background_tasks:
        background_tasks.add_task(process_pending_refunds_background, merchant_id)
        return {
            "message": "Pending refunds processing started in background",
            "status": "submitted"
        }
    else:
        # Direct processing (for testing)
        stats = await process_all_pending_refunds()
        return {
            "message": "Pending refunds processed",
            "stats": stats
        }


def process_pending_refunds_background(merchant_id: str):
    """Background task to process all pending refunds"""
    try:
        logger.info(f"[BACKGROUND] Starting pending refund processor for merchant {merchant_id}")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        stats = loop.run_until_complete(process_all_pending_refunds())
        loop.close()
        logger.info(
            f"[BACKGROUND] Pending refund processor completed: "
            f"{stats['processed']} processed, {stats['failed']} failed"
        )
    except Exception as e:
        logger.error(f"[BACKGROUND] Error in pending refund processor: {str(e)}", exc_info=True)


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


# Background task wrapper for processing refunds asynchronously
def process_refund(refund_id: str, merchant_id: str):
    """
    Wrapper function for background refund processing.
    Runs the async refund processor in a new event loop.
    Called by FastAPI BackgroundTasks.
    """
    try:
        logger.info(f"[BACKGROUND] Starting refund processor for refund_id={refund_id}, merchant_id={merchant_id}")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(process_refund_on_chain(refund_id, merchant_id))
        loop.close()
        logger.info(f"[BACKGROUND] Refund processor completed with result={result}")
    except Exception as e:
        logger.error(f"[BACKGROUND] Error in refund processor: {str(e)}", exc_info=True)
