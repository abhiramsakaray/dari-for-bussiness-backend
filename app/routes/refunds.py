"""
Refunds API Routes
Process refunds for completed payments
"""
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import and_
import secrets
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional, List

from app.core.database import get_db
from app.core import require_merchant
from app.models.models import (
    Merchant, Refund, PaymentSession, PaymentStatus,
    RefundStatus as DBRefundStatus
)
from app.schemas.schemas import (
    RefundCreate, RefundResponse, RefundList, RefundStatus
)

router = APIRouter(prefix="/refunds", tags=["Refunds"])


def generate_refund_id() -> str:
    """Generate a unique refund ID"""
    return f"ref_{secrets.token_urlsafe(12)}"


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
    - Full refund: Returns entire payment amount
    - Partial refund: Returns specified amount
    
    The refund will be processed asynchronously and sent to the customer's
    provided wallet address.
    """
    # Find the payment session
    payment = db.query(PaymentSession).filter(
        and_(
            PaymentSession.id == refund_data.payment_session_id,
            PaymentSession.merchant_id == uuid.UUID(current_user["id"])
        )
    ).first()
    
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    
    # Verify payment was successful
    if payment.status != PaymentStatus.PAID:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot refund payment with status: {payment.status.value}"
        )
    
    # Check if already fully refunded
    existing_refunds = db.query(Refund).filter(
        and_(
            Refund.payment_session_id == payment.id,
            Refund.status.in_([DBRefundStatus.PENDING, DBRefundStatus.PROCESSING, DBRefundStatus.COMPLETED])
        )
    ).all()
    
    total_refunded = sum(r.amount for r in existing_refunds)
    
    # Determine refund amount
    if refund_data.amount:
        refund_amount = refund_data.amount
    else:
        # Full refund - use the original payment amount
        refund_amount = payment.amount_crypto - total_refunded
    
    if refund_amount <= 0:
        raise HTTPException(
            status_code=400,
            detail="Payment has already been fully refunded"
        )
    
    if refund_amount > (payment.amount_crypto - total_refunded):
        raise HTTPException(
            status_code=400,
            detail=f"Refund amount exceeds available balance. Max refundable: {payment.amount_crypto - total_refunded}"
        )
    
    # Validate we have token and chain info
    if not payment.token or not payment.chain:
        raise HTTPException(
            status_code=400,
            detail="Payment missing token or chain information"
        )
    
    refund_id = generate_refund_id()
    
    refund = Refund(
        id=refund_id,
        payment_session_id=payment.id,
        merchant_id=uuid.UUID(current_user["id"]),
        amount=refund_amount,
        token=payment.token,
        chain=payment.chain,
        refund_address=refund_data.refund_address,
        status=DBRefundStatus.PENDING,
        reason=refund_data.reason
    )
    
    db.add(refund)
    
    # Update payment status if fully refunded
    remaining = payment.amount_crypto - total_refunded - refund_amount
    if remaining <= 0:
        payment.status = PaymentStatus.REFUNDED
    else:
        payment.status = PaymentStatus.PARTIALLY_REFUNDED
    
    db.commit()
    db.refresh(refund)
    
    # TODO: Process refund in background
    # background_tasks.add_task(process_refund, refund.id)
    
    return build_refund_response(refund)


@router.get("", response_model=RefundList)
async def list_refunds(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: Optional[RefundStatus] = None,
    payment_session_id: Optional[str] = None,
    current_user: dict = Depends(require_merchant),
    db: Session = Depends(get_db)
):
    """
    List all refunds for the merchant.
    
    Supports filtering by status and payment session.
    """
    # Filter by merchant_id for security
    query = db.query(Refund).filter(Refund.merchant_id == uuid.UUID(current_user["id"]))
    
    if status:
        query = query.filter(Refund.status == status.value)
    
    if payment_session_id:
        query = query.filter(Refund.payment_session_id == payment_session_id)
    
    total = query.count()
    
    refunds = query.order_by(Refund.created_at.desc())\
        .offset((page - 1) * page_size)\
        .limit(page_size)\
        .all()
    
    return RefundList(
        refunds=[build_refund_response(r) for r in refunds],
        total=total
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
    Cancel a pending refund.
    
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
    
    if refund.status != DBRefundStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail="Can only cancel pending refunds"
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
    Retry a failed refund.
    
    Creates a new processing attempt for a previously failed refund.
    """
    refund = db.query(Refund).filter(
        and_(
            Refund.id == refund_id,
            Refund.merchant_id == uuid.UUID(current_user["id"])
        )
    ).first()
    
    if not refund:
        raise HTTPException(status_code=404, detail="Refund not found")
    
    if refund.status != DBRefundStatus.FAILED:
        raise HTTPException(
            status_code=400,
            detail="Can only retry failed refunds"
        )
    
    refund.status = DBRefundStatus.PENDING
    db.commit()
    
    # TODO: Process refund in background
    # background_tasks.add_task(process_refund, refund.id)
    
    return {"message": "Refund queued for retry", "id": refund_id}


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
        created_at=refund.created_at,
        processed_at=refund.processed_at,
        completed_at=refund.completed_at
    )
