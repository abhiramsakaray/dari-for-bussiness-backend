from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta
from app.core import get_db
from app.models import PaymentSession, PaymentStatus
from app.schemas import PaymentSessionStatus

router = APIRouter(prefix="/public", tags=["Public"])


@router.get("/session/{session_id}/verify")
async def verify_payment_session(
    session_id: str,
    db: Session = Depends(get_db)
):
    """
    Public endpoint to verify if a payment session exists and get minimal info.
    Useful for integrations to verify session validity.
    """
    session = db.query(PaymentSession).filter(PaymentSession.id == session_id).first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment session not found"
        )
    
    # Check expiry
    expiry_time = session.created_at + timedelta(minutes=15)
    is_expired = datetime.utcnow() > expiry_time and session.status == PaymentStatus.CREATED
    
    return {
        "session_id": session.id,
        "exists": True,
        "status": session.status.value,
        "amount_usdc": session.amount_usdc,
        "merchant_name": session.merchant.name,
        "is_expired": is_expired,
        "created_at": session.created_at,
        "coupon_code": session.coupon_code,
        "discount_amount": float(session.discount_amount) if session.discount_amount else None,
    }


@router.get("/stats")
async def get_public_stats(db: Session = Depends(get_db)):
    """Get public gateway statistics (no authentication required)."""
    from app.models import Merchant
    
    total_sessions = db.query(PaymentSession).count()
    paid_sessions = db.query(PaymentSession).filter(
        PaymentSession.status == PaymentStatus.PAID
    ).count()
    
    active_merchants = db.query(Merchant).filter(
        Merchant.is_active == True
    ).count()
    
    # Last 24 hours stats
    yesterday = datetime.utcnow() - timedelta(hours=24)
    recent_paid = db.query(PaymentSession).filter(
        PaymentSession.status == PaymentStatus.PAID,
        PaymentSession.paid_at >= yesterday
    ).count()
    
    return {
        "gateway": "Dari for Business - Multi-Chain Payment Gateway",
        "network": "mainnet",
        "stats": {
            "total_transactions": total_sessions,
            "successful_payments": paid_sessions,
            "active_merchants": active_merchants,
            "last_24h_payments": recent_paid
        },
        "status": "operational"
    }
