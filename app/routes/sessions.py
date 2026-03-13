from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional, List
from decimal import Decimal
from app.core import get_db
from app.core.config import settings
from app.models import Merchant, PaymentSession, PaymentStatus, MerchantWallet
from app.schemas import (
    PaymentSessionCreate, PaymentSessionResponse, PaymentSessionStatus,
    PaymentSessionDetail, PaymentOption, SelectPaymentMethod
)
from app.services.payment_utils import generate_session_id
from app.services.token_registry import get_token_registry
from app.services.price_service import get_price_service
from app.services.currency_service import get_currency_for_country, convert_usdc_to_local
from app.services.payment_tokenization import auto_tokenize_session, sign_payload
from app.core.auth import get_api_key
from app.core.security_middleware import compute_risk_score
import logging
import json

router = APIRouter(prefix="/api/sessions", tags=["Payment Sessions - Public API"])
logger = logging.getLogger(__name__)


@router.post("/create", response_model=PaymentSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_payment_session_public(
    session_data: PaymentSessionCreate,
    api_key: str = Depends(get_api_key),
    db: Session = Depends(get_db)
):
    """
    Create a new payment session with multi-chain support.
    
    This endpoint is used by merchant websites and SDKs to create payment sessions.
    Supports multiple stablecoins (USDC, USDT, PYUSD) across multiple chains
    (Stellar, Ethereum, Polygon, Base, Tron).
    
    Example request body:
    ```json
    {
        "amount": 50.00,
        "currency": "USD",
        "accepted_tokens": ["USDC", "USDT", "PYUSD"],
        "accepted_chains": ["polygon", "ethereum", "stellar", "tron"],
        "order_id": "ORDER-12345",
        "success_url": "https://yourstore.com/success",
        "cancel_url": "https://yourstore.com/cart",
        "metadata": {
            "customer_email": "customer@example.com"
        }
    }
    ```
    
    Response includes checkout_url where customer selects payment method.
    """
    # Get merchant from API key
    merchant = db.query(Merchant).filter(Merchant.api_key == api_key).first()
    
    if not merchant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Merchant not found"
        )
    
    # Get amount (support both new and legacy format)
    amount = session_data.amount if session_data.amount else session_data.amount_usdc
    if not amount or amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Amount must be greater than 0"
        )
    
    currency = session_data.currency or merchant.base_currency or "USD"
    
    # Get accepted tokens and chains (with merchant defaults fallback)
    accepted_tokens = session_data.accepted_tokens or merchant.accepted_tokens or ["USDC", "USDT"]
    accepted_chains = session_data.accepted_chains or merchant.accepted_chains or ["stellar", "polygon"]
    
    # Validate merchant has wallets for requested chains
    merchant_wallets = db.query(MerchantWallet).filter(
        MerchantWallet.merchant_id == merchant.id,
        MerchantWallet.is_active == True
    ).all()
    
    available_chains = {w.chain.value if hasattr(w.chain, 'value') else str(w.chain) for w in merchant_wallets}
    
    # Include legacy stellar_address
    if merchant.stellar_address:
        available_chains.add("stellar")
    
    # Filter accepted_chains to only those with configured wallets
    valid_chains = [c for c in accepted_chains if c in available_chains]
    
    if not valid_chains:
        logger.warning(f"Merchant {merchant.email} has no wallets configured for chains: {accepted_chains}")
        # Fall back to stellar if available
        if merchant.stellar_address:
            valid_chains = ["stellar"]
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No wallets configured for requested chains. Please configure wallets first."
            )
    
    # Generate session ID
    session_id = generate_session_id()
    
    # Convert amount to token equivalent
    price_service = get_price_service()
    token_amount = await price_service.convert_fiat_to_token(
        Decimal(str(amount)),
        currency,
        "USDC"  # Use USDC as reference
    )
    
    # ── Dual Currency: Merchant side ──
    merchant_country = getattr(merchant, 'country', None)
    m_code, m_symbol, _ = get_currency_for_country(merchant_country)
    # Use merchant's configured base_currency if set
    if merchant.base_currency and merchant.base_currency != "USD":
        m_code = merchant.base_currency
        m_symbol = getattr(merchant, 'currency_symbol', m_symbol) or m_symbol

    merchant_amount_local = None
    merchant_exchange_rate = None
    if m_code != "USD":
        merchant_amount_local, merchant_exchange_rate = await convert_usdc_to_local(
            float(token_amount), m_code
        )
    else:
        merchant_amount_local = float(amount)
        merchant_exchange_rate = 1.0

    # ── Dual Currency: Payer side ──
    payer_currency_code = None
    payer_currency_symbol = None
    payer_amount_local = None
    payer_exchange_rate = None
    payer_country = session_data.payer_country
    is_cross_border = False

    if session_data.payer_currency:
        payer_currency_code = session_data.payer_currency.upper()
        p_info = None
        # Look up symbol from country map if country provided
        if payer_country:
            _, p_sym, _ = get_currency_for_country(payer_country)
            payer_currency_symbol = p_sym
        else:
            payer_currency_symbol = payer_currency_code
        if payer_currency_code != "USD":
            payer_amount_local, payer_exchange_rate = await convert_usdc_to_local(
                float(token_amount), payer_currency_code
            )
        else:
            payer_amount_local = float(amount)
            payer_exchange_rate = 1.0
    elif payer_country:
        p_code, p_sym, _ = get_currency_for_country(payer_country)
        payer_currency_code = p_code
        payer_currency_symbol = p_sym
        if p_code != "USD":
            payer_amount_local, payer_exchange_rate = await convert_usdc_to_local(
                float(token_amount), p_code
            )
        else:
            payer_amount_local = float(amount)
            payer_exchange_rate = 1.0

    # Cross-border detection
    if payer_country and merchant_country:
        is_cross_border = payer_country.strip().lower() != merchant_country.strip().lower()
    elif payer_currency_code and m_code:
        is_cross_border = payer_currency_code != m_code

    # ── Risk scoring ──
    risk_score, risk_flags = compute_risk_score(
        amount_usd=float(amount),
        payer_country=payer_country,
        merchant_country=merchant_country,
        is_cross_border=is_cross_border,
    )

    # Create payment session
    new_session = PaymentSession(
        id=session_id,
        merchant_id=merchant.id,
        amount_fiat=amount,
        fiat_currency=currency,
        amount_token=str(token_amount),
        amount_usdc=str(token_amount),  # Backward compatibility
        accepted_tokens=accepted_tokens,
        accepted_chains=valid_chains,
        order_id=session_data.order_id,
        session_metadata=session_data.metadata,
        collect_payer_data=session_data.collect_payer_data,
        status=PaymentStatus.CREATED,
        success_url=str(session_data.success_url) if session_data.success_url else "",
        cancel_url=str(session_data.cancel_url) if session_data.cancel_url else "",
        expires_at=datetime.utcnow() + timedelta(minutes=settings.PAYMENT_EXPIRY_MINUTES),
        # Dual currency — merchant
        merchant_currency=m_code,
        merchant_currency_symbol=m_symbol,
        merchant_amount_local=merchant_amount_local,
        merchant_exchange_rate=merchant_exchange_rate,
        # Dual currency — payer
        payer_currency=payer_currency_code,
        payer_currency_symbol=payer_currency_symbol,
        payer_amount_local=payer_amount_local,
        payer_exchange_rate=payer_exchange_rate,
        payer_country=payer_country,
        # Cross-border
        is_cross_border=is_cross_border,
        # Risk
        risk_score=risk_score,
        risk_flags=risk_flags if risk_flags else None,
    )
    
    db.add(new_session)
    db.flush()
    
    # ── Auto-tokenize every session ──
    payment_token = auto_tokenize_session(new_session)
    new_session.payment_token = payment_token
    new_session.is_tokenized = True
    new_session.token_created_at = datetime.utcnow()
    
    db.commit()
    db.refresh(new_session)
    
    logger.info(f"✅ Created session {session_id} for {amount} {currency} ({token_amount} tokens) [tokenized]")
    
    # Generate checkout URL
    checkout_url = f"{settings.APP_URL}/checkout/{new_session.id}"
    
    return PaymentSessionResponse(
        session_id=new_session.id,
        checkout_url=checkout_url,
        amount=amount,
        currency=currency,
        accepted_tokens=accepted_tokens,
        accepted_chains=valid_chains,
        order_id=session_data.order_id,
        expires_at=new_session.expires_at,
        status=new_session.status.value,
        amount_usdc=token_amount,  # Backward compatibility
        success_url=new_session.success_url,
        cancel_url=new_session.cancel_url,
        # Dual currency
        payer_currency=payer_currency_code,
        payer_amount_local=Decimal(str(payer_amount_local)) if payer_amount_local else None,
        merchant_currency=m_code,
        merchant_amount_local=Decimal(str(merchant_amount_local)) if merchant_amount_local else None,
        is_cross_border=is_cross_border,
        # Tokenization
        payment_token=payment_token,
        is_tokenized=True,
    )


@router.get("/{session_id}", response_model=PaymentSessionStatus)
async def get_payment_session_public(
    session_id: str,
    api_key: Optional[str] = Depends(get_api_key),
    db: Session = Depends(get_db)
):
    """
    Get payment session status with multi-chain details.
    
    Returns session status including selected chain and token if payment was made.
    """
    session = db.query(PaymentSession).filter(PaymentSession.id == session_id).first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment session not found"
        )
    
    # Verify API key belongs to the merchant who created the session
    if api_key:
        merchant = db.query(Merchant).filter(Merchant.api_key == api_key).first()
        if merchant and merchant.id != session.merchant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
    
    # Check if session has expired
    if session.expires_at and datetime.utcnow() > session.expires_at:
        if session.status == PaymentStatus.CREATED:
            session.status = PaymentStatus.EXPIRED
            db.commit()
    
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
        amount_usdc=session.amount_usdc,  # Backward compatibility
        metadata=session.session_metadata,
        # Dual currency
        payer_currency=session.payer_currency,
        payer_currency_symbol=session.payer_currency_symbol,
        payer_amount_local=float(session.payer_amount_local) if session.payer_amount_local else None,
        payer_exchange_rate=float(session.payer_exchange_rate) if session.payer_exchange_rate else None,
        merchant_currency=session.merchant_currency,
        merchant_currency_symbol=session.merchant_currency_symbol,
        merchant_amount_local=float(session.merchant_amount_local) if session.merchant_amount_local else None,
        merchant_exchange_rate=float(session.merchant_exchange_rate) if session.merchant_exchange_rate else None,
        is_cross_border=session.is_cross_border or False,
        is_tokenized=session.is_tokenized or False,
        risk_score=float(session.risk_score) if session.risk_score else None,
    )


@router.get("/{session_id}/options", response_model=List[PaymentOption])
async def get_payment_options(
    session_id: str,
    db: Session = Depends(get_db)
):
    """
    Get available payment options for a session.
    
    Returns list of token/chain combinations the customer can use to pay.
    Each option includes the wallet address and amount.
    """
    session = db.query(PaymentSession).filter(PaymentSession.id == session_id).first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment session not found"
        )
    
    # Check session validity
    if session.status != PaymentStatus.CREATED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Session is {session.status.value}"
        )
    
    if session.expires_at and datetime.utcnow() > session.expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session has expired"
        )
    
    merchant = session.merchant
    token_registry = get_token_registry()
    
    # Get merchant wallets
    merchant_wallets = {
        (w.chain.value if hasattr(w.chain, 'value') else str(w.chain)): w.wallet_address
        for w in merchant.wallets if w.is_active
    }
    
    # Add legacy stellar address
    if merchant.stellar_address:
        merchant_wallets["stellar"] = merchant.stellar_address
    
    # Build payment options
    options = []
    accepted_tokens = session.accepted_tokens or ["USDC"]
    accepted_chains = session.accepted_chains or ["stellar"]
    
    for chain in accepted_chains:
        wallet_address = merchant_wallets.get(chain)
        if not wallet_address:
            continue
            
        for token_symbol in accepted_tokens:
            token = token_registry.get_token(chain, token_symbol)
            if not token or not token.is_active:
                continue
            
            # Calculate amount for this token
            amount = session.amount_token or session.amount_usdc
            
            options.append(PaymentOption(
                token=token_symbol,
                chain=chain,
                chain_display=token_registry._get_chain_display_name(chain),
                wallet_address=wallet_address,
                amount=str(amount),
                label=f"{token_symbol} ({chain.capitalize()})",
                icon_url=token.icon_url,
                memo=session.id if chain == "stellar" else None
            ))
    
    return options


@router.post("/{session_id}/select", response_model=PaymentSessionDetail)
async def select_payment_method(
    session_id: str,
    selection: SelectPaymentMethod,
    db: Session = Depends(get_db)
):
    """
    Select payment method for a session.
    
    Customer selects which token/chain combination to use for payment.
    Returns updated session with payment address and amount.
    """
    session = db.query(PaymentSession).filter(PaymentSession.id == session_id).first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment session not found"
        )
    
    # Validate session status
    if session.status != PaymentStatus.CREATED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Session is {session.status.value}"
        )
    
    # Validate token/chain combination
    token_registry = get_token_registry()
    token = token_registry.get_token(selection.chain, selection.token)
    
    if not token or not token.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{selection.token} is not available on {selection.chain}"
        )
    
    # Validate against accepted options
    if session.accepted_tokens and selection.token not in session.accepted_tokens:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{selection.token} is not accepted for this payment"
        )
    
    if session.accepted_chains and selection.chain not in session.accepted_chains:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{selection.chain} is not accepted for this payment"
        )
    
    # Get merchant wallet for selected chain
    merchant = session.merchant
    wallet_address = None
    
    for wallet in merchant.wallets:
        chain_value = wallet.chain.value if hasattr(wallet.chain, 'value') else str(wallet.chain)
        if chain_value == selection.chain and wallet.is_active:
            wallet_address = wallet.wallet_address
            break
    
    # Fallback to legacy stellar address
    if not wallet_address and selection.chain == "stellar" and merchant.stellar_address:
        wallet_address = merchant.stellar_address
    
    if not wallet_address:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Merchant has no wallet configured for {selection.chain}"
        )
    
    # Update session with selected method
    session.token = selection.token
    session.chain = selection.chain
    session.merchant_wallet = wallet_address
    
    db.commit()
    db.refresh(session)
    
    logger.info(f"Session {session_id} selected {selection.token} on {selection.chain}")
    
    return PaymentSessionDetail(
        id=session.id,
        merchant_name=merchant.name,
        amount_fiat=session.amount_fiat,
        fiat_currency=session.fiat_currency,
        status=session.status.value,
        success_url=session.success_url,
        cancel_url=session.cancel_url,
        tx_hash=session.tx_hash,
        created_at=session.created_at,
        paid_at=session.paid_at,
        expires_at=session.expires_at,
        accepted_tokens=session.accepted_tokens,
        accepted_chains=session.accepted_chains,
        selected_token=session.token,
        selected_chain=session.chain,
        payment_address=wallet_address,
        payment_amount=session.amount_token or session.amount_usdc,
        payment_memo=session.id if selection.chain == "stellar" else None,
        merchant_stellar_address=merchant.stellar_address,
        amount_usdc=session.amount_usdc
    )


@router.post("/{session_id}/cancel", status_code=status.HTTP_200_OK)
async def cancel_payment_session(
    session_id: str,
    api_key: str = Depends(get_api_key),
    db: Session = Depends(get_db)
):
    """
    Cancel a payment session.
    
    Only sessions with status 'created' can be cancelled.
    """
    session = db.query(PaymentSession).filter(PaymentSession.id == session_id).first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment session not found"
        )
    
    # Verify ownership
    merchant = db.query(Merchant).filter(Merchant.api_key == api_key).first()
    if not merchant or merchant.id != session.merchant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    if session.status != PaymentStatus.CREATED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel session with status: {session.status.value}"
        )
    
    session.status = PaymentStatus.EXPIRED
    db.commit()
    
    return {"message": "Session cancelled", "session_id": session_id}


@router.get("/{session_id}/status", response_model=PaymentSessionStatus)
async def get_session_status_public(
    session_id: str,
    db: Session = Depends(get_db)
):
    """
    Get session status (public endpoint, no authentication required).
    
    Allows checkout page to poll for payment status.
    """
    session = db.query(PaymentSession).filter(PaymentSession.id == session_id).first()
    
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
        amount_usdc=session.amount_usdc
    )
