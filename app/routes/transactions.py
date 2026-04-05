"""
Transaction and Refund Tracking API
Provides endpoints for merchants to view transaction history with refund details
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import require_merchant
from app.models.models import PaymentSession, Refund, PaymentEvent, RefundStatus as DBRefundStatus
from pydantic import BaseModel
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/transactions", tags=["transactions"])


# ============= SCHEMAS =============

class RefundInfo(BaseModel):
    id: str
    payment_session_id: str
    status: str
    amount: Decimal
    token: str
    chain: str
    tx_hash: Optional[str]
    recipient_address: str
    reason: Optional[str]
    failure_reason: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


class TransactionDetail(BaseModel):
    """Complete transaction with refund details"""
    session_id: str
    amount_fiat: Decimal
    fiat_currency: str
    amount_token: str
    token: str
    chain: str
    status: str
    tx_hash: Optional[str]
    paid_at: Optional[datetime]
    created_at: datetime
    
    # Refund info (if exists)
    refund: Optional[RefundInfo] = None
    refund_count: int = 0


class RefundStatusSummary(BaseModel):
    """Summary of refund statuses"""
    pending: int
    processing: int
    completed: int
    failed: int
    total: int
    total_completed_amount: Decimal
    total_failed_amount: Decimal


class TransactionSummary(BaseModel):
    """Transaction summary with stats"""
    total_transactions: int
    total_paid_amount: Decimal
    average_transaction_value: Decimal
    transactions: List[TransactionDetail]


# ============= ENDPOINTS =============

@router.get("/refund-stats", response_model=RefundStatusSummary)
async def get_refund_statistics(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant)
):
    """Get refund status statistics for merchant"""
    
    merchant_id = current_user.get("id")
    
    # Count refunds by status
    stats = {
        "pending": 0,
        "processing": 0,
        "completed": 0,
        "failed": 0,
        "total": 0,
        "total_completed_amount": Decimal("0"),
        "total_failed_amount": Decimal("0"),
    }
    
    # Query refund counts by status
    for status in [DBRefundStatus.PENDING, DBRefundStatus.PROCESSING, DBRefundStatus.COMPLETED, DBRefundStatus.FAILED]:
        count = db.query(func.count(Refund.id)).filter(
            Refund.merchant_id == merchant_id,
            Refund.status == status
        ).scalar()
        
        status_key = status.value.lower()
        stats[status_key] = count or 0
        stats["total"] += stats[status_key]
    
    # Calculate totals for completed and failed
    completed_sum = db.query(func.sum(Refund.amount)).filter(
        Refund.merchant_id == merchant_id,
        Refund.status == DBRefundStatus.COMPLETED
    ).scalar()
    stats["total_completed_amount"] = completed_sum or Decimal("0")
    
    failed_sum = db.query(func.sum(Refund.amount)).filter(
        Refund.merchant_id == merchant_id,
        Refund.status == DBRefundStatus.FAILED
    ).scalar()
    stats["total_failed_amount"] = failed_sum or Decimal("0")
    
    logger.info(f"Refund stats for merchant {merchant_id}: {stats}")
    
    return RefundStatusSummary(**stats)


@router.get("/with-refunds", response_model=List[TransactionDetail])
async def get_transactions_with_refunds(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant)
):
    """Get merchant transactions with associated refund information"""
    
    merchant_id = current_user.get("id")
    
    # Query payment sessions for merchant
    query = db.query(PaymentSession).filter(
        PaymentSession.merchant_id == merchant_id
    )
    
    # Filter by status if provided
    if status:
        query = query.filter(PaymentSession.status == status)
    
    # Get total count
    total = query.count()
    
    # Apply pagination
    sessions = query.order_by(PaymentSession.created_at.desc()).offset(offset).limit(limit).all()
    
    result = []
    for session in sessions:
        # Get associated refunds
        refunds = db.query(Refund).filter(
            Refund.payment_session_id == session.id
        ).all()
        
        # Get the most recent refund
        latest_refund = None
        if refunds:
            latest_refund = max(refunds, key=lambda r: r.created_at)
        
        transaction = TransactionDetail(
            session_id=session.id,
            amount_fiat=session.amount_fiat,
            fiat_currency=session.fiat_currency,
            amount_token=session.amount_token,
            token=session.token or "",
            chain=session.chain or "",
            status=session.status.value if session.status else "unknown",
            tx_hash=session.tx_hash,
            paid_at=session.paid_at,
            created_at=session.created_at,
            refund=RefundInfo(
                id=latest_refund.id,
                payment_session_id=latest_refund.payment_session_id,
                status=latest_refund.status.value,
                amount=latest_refund.amount,
                token=latest_refund.token,
                chain=latest_refund.chain,
                tx_hash=latest_refund.tx_hash,
                recipient_address=latest_refund.refund_address,
                reason=latest_refund.reason,
                failure_reason=latest_refund.failure_reason,
                created_at=latest_refund.created_at,
                completed_at=latest_refund.completed_at
            ) if latest_refund else None,
            refund_count=len(refunds)
        )
        result.append(transaction)
    
    logger.info(f"Retrieved {len(result)} transactions with refunds for merchant {merchant_id}")
    
    return result


@router.get("/refund-details/{refund_id}")
async def get_refund_transaction_details(
    refund_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant)
):
    """Get detailed refund and transaction information"""
    
    merchant_id = current_user.get("id")
    
    # Get refund
    refund = db.query(Refund).filter(
        Refund.id == refund_id,
        Refund.merchant_id == merchant_id
    ).first()
    
    if not refund:
        raise HTTPException(status_code=404, detail="Refund not found")
    
    # Get payment session
    session = db.query(PaymentSession).filter(
        PaymentSession.id == refund.payment_session_id
    ).first()
    
    # Get payment events for refund
    events = db.query(PaymentEvent).filter(
        PaymentEvent.session_id == refund.payment_session_id
    ).order_by(PaymentEvent.created_at).all()
    
    return {
        "refund": RefundInfo.model_validate(refund),
        "transaction": {
            "session_id": session.id if session else None,
            "amount_fiat": session.amount_fiat if session else None,
            "amount_token": session.amount_token if session else None,
            "token": session.token if session else None,
            "chain": session.chain if session else None,
            "tx_hash": session.tx_hash if session else None,
            "paid_at": session.paid_at if session else None,
            "created_at": session.created_at if session else None,
        },
        "events": [
            {
                "event_type": event.event_type,
                "chain": event.chain,
                "tx_hash": event.tx_hash,
                "details": event.details,
                "created_at": event.created_at
            }
            for event in events
        ]
    }


@router.get("/summary")
async def get_transaction_summary(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant)
):
    """Get transaction summary for dashboard"""
    
    merchant_id = current_user.get("id")
    
    # Calculate date range
    now = datetime.utcnow()
    start_date = now - timedelta(days=days)
    
    # Get transactions in date range
    sessions = db.query(PaymentSession).filter(
        PaymentSession.merchant_id == merchant_id,
        PaymentSession.created_at >= start_date
    ).all()
    
    # Calculate stats
    total_transactions = len(sessions)
    total_paid = Decimal("0")
    completed_count = 0
    
    for session in sessions:
        if session.amount_fiat:
            total_paid += session.amount_fiat
        if str(session.status).upper() == "PAID":
            completed_count += 1
    
    # Get refund stats
    refund_stats = {
        "pending": db.query(func.count(Refund.id)).filter(
            Refund.merchant_id == merchant_id,
            Refund.status == DBRefundStatus.PENDING
        ).scalar() or 0,
        "processing": db.query(func.count(Refund.id)).filter(
            Refund.merchant_id == merchant_id,
            Refund.status == DBRefundStatus.PROCESSING
        ).scalar() or 0,
        "completed": db.query(func.count(Refund.id)).filter(
            Refund.merchant_id == merchant_id,
            Refund.status == DBRefundStatus.COMPLETED
        ).scalar() or 0,
        "failed": db.query(func.count(Refund.id)).filter(
            Refund.merchant_id == merchant_id,
            Refund.status == DBRefundStatus.FAILED
        ).scalar() or 0,
    }
    
    return {
        "period_days": days,
        "start_date": start_date.isoformat(),
        "end_date": now.isoformat(),
        "total_transactions": total_transactions,
        "completed_transactions": completed_count,
        "total_paid": str(total_paid),
        "average_transaction_value": str(total_paid / completed_count if completed_count > 0 else 0),
        "refund_summary": refund_stats,
        "total_refunds": sum(refund_stats.values())
    }


@router.get("/export")
async def export_transactions(
    format_type: str = Query("json", regex="^(json|csv)$"),
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant)
):
    """Export transactions with refund data"""
    
    merchant_id = current_user.get("id")
    
    # Calculate date range
    now = datetime.utcnow()
    start_date = now - timedelta(days=days)
    
    # Get transactions with refunds
    sessions = db.query(PaymentSession).filter(
        PaymentSession.merchant_id == merchant_id,
        PaymentSession.created_at >= start_date
    ).order_by(PaymentSession.created_at.desc()).all()
    
    data = []
    for session in sessions:
        refunds = db.query(Refund).filter(
            Refund.payment_session_id == session.id
        ).all()
        
        for refund in refunds:
            data.append({
                "transaction_id": session.id,
                "transaction_amount": str(session.amount_fiat),
                "transaction_currency": session.fiat_currency,
                "transaction_status": str(session.status),
                "transaction_date": session.created_at.isoformat(),
                "refund_id": refund.id,
                "refund_amount": str(refund.amount),
                "refund_token": refund.token,
                "refund_chain": refund.chain,
                "refund_status": refund.status.value,
                "refund_tx_hash": refund.tx_hash or "",
                "refund_recipient": refund.refund_address,
                "refund_reason": refund.reason or "",
                "refund_date": refund.created_at.isoformat(),
            })
    
    if format_type == "csv":
        import csv
        import io
        
        if not data:
            raise HTTPException(status_code=404, detail="No transactions to export")
        
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)
        
        return {
            "format": "csv",
            "data": output.getvalue()
        }
    else:
        return {
            "format": "json",
            "count": len(data),
            "data": data
        }
