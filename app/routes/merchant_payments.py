from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta
import uuid
import logging
from app.core import get_db, require_merchant
from app.core.cache import cache, make_cache_key
from app.models import Merchant, PaymentSession, PaymentStatus
from app.schemas import PaymentSessionStatus, PaymentListItem, LocalCurrencyAmount
from app.services.currency_service import get_currency_for_country, build_local_amount
from decimal import Decimal

router = APIRouter(prefix="/merchant/payments", tags=["Merchant Payments"])
logger = logging.getLogger(__name__)


def _session_to_list_item(session: PaymentSession) -> PaymentListItem:
    """Convert a PaymentSession ORM object to a PaymentListItem with coupon breakdown."""
    discount = session.discount_amount or Decimal("0")
    return PaymentListItem(
        id=session.id,
        merchant_id=str(session.merchant_id),
        merchant_name=session.merchant.name if session.merchant else "Unknown",
        amount_fiat=session.amount_fiat,
        fiat_currency=session.fiat_currency,
        amount_usdc=session.amount_usdc,
        status=session.status.value,
        tx_hash=session.tx_hash,
        created_at=session.created_at,
        paid_at=session.paid_at,
        expires_at=session.expires_at,
        payer_email=session.payer_email,
        payer_name=session.payer_name,
        coupon_code=session.coupon_code,
        discount_amount=session.discount_amount,
        amount_paid=session.amount_fiat - discount if session.discount_amount else None,
    )


async def _enrich_with_local_currency(
    items: list[PaymentListItem],
    merchant: Merchant,
) -> list[PaymentListItem]:
    """Add local currency conversions to payment list items."""
    currency_code, currency_symbol, _ = get_currency_for_country(merchant.country)
    if currency_code == "USD":
        return items

    for item in items:
        item.amount_fiat_local = LocalCurrencyAmount(
            **(await build_local_amount(float(item.amount_fiat), currency_code, currency_symbol))
        )
        if item.discount_amount is not None:
            item.discount_amount_local = LocalCurrencyAmount(
                **(await build_local_amount(float(item.discount_amount), currency_code, currency_symbol))
            )
        if item.amount_paid is not None:
            item.amount_paid_local = LocalCurrencyAmount(
                **(await build_local_amount(float(item.amount_paid), currency_code, currency_symbol))
            )
    return items


@router.get("", response_model=List[PaymentListItem])
async def get_my_payment_sessions(
    current_user: dict = Depends(require_merchant),
    db: Session = Depends(get_db),
    status: Optional[str] = Query(None, description="Filter by status: created, paid, expired"),
    limit: int = Query(50, le=100, description="Number of results to return"),
    offset: int = Query(0, description="Number of results to skip")
):
    """Get all payment sessions for the authenticated merchant."""
    try:
        merchant_uuid = uuid.UUID(current_user["id"]) if isinstance(current_user["id"], str) else current_user["id"]
        logger.info(f"Fetching payment sessions for merchant {merchant_uuid}, status={status}, limit={limit}, offset={offset}")
        
        # Check cache (only for default unfiltered listing)
        ck = make_cache_key("payments_list", merchant_uuid, status, limit, offset)
        cached = cache.get(ck, region="payments")
        if cached is not None:
            return cached
        
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
        
        payment_list = [_session_to_list_item(session) for session in sessions]
        
        # Enrich with local currency
        merchant = db.query(Merchant).filter(Merchant.id == merchant_uuid).first()
        if merchant:
            payment_list = await _enrich_with_local_currency(payment_list, merchant)
        
        logger.info(f"Found {len(payment_list)} payment sessions for merchant {merchant_uuid}")
        cache.set(ck, payment_list, region="payments")
        return payment_list
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching payment sessions: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch payment sessions: {str(e)}"
        )


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
    
    total_usdc = sum(Decimal(session.amount_usdc or "0") for session in paid_sessions)
    total_coupon_discount = sum(session.discount_amount or Decimal("0") for session in paid_sessions)
    coupon_payment_count = sum(1 for s in paid_sessions if s.coupon_code)
    
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
    
    # Local currency conversion
    merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    currency_code, currency_symbol, _ = get_currency_for_country(merchant.country if merchant else None)
    revenue_local = await build_local_amount(float(total_usdc), currency_code, currency_symbol)
    discount_local = await build_local_amount(float(total_coupon_discount), currency_code, currency_symbol)
    
    return {
        "total_sessions": total_sessions,
        "sessions_by_status": {
            "paid": paid_count,
            "pending": pending_count,
            "expired": expired_count
        },
        "revenue": {
            "total_usdc": float(total_usdc),
            "currency": "USDC",
            "total_coupon_discount": float(total_coupon_discount),
            "coupon_payment_count": coupon_payment_count,
            "total_local": revenue_local,
            "total_coupon_discount_local": discount_local,
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
    merchant_uuid = uuid.UUID(current_user["id"]) if isinstance(current_user["id"], str) else current_user["id"]
    sessions = db.query(PaymentSession).filter(
        PaymentSession.merchant_id == merchant_uuid
    ).order_by(
        PaymentSession.created_at.desc()
    ).limit(limit).all()
    
    items = [_session_to_list_item(session) for session in sessions]
    merchant = db.query(Merchant).filter(Merchant.id == merchant_uuid).first()
    if merchant:
        items = await _enrich_with_local_currency(items, merchant)
    return items


# ── Payer leads ──
@router.get("/payer-leads", response_model=List[PaymentListItem])
async def get_payer_leads(
    current_user: dict = Depends(require_merchant),
    db: Session = Depends(get_db),
    include_paid: bool = Query(False, description="Include already paid sessions"),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
):
    """
    Returns sessions where the customer submitted their contact info
    but payment is still pending or abandoned. Use this list to follow
    up with customers who started a payment but didn't complete it.
    """
    merchant_uuid = uuid.UUID(current_user["id"]) if isinstance(current_user["id"], str) else current_user["id"]

    query = db.query(PaymentSession).filter(
        PaymentSession.merchant_id == merchant_uuid,
        PaymentSession.payer_email.isnot(None),
    )
    if not include_paid:
        query = query.filter(PaymentSession.status != PaymentStatus.PAID)

    sessions = query.order_by(PaymentSession.created_at.desc()).offset(offset).limit(limit).all()

    items = [_session_to_list_item(session) for session in sessions]
    merchant = db.query(Merchant).filter(Merchant.id == merchant_uuid).first()
    if merchant:
        items = await _enrich_with_local_currency(items, merchant)
    return items


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
        amount=str(session.amount_fiat),
        currency=session.fiat_currency,
        token=session.token,
        chain=session.chain,
        tx_hash=session.tx_hash,
        block_number=session.block_number,
        confirmations=session.confirmations,
        order_id=session.order_id,
        created_at=session.created_at,
        paid_at=session.paid_at,
        expires_at=session.expires_at,
        amount_usdc=session.amount_usdc,
        metadata=session.session_metadata,
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
