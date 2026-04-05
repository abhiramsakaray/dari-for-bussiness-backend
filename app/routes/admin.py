from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.core import get_db, require_admin
from app.core.security import require_merchant_or_admin
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
            paid_at=session.paid_at,
            coupon_code=session.coupon_code,
            discount_amount=session.discount_amount,
            amount_paid=(session.amount_fiat or 0) - (session.discount_amount or 0),
            payer_email=session.payer_email,
            payer_name=session.payer_name,
            payer_currency=session.payer_currency,
            payer_amount_local=float(session.payer_amount_local) if session.payer_amount_local else None,
            merchant_currency=session.merchant_currency,
            merchant_amount_local=float(session.merchant_amount_local) if session.merchant_amount_local else None,
            is_cross_border=session.is_cross_border or False,
            is_tokenized=session.is_tokenized or False,
            risk_score=float(session.risk_score) if session.risk_score else None,
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


# ============================================
# Scheduler Management Endpoints
# ============================================

@router.get("/scheduler/status")
async def get_scheduler_status(current_user: dict = Depends(require_admin)):
    """Get current scheduler status and list all jobs (admin only)."""
    try:
        from app.services.refund_scheduler import scheduler, list_scheduled_jobs
        
        jobs = list_scheduled_jobs()
        
        return {
            "status": "running" if scheduler.running else "stopped",
            "jobs": jobs,
            "total_jobs": len(jobs)
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting scheduler status: {str(e)}"
        )


@router.post("/scheduler/refunds/trigger")
async def trigger_refund_processing(current_user: dict = Depends(require_merchant_or_admin)):
    """Manually trigger INSTANT refund processing (admin or merchant)."""
    try:
        from app.services.refund_processor import process_all_pending_refunds
        
        # Run async function in INSTANT mode
        stats = await process_all_pending_refunds(mode="instant")
        
        return {
            "message": "Refund processing completed (INSTANT MODE)",
            "status": "success",
            "mode": "instant",
            "statistics": {
                "total_pending_found": stats['total_pending'],
                "successfully_processed": stats['processed'],
                "failed": stats['failed'],
                "errors": stats['errors']
            }
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing refunds: {str(e)}"
        )


@router.post("/scheduler/refunds/start")
async def start_refund_scheduler(
    current_user: dict = Depends(require_admin),
    interval_minutes: int = 60
):
    """Start the automatic refund scheduler (admin only)."""
    try:
        from app.services.refund_scheduler import scheduler, start_refund_scheduler
        
        if scheduler.running:
            return {
                "message": "Scheduler is already running",
                "status": "already_running"
            }
        
        start_refund_scheduler(interval_minutes=interval_minutes)
        
        return {
            "message": f"Refund scheduler started (interval: {interval_minutes} minutes)",
            "status": "started",
            "interval_minutes": interval_minutes
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error starting scheduler: {str(e)}"
        )


@router.post("/scheduler/refunds/stop")
async def stop_refund_scheduler(current_user: dict = Depends(require_admin)):
    """Stop the automatic refund scheduler (admin only)."""
    try:
        from app.services.refund_scheduler import scheduler, stop_refund_scheduler
        
        if not scheduler.running:
            return {
                "message": "Scheduler is not running",
                "status": "already_stopped"
            }
        
        stop_refund_scheduler()
        
        return {
            "message": "Refund scheduler stopped",
            "status": "stopped"
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error stopping scheduler: {str(e)}"
        )
