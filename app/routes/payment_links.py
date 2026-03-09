"""
Payment Links API Routes
Reusable payment links for merchants
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import and_
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Optional, List

from app.core.database import get_db
from app.core import require_merchant
from app.models.models import Merchant, PaymentLink, PaymentLinkSession, PaymentSession
from app.schemas.schemas import (
    PaymentLinkCreate, PaymentLinkUpdate, PaymentLinkResponse, PaymentLinkList
)
from app.services.price_service import PriceService

router = APIRouter(prefix="/payment-links", tags=["Payment Links"])


def generate_link_id() -> str:
    """Generate a unique payment link ID"""
    return f"link_{secrets.token_urlsafe(16)}"


def get_checkout_url(request: Request, link_id: str) -> str:
    """Generate the public checkout URL for a payment link"""
    base_url = str(request.base_url).rstrip("/")
    return f"{base_url}/pay/{link_id}"


@router.post("", response_model=PaymentLinkResponse)
async def create_payment_link(
    link_data: PaymentLinkCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant)
):
    """
    Create a new reusable payment link.
    
    Payment links can be:
    - Fixed amount: Customer pays exact amount
    - Variable amount: Customer enters amount (within min/max range)
    - Single use: Deactivates after first payment
    - Expiring: Becomes invalid after expiry date
    """
    # Validate amount configuration
    if not link_data.is_amount_fixed:
        if link_data.min_amount and link_data.max_amount:
            if link_data.min_amount > link_data.max_amount:
                raise HTTPException(
                    status_code=400,
                    detail="min_amount cannot exceed max_amount"
                )
    
    link_id = generate_link_id()
    
    merchant = db.query(Merchant).filter(Merchant.id == uuid.UUID(current_user["id"])).first()
    
    payment_link = PaymentLink(
        id=link_id,
        merchant_id=uuid.UUID(current_user["id"]),
        name=link_data.name,
        description=link_data.description,
        amount_fiat=link_data.amount_fiat,
        fiat_currency=(link_data.fiat_currency or merchant.base_currency).upper(),
        is_amount_fixed=link_data.is_amount_fixed,
        min_amount=link_data.min_amount,
        max_amount=link_data.max_amount,
        accepted_tokens=link_data.accepted_tokens,
        accepted_chains=link_data.accepted_chains,
        success_url=link_data.success_url,
        cancel_url=link_data.cancel_url,
        is_single_use=link_data.is_single_use,
        expires_at=link_data.expires_at,
        link_metadata=link_data.metadata
    )
    
    db.add(payment_link)
    db.commit()
    db.refresh(payment_link)
    
    return PaymentLinkResponse(
        id=payment_link.id,
        name=payment_link.name,
        description=payment_link.description,
        amount_fiat=payment_link.amount_fiat,
        fiat_currency=payment_link.fiat_currency,
        is_amount_fixed=payment_link.is_amount_fixed,
        accepted_tokens=payment_link.accepted_tokens or [],
        accepted_chains=payment_link.accepted_chains or [],
        checkout_url=get_checkout_url(request, payment_link.id),
        success_url=payment_link.success_url,
        cancel_url=payment_link.cancel_url,
        is_active=payment_link.is_active,
        is_single_use=payment_link.is_single_use,
        expires_at=payment_link.expires_at,
        view_count=payment_link.view_count,
        payment_count=payment_link.payment_count,
        total_collected_usd=payment_link.total_collected_usd or 0,
        created_at=payment_link.created_at
    )


@router.get("", response_model=PaymentLinkList)
async def list_payment_links(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    """
    List all payment links for the merchant.
    
    Supports filtering by active status and pagination.
    """
    print(f"========== PAYMENT LINKS ENDPOINT HIT ==========")
    print(f"Page: {page}, Page size: {page_size}")
    print(f"================================================")
    
    # TEMP: Show all data (no auth)
    query = db.query(PaymentLink)
    
    if is_active is not None:
        query = query.filter(PaymentLink.is_active == is_active)
    
    total = query.count()
    
    links = query.order_by(PaymentLink.created_at.desc())\
        .offset((page - 1) * page_size)\
        .limit(page_size)\
        .all()
    
    link_responses = [
        PaymentLinkResponse(
            id=link.id,
            name=link.name,
            description=link.description,
            amount_fiat=link.amount_fiat,
            fiat_currency=link.fiat_currency,
            is_amount_fixed=link.is_amount_fixed,
            accepted_tokens=link.accepted_tokens or [],
            accepted_chains=link.accepted_chains or [],
            checkout_url=get_checkout_url(request, link.id),
            success_url=link.success_url,
            cancel_url=link.cancel_url,
            is_active=link.is_active,
            is_single_use=link.is_single_use,
            expires_at=link.expires_at,
            view_count=link.view_count,
            payment_count=link.payment_count,
            total_collected_usd=link.total_collected_usd or 0,
            created_at=link.created_at
        )
        for link in links
    ]
    
    return PaymentLinkList(
        links=link_responses,
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/{link_id}", response_model=PaymentLinkResponse)
async def get_payment_link(
    link_id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Get a specific payment link by ID."""
    # TEMP: Show all data (no auth)
    payment_link = db.query(PaymentLink).filter(PaymentLink.id == link_id).first()
    
    if not payment_link:
        raise HTTPException(status_code=404, detail="Payment link not found")
    
    return PaymentLinkResponse(
        id=payment_link.id,
        name=payment_link.name,
        description=payment_link.description,
        amount_fiat=payment_link.amount_fiat,
        fiat_currency=payment_link.fiat_currency,
        is_amount_fixed=payment_link.is_amount_fixed,
        accepted_tokens=payment_link.accepted_tokens or [],
        accepted_chains=payment_link.accepted_chains or [],
        checkout_url=get_checkout_url(request, payment_link.id),
        success_url=payment_link.success_url,
        cancel_url=payment_link.cancel_url,
        is_active=payment_link.is_active,
        is_single_use=payment_link.is_single_use,
        expires_at=payment_link.expires_at,
        view_count=payment_link.view_count,
        payment_count=payment_link.payment_count,
        total_collected_usd=payment_link.total_collected_usd or 0,
        created_at=payment_link.created_at
    )


@router.patch("/{link_id}", response_model=PaymentLinkResponse)
async def update_payment_link(
    link_id: str,
    update_data: PaymentLinkUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant)
):
    """
    Update a payment link.
    
    Only provided fields will be updated.
    """
    payment_link = db.query(PaymentLink).filter(
        and_(
            PaymentLink.id == link_id,
            PaymentLink.merchant_id == uuid.UUID(current_user["id"])
        )
    ).first()
    
    if not payment_link:
        raise HTTPException(status_code=404, detail="Payment link not found")
    
    update_fields = update_data.model_dump(exclude_unset=True)
    
    for field, value in update_fields.items():
        setattr(payment_link, field, value)
    
    payment_link.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(payment_link)
    
    return PaymentLinkResponse(
        id=payment_link.id,
        name=payment_link.name,
        description=payment_link.description,
        amount_fiat=payment_link.amount_fiat,
        fiat_currency=payment_link.fiat_currency,
        is_amount_fixed=payment_link.is_amount_fixed,
        accepted_tokens=payment_link.accepted_tokens or [],
        accepted_chains=payment_link.accepted_chains or [],
        checkout_url=get_checkout_url(request, payment_link.id),
        success_url=payment_link.success_url,
        cancel_url=payment_link.cancel_url,
        is_active=payment_link.is_active,
        is_single_use=payment_link.is_single_use,
        expires_at=payment_link.expires_at,
        view_count=payment_link.view_count,
        payment_count=payment_link.payment_count,
        total_collected_usd=payment_link.total_collected_usd or 0,
        created_at=payment_link.created_at
    )


@router.delete("/{link_id}")
async def delete_payment_link(
    link_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant)
):
    """
    Deactivate a payment link.
    
    Links are soft-deleted (deactivated) to preserve payment history.
    """
    payment_link = db.query(PaymentLink).filter(
        and_(
            PaymentLink.id == link_id,
            PaymentLink.merchant_id == uuid.UUID(current_user["id"])
        )
    ).first()
    
    if not payment_link:
        raise HTTPException(status_code=404, detail="Payment link not found")
    
    payment_link.is_active = False
    payment_link.updated_at = datetime.utcnow()
    db.commit()
    
    return {"message": "Payment link deactivated", "id": link_id}


@router.get("/{link_id}/analytics")
async def get_link_analytics(
    link_id: str,
    db: Session = Depends(get_db)
):
    """
    Get analytics for a payment link.
    
    Returns conversion metrics, recent payments, and usage stats.
    """
    # TEMP: Show all data (no auth)
    payment_link = db.query(PaymentLink).filter(PaymentLink.id == link_id).first()
    
    if not payment_link:
        raise HTTPException(status_code=404, detail="Payment link not found")
    
    # Get recent payments through this link
    recent_payments = db.query(PaymentSession).join(
        PaymentLinkSession,
        PaymentLinkSession.session_id == PaymentSession.id
    ).filter(
        PaymentLinkSession.payment_link_id == link_id
    ).order_by(
        PaymentSession.created_at.desc()
    ).limit(10).all()
    
    # Calculate conversion rate
    conversion_rate = 0
    if payment_link.view_count > 0:
        conversion_rate = (payment_link.payment_count / payment_link.view_count) * 100
    
    return {
        "link_id": link_id,
        "views": payment_link.view_count,
        "payments": payment_link.payment_count,
        "conversion_rate": round(conversion_rate, 2),
        "total_collected_usd": float(payment_link.total_collected_usd or 0),
        "recent_payments": [
            {
                "session_id": p.id,
                "amount": float(p.amount_fiat),
                "currency": p.fiat_currency,
                "status": p.status.value if hasattr(p.status, 'value') else p.status,
                "paid_at": p.paid_at.isoformat() if p.paid_at else None
            }
            for p in recent_payments
        ]
    }
