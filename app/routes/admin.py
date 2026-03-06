from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.core import get_db, require_admin
from app.models import Merchant, PaymentSession
from app.schemas import MerchantListItem, PaymentListItem, MerchantDisable

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/merchants", response_model=List[MerchantListItem])
async def list_all_merchants(
    current_user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    """List all merchants (admin only)."""
    merchants = db.query(Merchant).offset(skip).limit(limit).all()
    
    return [
        MerchantListItem(
            id=str(merchant.id),
            name=merchant.name,
            email=merchant.email,
            stellar_address=merchant.stellar_address,
            is_active=merchant.is_active,
            created_at=merchant.created_at
        )
        for merchant in merchants
    ]


@router.get("/payments", response_model=List[PaymentListItem])
async def list_all_payments(
    current_user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    """List all payment sessions (admin only)."""
    sessions = db.query(PaymentSession).offset(skip).limit(limit).all()
    
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


@router.patch("/merchants/{merchant_id}/disable")
async def disable_merchant(
    merchant_id: str,
    disable_data: MerchantDisable,
    current_user: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Enable or disable a merchant (admin only)."""
    merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    
    if not merchant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Merchant not found"
        )
    
    merchant.is_active = disable_data.is_active
    db.commit()
    
    action = "enabled" if disable_data.is_active else "disabled"
    return {"message": f"Merchant {action} successfully"}


@router.get("/health")
async def gateway_health(
    current_user: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Get gateway health statistics (admin only)."""
    from app.models import PaymentStatus
    
    total_merchants = db.query(Merchant).count()
    active_merchants = db.query(Merchant).filter(Merchant.is_active == True).count()
    
    total_sessions = db.query(PaymentSession).count()
    paid_sessions = db.query(PaymentSession).filter(PaymentSession.status == PaymentStatus.PAID).count()
    pending_sessions = db.query(PaymentSession).filter(PaymentSession.status == PaymentStatus.CREATED).count()
    expired_sessions = db.query(PaymentSession).filter(PaymentSession.status == PaymentStatus.EXPIRED).count()
    
    return {
        "status": "healthy",
        "merchants": {
            "total": total_merchants,
            "active": active_merchants,
            "inactive": total_merchants - active_merchants
        },
        "payments": {
            "total": total_sessions,
            "paid": paid_sessions,
            "pending": pending_sessions,
            "expired": expired_sessions
        }
    }
