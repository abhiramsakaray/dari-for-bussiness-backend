"""
Payment Links API Routes
Reusable payment links for merchants
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import and_
import secrets
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, List

from app.core.database import get_db
from app.core import require_merchant
from app.core.config import settings
from app.models.models import Merchant, PaymentLink, PaymentLinkSession, PaymentSession, PaymentStatus
from app.schemas.schemas import (
    PaymentLinkCreate, PaymentLinkUpdate, PaymentLinkResponse, PaymentLinkList
)
from app.services.price_service import PriceService
from app.services.payment_utils import generate_session_id
from app.services.currency_service import get_currency_for_country, convert_usdc_to_local
from app.services.payment_tokenization import auto_tokenize_session

router = APIRouter(prefix="/payment-links", tags=["Payment Links"])
pay_router = APIRouter(prefix="/pay", tags=["Public Payment Links"])

_price_svc = PriceService()


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


# ============= PUBLIC PAYMENT LINK HANDLER =============

@pay_router.get("/{link_id}")
async def open_payment_link(
    link_id: str,
    request: Request,
    amount: Optional[float] = None,
    db: Session = Depends(get_db)
):
    """
    Public endpoint — opens a payment link and creates a checkout session.
    Redirects the payer to the checkout page.
    """
    link = db.query(PaymentLink).filter(PaymentLink.id == link_id).first()
    if not link:
        raise HTTPException(status_code=404, detail="Payment link not found")

    if not link.is_active:
        raise HTTPException(status_code=410, detail="This payment link is no longer active")

    if link.expires_at and datetime.utcnow() > link.expires_at:
        raise HTTPException(status_code=410, detail="This payment link has expired")

    if link.is_single_use and link.payment_count > 0:
        raise HTTPException(status_code=410, detail="This payment link has already been used")

    # Determine fiat amount
    if link.is_amount_fixed:
        fiat_amount = float(link.amount_fiat)
    else:
        if amount is None:
            # Return a minimal HTML form for the customer to enter an amount
            currency = link.fiat_currency or "USD"
            min_val = f' min="{link.min_amount}"' if link.min_amount else ""
            max_val = f' max="{link.max_amount}"' if link.max_amount else ""
            html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{link.name} — Enter Amount</title>
  <style>
    body {{ font-family: system-ui, sans-serif; display: flex; align-items: center;
           justify-content: center; min-height: 100vh; margin: 0; background: #f5f5f5; }}
    .card {{ background: #fff; border-radius: 12px; padding: 2rem; max-width: 380px;
             width: 100%; box-shadow: 0 2px 20px rgba(0,0,0,.1); text-align: center; }}
    h2 {{ margin: 0 0 .5rem; }}
    p {{ color: #666; margin: 0 0 1.5rem; }}
    input {{ width: 100%; padding: .75rem; font-size: 1.1rem; border: 1px solid #ddd;
             border-radius: 8px; box-sizing: border-box; margin-bottom: 1rem; }}
    button {{ width: 100%; padding: .85rem; background: #4f46e5; color: #fff;
              border: none; border-radius: 8px; font-size: 1rem; cursor: pointer; }}
    button:hover {{ background: #4338ca; }}
  </style>
</head>
<body>
  <div class="card">
    <h2>{link.name}</h2>
    { f'<p>{link.description}</p>' if link.description else '<p>Enter the amount to pay</p>' }
    <form method="get" action="/pay/{link_id}">
      <input type="number" name="amount" placeholder="Amount ({currency})"
             step="0.01"{min_val}{max_val} required>
      <button type="submit">Continue to Payment</button>
    </form>
  </div>
</body>
</html>"""
            return HTMLResponse(content=html)

        fiat_amount = amount
        if link.min_amount and fiat_amount < float(link.min_amount):
            raise HTTPException(
                status_code=400,
                detail=f"Amount must be at least {link.min_amount} {link.fiat_currency}"
            )
        if link.max_amount and fiat_amount > float(link.max_amount):
            raise HTTPException(
                status_code=400,
                detail=f"Amount must be at most {link.max_amount} {link.fiat_currency}"
            )

    # Pick default token / chain
    token_symbol = (link.accepted_tokens[0] if link.accepted_tokens else "USDC")
    default_chain = (link.accepted_chains[0] if link.accepted_chains else "stellar")
    fiat_currency = link.fiat_currency or "USD"

    # Convert fiat → token
    try:
        token_amount = await _price_svc.convert_fiat_to_token(
            Decimal(str(fiat_amount)),
            fiat_currency,
            token_symbol
        )
    except Exception:
        token_amount = Decimal(str(fiat_amount))

    # Build fallback URLs
    base_url = str(request.base_url).rstrip("/")
    success_url = link.success_url or base_url
    cancel_url = link.cancel_url or base_url

    # Create checkout session
    session_id = generate_session_id()

    # ── Dual Currency: Merchant side ──
    merchant = db.query(Merchant).filter(Merchant.id == link.merchant_id).first()
    merchant_country = getattr(merchant, 'country', None) if merchant else None
    m_code, m_symbol, _ = get_currency_for_country(merchant_country)
    if merchant and merchant.base_currency and merchant.base_currency != "USD":
        m_code = merchant.base_currency
        m_symbol = getattr(merchant, 'currency_symbol', m_symbol) or m_symbol

    merchant_amount_local = float(fiat_amount)
    merchant_exchange_rate = 1.0
    if m_code != "USD":
        merchant_amount_local, merchant_exchange_rate = await convert_usdc_to_local(
            float(token_amount), m_code
        )

    new_session = PaymentSession(
        id=session_id,
        merchant_id=link.merchant_id,
        amount_fiat=fiat_amount,
        fiat_currency=fiat_currency,
        amount_token=str(token_amount),
        amount_usdc=str(token_amount),
        token=token_symbol,
        chain=default_chain,
        accepted_tokens=link.accepted_tokens,
        accepted_chains=link.accepted_chains,
        status=PaymentStatus.CREATED,
        success_url=success_url,
        cancel_url=cancel_url,
        expires_at=datetime.utcnow() + timedelta(minutes=settings.PAYMENT_EXPIRY_MINUTES),
        session_metadata={"payment_link_id": link.id},
        # Dual currency — merchant
        merchant_currency=m_code,
        merchant_currency_symbol=m_symbol,
        merchant_amount_local=merchant_amount_local,
        merchant_exchange_rate=merchant_exchange_rate,
    )
    db.add(new_session)
    db.flush()  # Persist session row before FK reference in payment_link_sessions

    # Auto-tokenize
    payment_token = auto_tokenize_session(new_session)
    new_session.payment_token = payment_token
    new_session.is_tokenized = True
    new_session.token_created_at = datetime.utcnow()

    # Record the link→session association
    db.add(PaymentLinkSession(payment_link_id=link.id, session_id=session_id))

    # Increment view count
    link.view_count = (link.view_count or 0) + 1

    db.commit()

    return RedirectResponse(url=f"/checkout/{session_id}", status_code=302)
