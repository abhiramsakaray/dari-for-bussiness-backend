from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import uuid
from app.core import get_db, require_merchant
from app.core.config import settings
from app.models import Merchant, PaymentSession, PaymentStatus
from app.schemas import PaymentSessionCreate, PaymentSessionResponse, PaymentSessionStatus
from app.services.payment_utils import generate_session_id, convert_fiat_to_usdc
from app.services.currency_service import get_currency_for_country, convert_usdc_to_local
from app.services.payment_tokenization import auto_tokenize_session
from decimal import Decimal

router = APIRouter(prefix="/v1/payment_sessions", tags=["Payment Sessions"])


@router.post("", response_model=PaymentSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_payment_session(
    session_data: PaymentSessionCreate,
    current_user: dict = Depends(require_merchant),
    db: Session = Depends(get_db)
):
    """Create a new payment session (merchant only)."""
    # Get merchant details
    merchant = db.query(Merchant).filter(Merchant.id == uuid.UUID(current_user["id"])).first()
    
    if not merchant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Merchant not found"
        )
    
    if not merchant.stellar_address:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Merchant must set Stellar address before creating payment sessions"
        )
    
    # Generate session ID
    session_id = generate_session_id()
    
    # Convert fiat to USDC
    resolved_currency = (session_data.currency or merchant.base_currency).upper()
    amount_usdc = convert_fiat_to_usdc(session_data.amount, resolved_currency)
    
    # ── Dual Currency: Merchant side ──
    merchant_country = getattr(merchant, 'country', None)
    m_code, m_symbol, _ = get_currency_for_country(merchant_country)
    if merchant.base_currency and merchant.base_currency != "USD":
        m_code = merchant.base_currency
        m_symbol = getattr(merchant, 'currency_symbol', m_symbol) or m_symbol
    
    merchant_amount_local = float(session_data.amount)
    merchant_exchange_rate = 1.0
    if m_code != "USD":
        merchant_amount_local, merchant_exchange_rate = await convert_usdc_to_local(
            float(amount_usdc), m_code
        )
    
    # Create payment session
    new_session = PaymentSession(
        id=session_id,
        merchant_id=merchant.id,
        amount_fiat=session_data.amount,
        fiat_currency=resolved_currency,
        amount_usdc=amount_usdc,
        status=PaymentStatus.CREATED,
        success_url=str(session_data.success_url),
        cancel_url=str(session_data.cancel_url),
        # Dual currency — merchant
        merchant_currency=m_code,
        merchant_currency_symbol=m_symbol,
        merchant_amount_local=merchant_amount_local,
        merchant_exchange_rate=merchant_exchange_rate,
    )
    
    db.add(new_session)
    db.flush()
    
    # Auto-tokenize
    payment_token = auto_tokenize_session(new_session)
    new_session.payment_token = payment_token
    new_session.is_tokenized = True
    new_session.token_created_at = datetime.utcnow()
    
    db.commit()
    
    # Generate checkout URL
    checkout_url = f"{settings.APP_BASE_URL}/checkout/{session_id}"
    
    return PaymentSessionResponse(
        session_id=session_id,
        checkout_url=checkout_url
    )


@router.get("/{session_id}", response_model=PaymentSessionStatus)
async def get_payment_session_status(
    session_id: str,
    db: Session = Depends(get_db)
):
    """Get payment session status (public endpoint)."""
    session = db.query(PaymentSession).filter(PaymentSession.id == session_id).first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment session not found"
        )
    
    # Check if session has expired
    expiry_time = session.created_at + timedelta(minutes=settings.PAYMENT_EXPIRY_MINUTES)
    if session.status == PaymentStatus.CREATED and datetime.utcnow() > expiry_time:
        session.status = PaymentStatus.EXPIRED
        db.commit()
    
    return PaymentSessionStatus(
        session_id=session.id,
        status=session.status.value,
        amount_usdc=session.amount_usdc,
        tx_hash=session.tx_hash,
        created_at=session.created_at,
        paid_at=session.paid_at
    )
