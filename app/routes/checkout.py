from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from app.core import get_db
from app.core.config import settings
from app.core.cache import cache, make_cache_key
from app.models import PaymentSession, PaymentStatus, MerchantWallet
from app.models.models import PayerInfo
from app.schemas import PaymentSessionDetail
from app.schemas.schemas import PayerDataCollect, PayerDataResponse, TokenizeCheckoutResponse
from app.services.payment_tokenization import (
    create_payment_token, resolve_payment_token, revoke_payment_token, sign_payload,
)
from decimal import Decimal
from stellar_sdk import Keypair
import qrcode
import io
import base64
import json
import logging

router = APIRouter(prefix="/checkout", tags=["Checkout"])
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger(__name__)


def generate_qr_code(data: str) -> str:
    """Generate QR code and return as base64 encoded image."""
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert to base64
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    
    return f"data:image/png;base64,{img_str}"


@router.get("/{session_id}", response_class=HTMLResponse)
async def checkout_page(
    request: Request,
    session_id: str,
    chain: str = None,
    token: str = None,
    db: Session = Depends(get_db)
):
    """Display hosted checkout page."""
    session = db.query(PaymentSession).filter(PaymentSession.id == session_id).first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment session not found"
        )
    
    # Check if already paid
    if session.status == PaymentStatus.PAID:
        return HTMLResponse(content=f"""
        <!DOCTYPE html>
        <html>
        <head><title>Payment Complete</title>
        <meta http-equiv="refresh" content="2;url={session.success_url}">
        </head>
        <body style="font-family:Inter,Arial;text-align:center;padding:50px;background:#0a0e27;color:#fff">
            <h1>✅ Payment Complete!</h1><p>Redirecting to merchant...</p>
        </body></html>
        """)
    
    # Determine expiry using the session's own expires_at (set at creation)
    # If expires_at is missing, compute from created_at
    if session.expires_at:
        expiry_time = session.expires_at
    else:
        expiry_time = session.created_at + timedelta(minutes=settings.PAYMENT_EXPIRY_MINUTES)
    
    is_expired = datetime.utcnow() > expiry_time
    
    # If expired but status not yet marked, mark it now
    if is_expired and session.status not in (PaymentStatus.EXPIRED, PaymentStatus.PAID):
        session.status = PaymentStatus.EXPIRED
        db.commit()
    
    # If session is expired, reset it for re-use (extend expiry by another window)
    if is_expired and session.status == PaymentStatus.EXPIRED:
        session.status = PaymentStatus.CREATED
        session.expires_at = datetime.utcnow() + timedelta(minutes=settings.PAYMENT_EXPIRY_MINUTES)
        expiry_time = session.expires_at
        is_expired = False
        db.commit()
    
    # ── Parse available chains / tokens (handle JSONB strings) ──
    def _parse_json_field(val, default):
        if val:
            if isinstance(val, str):
                try:
                    parsed = json.loads(val)
                    return parsed if isinstance(parsed, list) else default
                except Exception:
                    return default
            if isinstance(val, list):
                return val
        return default

    # Always show all supported chains regardless of DB value
    available_chains = ['stellar', 'ethereum', 'polygon', 'base', 'tron']

    available_tokens = _parse_json_field(
        session.accepted_tokens,
        ['USDC', 'USDT', 'PYUSD']
    )

    # Normalise chain names to lowercase
    available_chains = [c.lower() for c in available_chains]

    # ── Resolve current chain / token (query-param > session > default) ──
    current_chain = (chain or session.chain or available_chains[0]).lower()
    if current_chain not in available_chains:
        current_chain = available_chains[0]

    current_token = (token or session.token or available_tokens[0]).upper()
    if current_token not in [t.upper() for t in available_tokens]:
        current_token = available_tokens[0].upper()

    # ── Static mappings ──
    chain_icons = {
        'stellar': 'S', 'ethereum': 'E', 'polygon': 'P',
        'base': 'B', 'tron': 'T', 'solana': 'So',
    }

    chain_names = {
        'stellar': 'Stellar', 'ethereum': 'Ethereum', 'polygon': 'Polygon',
        'base': 'Base', 'tron': 'Tron', 'solana': 'Solana',
    }

    # Chain logos (CDN SVGs)
    chain_logos = {
        'stellar':  'https://cryptologos.cc/logos/stellar-xlm-logo.svg',
        'ethereum': 'https://cryptologos.cc/logos/ethereum-eth-logo.svg',
        'polygon':  'https://cryptologos.cc/logos/polygon-matic-logo.svg',
        'base':     'https://raw.githubusercontent.com/base-org/brand-kit/main/logo/symbol/Base_Symbol_Blue.svg',
        'tron':     'https://cryptologos.cc/logos/tron-trx-logo.svg',
    }

    currency_symbols = {
        'USD': '$', 'INR': '₹', 'EUR': '€', 'GBP': '£', 'JPY': '¥',
        'AUD': 'A$', 'CAD': 'C$', 'SGD': 'S$', 'AED': 'د.إ',
    }
    fiat = (session.fiat_currency or 'USD').upper()
    # Prefer merchant's stored symbol, fall back to lookup
    merchant_sym = getattr(session.merchant, 'currency_symbol', None) if session.merchant and getattr(session.merchant, 'base_currency', None) == fiat else None
    if merchant_sym:
        currency_symbol = merchant_sym
    else:
        currency_symbol = currency_symbols.get(fiat, fiat + ' ')

    # ── Wallet data per chain (no emojis, use icon URLs or abbreviations) ──
    _wallets = {
        'stellar': [
            {'name': 'Lobstr',    'abbr': 'LO', 'color': '#4361ee', 'bg': '#eef2ff', 'url': 'https://lobstr.co/',            'icon': 'https://lobstr.co/static/images/lobstr-icon.png'},
            {'name': 'Freighter', 'abbr': 'FR', 'color': '#7c3aed', 'bg': '#f5f3ff', 'url': 'https://www.freighter.app/',    'icon': ''},
            {'name': 'Solar',     'abbr': 'SO', 'color': '#f59e0b', 'bg': '#fffbeb', 'url': 'https://solarwallet.io/',        'icon': ''},
            {'name': 'xBull',     'abbr': 'XB', 'color': '#059669', 'bg': '#ecfdf5', 'url': 'https://xbull.app/',             'icon': ''},
        ],
        'ethereum': [
            {'name': 'MetaMask',     'abbr': 'MM', 'color': '#e2761b', 'bg': '#fef3e2', 'url': 'https://metamask.io/',              'icon': 'https://upload.wikimedia.org/wikipedia/commons/3/36/MetaMask_Fox.svg'},
            {'name': 'Coinbase',     'abbr': 'CB', 'color': '#0052ff', 'bg': '#eff6ff', 'url': 'https://www.coinbase.com/wallet',   'icon': ''},
            {'name': 'Trust Wallet', 'abbr': 'TW', 'color': '#3375bb', 'bg': '#eef5ff', 'url': 'https://trustwallet.com/',          'icon': ''},
            {'name': 'Rainbow',      'abbr': 'RB', 'color': '#e040fb', 'bg': '#fdf2ff', 'url': 'https://rainbow.me/',               'icon': ''},
        ],
        'polygon': [
            {'name': 'MetaMask',     'abbr': 'MM', 'color': '#e2761b', 'bg': '#fef3e2', 'url': 'https://metamask.io/',              'icon': 'https://upload.wikimedia.org/wikipedia/commons/3/36/MetaMask_Fox.svg'},
            {'name': 'Coinbase',     'abbr': 'CB', 'color': '#0052ff', 'bg': '#eff6ff', 'url': 'https://www.coinbase.com/wallet',   'icon': ''},
            {'name': 'Trust Wallet', 'abbr': 'TW', 'color': '#3375bb', 'bg': '#eef5ff', 'url': 'https://trustwallet.com/',          'icon': ''},
        ],
        'base': [
            {'name': 'Coinbase',     'abbr': 'CB', 'color': '#0052ff', 'bg': '#eff6ff', 'url': 'https://www.coinbase.com/wallet',   'icon': ''},
            {'name': 'MetaMask',     'abbr': 'MM', 'color': '#e2761b', 'bg': '#fef3e2', 'url': 'https://metamask.io/',              'icon': 'https://upload.wikimedia.org/wikipedia/commons/3/36/MetaMask_Fox.svg'},
            {'name': 'Rainbow',      'abbr': 'RB', 'color': '#e040fb', 'bg': '#fdf2ff', 'url': 'https://rainbow.me/',               'icon': ''},
        ],
        'tron': [
            {'name': 'TronLink',     'abbr': 'TL', 'color': '#e53935', 'bg': '#fef2f2', 'url': 'https://www.tronlink.org/',         'icon': ''},
            {'name': 'Trust Wallet', 'abbr': 'TW', 'color': '#3375bb', 'bg': '#eef5ff', 'url': 'https://trustwallet.com/',          'icon': ''},
            {'name': 'TokenPocket',  'abbr': 'TP', 'color': '#2979ff', 'bg': '#e3f2fd', 'url': 'https://www.tokenpocket.pro/',      'icon': ''},
        ],
    }

    # Build structured chain list for the sidebar
    all_chains = []
    for cid in available_chains:
        all_chains.append({
            'id': cid,
            'name': chain_names.get(cid, cid.title()),
            'logo': chain_logos.get(cid, ''),
            'wallets': _wallets.get(cid, []),
        })

    current_chain_wallets = _wallets.get(current_chain, [])

    # Recommended wallet per chain
    _rec = {
        'stellar':  {'abbr': 'LO', 'label': 'Lobstr - Stellar Wallet',  'bg': '#eef2ff', 'url': 'https://lobstr.co/',            'icon': 'https://lobstr.co/static/images/lobstr-icon.png'},
        'ethereum': {'abbr': 'MM', 'label': 'MetaMask - Ethereum',      'bg': '#fef3e2', 'url': 'https://metamask.io/',           'icon': 'https://upload.wikimedia.org/wikipedia/commons/3/36/MetaMask_Fox.svg'},
        'polygon':  {'abbr': 'MM', 'label': 'MetaMask - Polygon',       'bg': '#fef3e2', 'url': 'https://metamask.io/',           'icon': 'https://upload.wikimedia.org/wikipedia/commons/3/36/MetaMask_Fox.svg'},
        'base':     {'abbr': 'CB', 'label': 'Coinbase Wallet - Base',   'bg': '#eff6ff', 'url': 'https://www.coinbase.com/wallet','icon': ''},
        'tron':     {'abbr': 'TL', 'label': 'TronLink - Tron Wallet',   'bg': '#fef2f2', 'url': 'https://www.tronlink.org/',      'icon': ''},
    }
    recommended_wallet = _rec.get(current_chain, _rec['ethereum'])

    # ── Payment address (look up from MerchantWallet first, fall back to legacy stellar_address) ──
    payment_address = ''
    merchant_wallet_record = db.query(MerchantWallet).filter(
        MerchantWallet.merchant_id == session.merchant_id,
        MerchantWallet.is_active == True,
    ).all()

    # Try to find wallet for the selected chain
    for mw in merchant_wallet_record:
        chain_val = mw.chain.value if hasattr(mw.chain, 'value') else str(mw.chain)
        if chain_val == current_chain:
            payment_address = mw.wallet_address
            break

    # Fall back to legacy stellar_address for stellar chain
    if not payment_address and current_chain == 'stellar' and session.merchant.stellar_address:
        payment_address = session.merchant.stellar_address

    # If still no address, try any available wallet and switch chain
    if not payment_address:
        for mw in merchant_wallet_record:
            if mw.wallet_address:
                payment_address = mw.wallet_address
                current_chain = mw.chain.value if hasattr(mw.chain, 'value') else str(mw.chain)
                break

    # Last resort: legacy stellar_address
    if not payment_address and session.merchant.stellar_address:
        payment_address = session.merchant.stellar_address
        current_chain = 'stellar'

    if not payment_address:
        return HTMLResponse(content="""
        <html><body style="font-family:Inter,Arial;text-align:center;padding:50px;background:#0a0e27;color:#fff">
        <h1>⚠️ Configuration Error</h1><p>Merchant wallet not configured. Please add a wallet in your dashboard.</p>
        </body></html>""", status_code=500)

    # ── Token amount ──
    amount_usdc = session.amount_usdc or '0'
    amount_token_val = session.amount_token or amount_usdc

    # ── Network details (Chain ID, Contracts) ──
    is_testnet = settings.STELLAR_NETWORK == 'testnet'
    network_name = f"{chain_names.get(current_chain, current_chain.title())} {'Testnet' if is_testnet else 'Mainnet'}"
    
    memo_required = current_chain == 'stellar'
    token_contract = None
    asset_issuer = None
    chain_id = None
    decimals = 6  # Default for USDC/USDT/PYUSD

    if current_chain == 'stellar':
        if current_token == 'USDC':
            asset_issuer = settings.USDC_ASSET_ISSUER
            
    elif current_chain == 'ethereum':
        chain_id = settings.ETHEREUM_CHAIN_ID
        if current_token == 'USDC':
            token_contract = settings.ETHEREUM_USDC_ADDRESS
        elif current_token == 'USDT':
            token_contract = settings.ETHEREUM_USDT_ADDRESS
            
    elif current_chain == 'polygon':
        chain_id = settings.POLYGON_CHAIN_ID
        if current_token == 'USDC':
            token_contract = settings.POLYGON_USDC_ADDRESS
        elif current_token == 'USDT':
            token_contract = settings.POLYGON_USDT_ADDRESS

    elif current_chain == 'base':
        chain_id = settings.BASE_CHAIN_ID
        if current_token == 'USDC':
            token_contract = settings.BASE_USDC_ADDRESS
            
    elif current_chain == 'tron':
        if current_token == 'USDT':
            token_contract = settings.TRON_USDT_ADDRESS
        elif current_token == 'USDC':
            token_contract = getattr(settings, 'TRON_USDC_ADDRESS', None)

    # ── QR Code Data Generation (EIP-681 for EVM) ──
    qr_data = payment_address  # Default fallback
    dari_qr_data = None  # Dari App specific QR with merchant param

    try:
        if current_chain in ['ethereum', 'polygon', 'base'] and token_contract and chain_id:
            # EIP-681 Format: ethereum:<contract_address>@<chain_id>/transfer?address=<recipient_address>&uint256=<amount>
            # Amount in atomic units (wei)
            amount_wei = int(Decimal(str(amount_token_val)) * (10 ** decimals))
            qr_data = f"ethereum:{token_contract}@{chain_id}/transfer?address={payment_address}&uint256={amount_wei}"
            logger.info(f"Generated EIP-681 QR: {qr_data}")

    except Exception as e:
        logger.error(f"Error generating payment URI: {e}")
        qr_data = payment_address  # Fallback on error

    # ── Dari App QR — always generate using Polygon USDC with merchant name ──
    try:
        polygon_usdc_contract = settings.POLYGON_USDC_ADDRESS
        polygon_chain_id = settings.POLYGON_CHAIN_ID
        dari_amount_wei = int(Decimal(str(amount_token_val)) * (10 ** 6))
        merchant_name_safe = (session.merchant.name or 'Merchant').replace(' ', '%20')
        dari_qr_data = f"ethereum:{polygon_usdc_contract}@{polygon_chain_id}/transfer?address={payment_address}&uint256={dari_amount_wei}&merchant={merchant_name_safe}"
        logger.info(f"Generated Dari App QR: {dari_qr_data}")
    except Exception as e:
        logger.error(f"Error generating Dari App URI: {e}")

    # ── QR code image (standard) ──
    qr = qrcode.QRCode(version=1, box_size=8, border=4)
    qr.add_data(qr_data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qr_code_b64 = f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"

    # ── Dari App QR code image ──
    dari_qr_b64 = None
    if dari_qr_data:
        qr2 = qrcode.QRCode(version=1, box_size=8, border=4)
        qr2.add_data(dari_qr_data)
        qr2.make(fit=True)
        img2 = qr2.make_image(fill_color="black", back_color="white")
        buf2 = io.BytesIO()
        img2.save(buf2, format="PNG")
        dari_qr_b64 = f"data:image/png;base64,{base64.b64encode(buf2.getvalue()).decode()}"

    # ── Check if payer already submitted data ──
    payer_exists = db.query(PayerInfo).filter(PayerInfo.session_id == session_id).first() is not None

    # ── Render ──
    return templates.TemplateResponse("checkout.html", {
        "request": request,
        "session_id": session_id,
        "merchant_name": session.merchant.name or "Merchant",
        "amount_fiat": str(session.amount_fiat),
        "fiat_currency": fiat,
        "currency_symbol": currency_symbol,
        "amount_token": str(amount_token_val),
        "token": current_token,
        "payment_address": payment_address,
        "current_chain": current_chain,
        "chain_name": chain_names.get(current_chain, current_chain.title()),
        "all_chains": all_chains,
        "available_tokens": available_tokens,
        "chain_icons": chain_icons,
        "chain_names": chain_names,
        "current_chain_wallets": current_chain_wallets,
        "recommended_wallet": recommended_wallet,
        "qr_code_b64": qr_code_b64,
        "token_contract": token_contract,
        "asset_issuer": asset_issuer,
        "memo_required": memo_required,
        "network_name": network_name,
        "success_url": session.success_url or "/",
        "cancel_url": session.cancel_url or "/",
        "expires_at": expiry_time.isoformat() + "Z",
        "collect_payer_data": bool(session.collect_payer_data),
        "payer_data_submitted": payer_exists,
        "merchant_id": str(session.merchant_id),
        "dari_qr_b64": dari_qr_b64,
        "show_dari": dari_qr_b64 is not None,
    })


@router.get("/api/{session_id}", response_model=PaymentSessionDetail)
async def get_checkout_details(
    session_id: str,
    db: Session = Depends(get_db)
):
    """Get checkout details as JSON (for frontend integration)."""
    session = db.query(PaymentSession).filter(PaymentSession.id == session_id).first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment session not found"
        )
    
    return PaymentSessionDetail(
        id=session.id,
        merchant_name=session.merchant.name,
        merchant_stellar_address=session.merchant.stellar_address,
        amount_fiat=session.amount_fiat,
        fiat_currency=session.fiat_currency,
        amount_usdc=session.amount_usdc,
        status=session.status.value,
        success_url=session.success_url,
        cancel_url=session.cancel_url,
        tx_hash=session.tx_hash,
        created_at=session.created_at,
        paid_at=session.paid_at
    )


# ============= PAYER DATA COLLECTION =============

@router.post("/{session_id}/payer-data", response_model=PayerDataResponse)
async def submit_payer_data(
    session_id: str,
    data: PayerDataCollect,
    db: Session = Depends(get_db),
):
    """
    Collect payer data before showing the payment screen.
    Called by the checkout page after the customer fills in their details.
    """
    session = db.query(PaymentSession).filter(PaymentSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Payment session not found")
    if session.status == PaymentStatus.PAID:
        raise HTTPException(status_code=400, detail="Payment already completed")

    # Upsert payer info
    payer = db.query(PayerInfo).filter(PayerInfo.session_id == session_id).first()
    if not payer:
        payer = PayerInfo(session_id=session_id, merchant_id=session.merchant_id)
        db.add(payer)

    for field in [
        "email", "name", "phone",
        "billing_address_line1", "billing_address_line2",
        "billing_city", "billing_state", "billing_postal_code", "billing_country",
        "shipping_address_line1", "shipping_city", "shipping_state",
        "shipping_postal_code", "shipping_country", "custom_fields",
    ]:
        val = getattr(data, field, None)
        if val is not None:
            setattr(payer, field, val)

    # Also store contact on the session for quick access
    if data.email:
        session.payer_email = data.email
    if data.name:
        session.payer_name = data.name

    db.commit()
    db.refresh(payer)

    return PayerDataResponse(
        email=payer.email, name=payer.name, phone=payer.phone,
        billing_address_line1=payer.billing_address_line1,
        billing_city=payer.billing_city, billing_state=payer.billing_state,
        billing_postal_code=payer.billing_postal_code,
        billing_country=payer.billing_country,
        custom_fields=payer.custom_fields,
    )


# ============= PAYMENT TOKENIZATION =============

@router.post("/{session_id}/tokenize", response_model=TokenizeCheckoutResponse)
async def tokenize_checkout(
    session_id: str,
    db: Session = Depends(get_db),
):
    """
    Tokenize a checkout session so the frontend only transmits an
    opaque token instead of raw payment data.
    """
    session = db.query(PaymentSession).filter(PaymentSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Payment session not found")
    if session.status == PaymentStatus.PAID:
        raise HTTPException(status_code=400, detail="Payment already completed")

    # Build the sensitive payload that gets tokenized
    payload = {
        "session_id": session.id,
        "amount_fiat": str(session.amount_fiat),
        "fiat_currency": session.fiat_currency,
        "amount_token": session.amount_token or session.amount_usdc or "0",
        "token": session.token or "USDC",
        "chain": session.chain or "stellar",
        "merchant_id": str(session.merchant_id),
    }

    token = create_payment_token(session.id, payload)
    sig = sign_payload({"payment_token": token, "session_id": session.id})

    # Store token reference on the session
    session.payment_token = token
    db.commit()

    return TokenizeCheckoutResponse(
        payment_token=token,
        expires_in_seconds=settings.PAYMENT_EXPIRY_MINUTES * 60,
        signature=sig,
    )


@router.get("/{session_id}/resolve-token")
async def resolve_token(
    session_id: str,
    token: str,
    db: Session = Depends(get_db),
):
    """
    Resolve a payment token back to real checkout data.
    Only used server-side or by trusted frontends.
    """
    data = resolve_payment_token(token)
    if not data or data.get("session_id") != session_id:
        raise HTTPException(status_code=404, detail="Invalid or expired payment token")
    return data
