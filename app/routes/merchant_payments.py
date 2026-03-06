from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta
import uuid
from app.core import get_db, require_merchant
from app.models import Merchant, PaymentSession, PaymentStatus
from app.schemas import PaymentSessionStatus, PaymentListItem
from decimal import Decimal

router = APIRouter(prefix="/merchant/payments", tags=["Merchant Payments"])


@router.get("", response_model=List[PaymentListItem])
async def get_my_payment_sessions(
    current_user: dict = Depends(require_merchant),
    db: Session = Depends(get_db),
    status: Optional[str] = Query(None, description="Filter by status: created, paid, expired"),
    limit: int = Query(50, le=100, description="Number of results to return"),
    offset: int = Query(0, description="Number of results to skip")
):
    """Get all payment sessions for the authenticated merchant."""
    merchant_uuid = uuid.UUID(current_user["id"]) if isinstance(current_user["id"], str) else current_user["id"]
    query = db.query(PaymentSession).filter(PaymentSession.merchant_id == merchant_uuid)
    
    # Filter by status if provided
    if status:
        try:
            status_enum = PaymentStatus(status.lower())
            query = query.filter(PaymentSession.status == status_enum)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status. Must be one of: created, paid, expired"
            )
    
    # Order by created_at descending (newest first)
    sessions = query.order_by(PaymentSession.created_at.desc()).offset(offset).limit(limit).all()
    
    return [
        PaymentListItem(
            id=session.id,
            merchant_id=str(session.merchant_id),
            merchant_name=session.merchant.name,
            amount_fiat=session.amount_fiat,
            fiat_currency=session.fiat_currency,
            amount_usdc=session.amount_usdc,
            status=session.status.value,
            tx_hash=session.tx_hash,
            created_at=session.created_at,
            paid_at=session.paid_at
        )
        for session in sessions
    ]


@router.get("/stats")
async def get_payment_stats(
    current_user: dict = Depends(require_merchant),
    db: Session = Depends(get_db)
):
    """Get payment statistics for the authenticated merchant."""
    merchant_uuid = uuid.UUID(current_user["id"]) if isinstance(current_user["id"], str) else current_user["id"]
    merchant_id = merchant_uuid
    
    # Total sessions
    total_sessions = db.query(PaymentSession).filter(
        PaymentSession.merchant_id == merchant_id
    ).count()
    
    # Sessions by status
    paid_count = db.query(PaymentSession).filter(
        PaymentSession.merchant_id == merchant_id,
        PaymentSession.status == PaymentStatus.PAID
    ).count()
    
    pending_count = db.query(PaymentSession).filter(
        PaymentSession.merchant_id == merchant_id,
        PaymentSession.status == PaymentStatus.CREATED
    ).count()
    
    expired_count = db.query(PaymentSession).filter(
        PaymentSession.merchant_id == merchant_id,
        PaymentSession.status == PaymentStatus.EXPIRED
    ).count()
    
    # Total revenue (sum of paid sessions)
    paid_sessions = db.query(PaymentSession).filter(
        PaymentSession.merchant_id == merchant_id,
        PaymentSession.status == PaymentStatus.PAID
    ).all()
    
    total_usdc = sum(Decimal(session.amount_usdc) for session in paid_sessions)
    
    # Today's stats
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_paid = db.query(PaymentSession).filter(
        PaymentSession.merchant_id == merchant_id,
        PaymentSession.status == PaymentStatus.PAID,
        PaymentSession.paid_at >= today_start
    ).count()
    
    # This week's stats
    week_start = datetime.utcnow() - timedelta(days=7)
    week_paid = db.query(PaymentSession).filter(
        PaymentSession.merchant_id == merchant_id,
        PaymentSession.status == PaymentStatus.PAID,
        PaymentSession.paid_at >= week_start
    ).count()
    
    # Success rate
    success_rate = (paid_count / total_sessions * 100) if total_sessions > 0 else 0
    
    return {
        "total_sessions": total_sessions,
        "sessions_by_status": {
            "paid": paid_count,
            "pending": pending_count,
            "expired": expired_count
        },
        "revenue": {
            "total_usdc": float(total_usdc),
            "currency": "USDC"
        },
        "recent": {
            "today": today_paid,
            "this_week": week_paid
        },
        "success_rate": round(success_rate, 2)
    }


@router.get("/recent", response_model=List[PaymentListItem])
async def get_recent_payments(
    current_user: dict = Depends(require_merchant),
    db: Session = Depends(get_db),
    limit: int = Query(10, le=50, description="Number of recent payments to return")
):
    """Get recent payment sessions for the authenticated merchant."""
    sessions = db.query(PaymentSession).filter(
        PaymentSession.merchant_id == current_user["id"]
    ).order_by(
        PaymentSession.created_at.desc()
    ).limit(limit).all()
    
    return [
        PaymentListItem(
            id=session.id,
            merchant_id=str(session.merchant_id),
            merchant_name=session.merchant.name,
            amount_fiat=session.amount_fiat,
            fiat_currency=session.fiat_currency,
            amount_usdc=session.amount_usdc,
            status=session.status.value,
            tx_hash=session.tx_hash,
            created_at=session.created_at,
            paid_at=session.paid_at
        )
        for session in sessions
    ]


@router.get("/{session_id}", response_model=PaymentSessionStatus)
async def get_payment_session_detail(
    session_id: str,
    current_user: dict = Depends(require_merchant),
    db: Session = Depends(get_db)
):
    """Get detailed information about a specific payment session."""
    session = db.query(PaymentSession).filter(
        PaymentSession.id == session_id,
        PaymentSession.merchant_id == current_user["id"]
    ).first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment session not found"
        )
    
    return PaymentSessionStatus(
        session_id=session.id,
        status=session.status.value,
        amount_usdc=session.amount_usdc,
        tx_hash=session.tx_hash,
        created_at=session.created_at,
        paid_at=session.paid_at
    )


@router.post("/{session_id}/cancel")
async def cancel_payment_session(
    session_id: str,
    current_user: dict = Depends(require_merchant),
    db: Session = Depends(get_db)
):
    """Manually cancel/expire a payment session."""
    session = db.query(PaymentSession).filter(
        PaymentSession.id == session_id,
        PaymentSession.merchant_id == current_user["id"]
    ).first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment session not found"
        )
    
    if session.status == PaymentStatus.PAID:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot cancel a paid session"
        )
    
    if session.status == PaymentStatus.EXPIRED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session is already expired"
        )
    
    session.status = PaymentStatus.EXPIRED
    db.commit()
    
    return {
        "message": "Payment session cancelled successfully",
        "session_id": session_id,
        "status": "expired"
    }
