"""
Merchant Onboarding Routes
Simplified onboarding flow: Signup → Business Details → Wallet Setup → Dashboard
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.orm import Session
import secrets
import logging

from app.core import get_db, get_current_user, settings
from app.core.security import create_access_token
from app.models import Merchant, MerchantWallet, BlockchainNetwork
from app.schemas import (
    OnboardingBusinessDetails,
    OnboardingWalletSetup,
    OnboardingCompleteRequest,
    OnboardingStatusResponse,
    OnboardingCompleteResponse,
    MerchantWalletResponse,
)
from app.services.currency_service import get_currency_for_country

router = APIRouter(prefix="/onboarding", tags=["Onboarding"])
logger = logging.getLogger(__name__)

# ============= DEFAULT CHAINS & TOKENS =============

DEFAULT_CHAINS = ["stellar", "ethereum", "polygon", "base", "tron"]
DEFAULT_TOKENS = ["USDC", "USDT", "PYUSD"]


def generate_api_key() -> str:
    """Generate a secure API key for merchant."""
    return f"pk_live_{secrets.token_urlsafe(32)}"


# ============= ONBOARDING STATUS =============

@router.get("/status", response_model=OnboardingStatusResponse)
async def get_onboarding_status(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current onboarding progress for the authenticated merchant."""
    merchant = db.query(Merchant).filter(Merchant.id == current_user["id"]).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    wallet_count = db.query(MerchantWallet).filter(
        MerchantWallet.merchant_id == merchant.id,
        MerchantWallet.is_active == True,
    ).count()

    return OnboardingStatusResponse(
        step=merchant.onboarding_step or 0,
        onboarding_completed=merchant.onboarding_completed or False,
        merchant_id=str(merchant.id),
        name=merchant.name,
        email=merchant.email,
        merchant_category=merchant.merchant_category,
        business_name=merchant.business_name,
        business_email=merchant.business_email,
        country=merchant.country,
        base_currency=merchant.base_currency or "USD",
        currency_symbol=merchant.currency_symbol or "$",
        currency_name=merchant.currency_name or "US Dollar",
        has_wallets=wallet_count > 0,
        wallet_count=wallet_count,
    )


# ============= STEP 1: BUSINESS DETAILS =============

@router.post("/business-details", response_model=OnboardingStatusResponse)
async def set_business_details(
    details: OnboardingBusinessDetails,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Step 1: Provide business details.
    Called after signup (email/password or Google OAuth).
    """
    merchant = db.query(Merchant).filter(Merchant.id == current_user["id"]).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    # Update business details
    merchant.business_name = details.business_name
    merchant.business_email = details.business_email or merchant.email
    merchant.country = details.country
    merchant.merchant_category = details.merchant_category.value
    merchant.onboarding_step = max(merchant.onboarding_step or 0, 1)

    # Auto-set currency from country
    currency_code, currency_symbol, currency_name = get_currency_for_country(details.country)
    merchant.base_currency = currency_code
    merchant.currency_symbol = currency_symbol
    merchant.currency_name = currency_name

    db.commit()
    db.refresh(merchant)

    wallet_count = db.query(MerchantWallet).filter(
        MerchantWallet.merchant_id == merchant.id,
        MerchantWallet.is_active == True,
    ).count()

    logger.info(f"Merchant {merchant.id} completed business details step")

    return OnboardingStatusResponse(
        step=merchant.onboarding_step,
        onboarding_completed=merchant.onboarding_completed or False,
        merchant_id=str(merchant.id),
        name=merchant.name,
        email=merchant.email,
        merchant_category=merchant.merchant_category,
        business_name=merchant.business_name,
        business_email=merchant.business_email,
        country=merchant.country,
        base_currency=merchant.base_currency or "USD",
        currency_symbol=merchant.currency_symbol or "$",
        currency_name=merchant.currency_name or "US Dollar",
        has_wallets=wallet_count > 0,
        wallet_count=wallet_count,
    )


# ============= STEP 2: WALLET SETUP =============

@router.post("/wallet-setup")
async def setup_wallets(
    wallet_setup: OnboardingWalletSetup,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Step 2: Configure which chains/tokens to accept.
    Auto-generates placeholder wallets if auto_generate is True.
    Merchants can update wallet addresses later from the dashboard.
    
    Accepts two formats:
    1. {"chains": [...], "tokens": [...], "auto_generate": true}
    2. {"wallets": [{"chain": "stellar", "token": "USDC", "auto_generate": true}, ...]}
    """
    merchant = db.query(Merchant).filter(Merchant.id == current_user["id"]).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    created_wallets = []
    
    # Handle both formats
    if wallet_setup.wallets:
        # Frontend format: individual wallet configs
        chains_to_create = {}  # {chain: [tokens]}
        for wallet_config in wallet_setup.wallets:
            if wallet_config.auto_generate:
                chain = wallet_config.chain.value
                token = wallet_config.token.value
                if chain not in chains_to_create:
                    chains_to_create[chain] = []
                if token not in chains_to_create[chain]:
                    chains_to_create[chain].append(token)
        
        # Update merchant settings
        all_chains = list(chains_to_create.keys())
        all_tokens = list(set(token for tokens in chains_to_create.values() for token in tokens))
        merchant.accepted_chains = all_chains
        merchant.accepted_tokens = all_tokens
        
        # Generate wallet for each unique chain
        for chain in chains_to_create.keys():
            existing = db.query(MerchantWallet).filter(
                MerchantWallet.merchant_id == merchant.id,
                MerchantWallet.chain == BlockchainNetwork(chain),
            ).first()

            if existing:
                created_wallets.append({
                    "chain": chain,
                    "wallet_address": existing.wallet_address,
                    "status": "already_exists",
                })
                continue

            placeholder_address = _generate_placeholder_address(chain)
            wallet = MerchantWallet(
                merchant_id=merchant.id,
                chain=BlockchainNetwork(chain),
                wallet_address=placeholder_address,
                is_active=True,
            )
            db.add(wallet)
            created_wallets.append({
                "chain": chain,
                "wallet_address": placeholder_address,
                "status": "created",
            })
    elif wallet_setup.chains:
        # Backend format: chains and tokens lists
        merchant.accepted_chains = [c.value for c in wallet_setup.chains]
        merchant.accepted_tokens = [t.value for t in wallet_setup.tokens] if wallet_setup.tokens else ["USDC"]

        if wallet_setup.auto_generate:
            # Generate placeholder wallets for each selected chain
            for chain in wallet_setup.chains:
                existing = db.query(MerchantWallet).filter(
                    MerchantWallet.merchant_id == merchant.id,
                    MerchantWallet.chain == BlockchainNetwork(chain.value),
                ).first()

                if existing:
                    created_wallets.append({
                        "chain": chain.value,
                        "wallet_address": existing.wallet_address,
                        "status": "already_exists",
                    })
                    continue

                placeholder_address = _generate_placeholder_address(chain.value)

                wallet = MerchantWallet(
                    merchant_id=merchant.id,
                    chain=BlockchainNetwork(chain.value),
                    wallet_address=placeholder_address,
                    is_active=True,
                )
                db.add(wallet)
                created_wallets.append({
                    "chain": chain.value,
                    "wallet_address": placeholder_address,
                    "status": "created",
                })

    merchant.onboarding_step = max(merchant.onboarding_step or 0, 2)
    db.commit()
    db.refresh(merchant)

    wallet_count = db.query(MerchantWallet).filter(
        MerchantWallet.merchant_id == merchant.id,
        MerchantWallet.is_active == True,
    ).count()

    logger.info(f"Merchant {merchant.id} completed wallet setup with {wallet_count} wallets")

    return {
        "message": "Wallet setup complete",
        "step": merchant.onboarding_step,
        "wallets": created_wallets,
        "accepted_chains": merchant.accepted_chains,
        "accepted_tokens": merchant.accepted_tokens,
        "wallet_count": wallet_count,
    }


# ============= STEP 3: COMPLETE ONBOARDING =============

@router.post("/complete", response_model=OnboardingCompleteResponse)
async def complete_onboarding(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    request: Optional[OnboardingCompleteRequest] = Body(None),
):
    """
    Step 3: Mark onboarding as complete.
    Optionally accepts wallet setup data and subscription plan to create wallets in the same call.
    If no wallet setup provided, ensures merchant has at least one wallet already.
    Returns the API key for integration.
    """
    # Debug logging
    logger.info(f"Complete onboarding called with request: {request}")
    if request:
        logger.info(f"Request chains: {request.chains}, wallets: {request.wallets}, auto_generate: {request.auto_generate}")
    
    merchant = db.query(Merchant).filter(Merchant.id == current_user["id"]).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    # Validate minimum requirements
    if not merchant.business_name:
        raise HTTPException(
            status_code=400,
            detail="Business name is required. Complete business details first.",
        )

    # If wallet setup data provided, create wallets
    if request:
        # Handle subscription plan if provided
        if request.plan:
            # Plan is stored in merchant_subscriptions table, but we'll just note it for now
            # The subscription is created automatically via trigger when merchant is created
            pass
        
        # Handle both formats: wallets array or chains/tokens lists
        if request.wallets:
            # Frontend format: individual wallet configs
            chains_to_create = {}  # {chain: [tokens]}
            for wallet_config in request.wallets:
                if wallet_config.auto_generate:
                    chain = wallet_config.chain.value
                    token = wallet_config.token.value
                    if chain not in chains_to_create:
                        chains_to_create[chain] = []
                    if token not in chains_to_create[chain]:
                        chains_to_create[chain].append(token)
            
            # Update merchant settings with unique chains and tokens
            all_chains = list(chains_to_create.keys())
            all_tokens = list(set(token for tokens in chains_to_create.values() for token in tokens))
            merchant.accepted_chains = all_chains
            merchant.accepted_tokens = all_tokens
            
            # Generate wallet for each unique chain (not per token)
            for chain in chains_to_create.keys():
                existing = db.query(MerchantWallet).filter(
                    MerchantWallet.merchant_id == merchant.id,
                    MerchantWallet.chain == BlockchainNetwork(chain),
                ).first()

                if not existing:
                    placeholder_address = _generate_placeholder_address(chain)
                    wallet = MerchantWallet(
                        merchant_id=merchant.id,
                        chain=BlockchainNetwork(chain),
                        wallet_address=placeholder_address,
                        is_active=True,
                    )
                    db.add(wallet)
            
            # Flush to make added wallets visible
            db.flush()
        elif request.chains:
            # Backend format: chains and tokens lists
            # Update accepted tokens and chains
            merchant.accepted_chains = [c.value for c in request.chains]
            merchant.accepted_tokens = [t.value for t in request.tokens] if request.tokens else ["USDC", "USDT"]

            if request.auto_generate:
                # Generate placeholder wallets for each selected chain
                for chain in request.chains:
                    # Check if wallet already exists for this chain
                    existing = db.query(MerchantWallet).filter(
                        MerchantWallet.merchant_id == merchant.id,
                        MerchantWallet.chain == BlockchainNetwork(chain.value),
                    ).first()

                    if not existing:
                        # Generate a placeholder address
                        placeholder_address = _generate_placeholder_address(chain.value)

                        wallet = MerchantWallet(
                            merchant_id=merchant.id,
                            chain=BlockchainNetwork(chain.value),
                            wallet_address=placeholder_address,
                            is_active=True,
                        )
                        db.add(wallet)
        
        # Flush to make added wallets visible to subsequent queries
        db.flush()

    # Check if merchant has at least one wallet
    wallet_count = db.query(MerchantWallet).filter(
        MerchantWallet.merchant_id == merchant.id,
        MerchantWallet.is_active == True,
    ).count()

    if wallet_count == 0:
        # Auto-generate default wallets instead of failing
        logger.info(f"Merchant {merchant.id} has no wallets — auto-generating defaults for: {DEFAULT_CHAINS}")
        if not merchant.accepted_chains:
            merchant.accepted_chains = DEFAULT_CHAINS
        if not merchant.accepted_tokens:
            merchant.accepted_tokens = DEFAULT_TOKENS

        for chain in merchant.accepted_chains:
            existing = db.query(MerchantWallet).filter(
                MerchantWallet.merchant_id == merchant.id,
                MerchantWallet.chain == BlockchainNetwork(chain),
            ).first()
            if not existing:
                placeholder_address = _generate_placeholder_address(chain)
                wallet = MerchantWallet(
                    merchant_id=merchant.id,
                    chain=BlockchainNetwork(chain),
                    wallet_address=placeholder_address,
                    is_active=True,
                )
                db.add(wallet)
        db.flush()
        wallet_count = db.query(MerchantWallet).filter(
            MerchantWallet.merchant_id == merchant.id,
            MerchantWallet.is_active == True,
        ).count()
        logger.info(f"Auto-generated {wallet_count} wallets for merchant {merchant.id}")

    # Generate API key if not already present
    if not merchant.api_key:
        merchant.api_key = generate_api_key()

    # Set default chains/tokens if not set
    if not merchant.accepted_chains:
        merchant.accepted_chains = DEFAULT_CHAINS
    if not merchant.accepted_tokens:
        merchant.accepted_tokens = DEFAULT_TOKENS

    merchant.onboarding_completed = True
    merchant.onboarding_step = 3
    db.commit()
    db.refresh(merchant)

    # Get wallets for response
    wallets = db.query(MerchantWallet).filter(
        MerchantWallet.merchant_id == merchant.id,
        MerchantWallet.is_active == True,
    ).all()

    wallet_list = [
        {"chain": w.chain.value, "wallet_address": w.wallet_address}
        for w in wallets
    ]

    logger.info(f"Merchant {merchant.id} completed onboarding")

    return OnboardingCompleteResponse(
        message="Onboarding complete! You can now start accepting payments.",
        merchant_id=str(merchant.id),
        api_key=merchant.api_key,
        onboarding_completed=True,
        wallets=wallet_list,
    )


# ============= SKIP ONBOARDING (Disabled) =============

@router.post("/skip")
async def skip_onboarding(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Skip onboarding is disabled. Merchants must complete onboarding.
    """
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Onboarding cannot be skipped. Please complete all onboarding steps to access your dashboard.",
    )


# ============= HELPER FUNCTIONS =============

def _generate_placeholder_address(chain: str) -> str:
    """
    Generate a placeholder wallet address for a given chain.
    In production, this would integrate with actual key generation.
    Merchants should replace these with their real wallet addresses.
    """
    random_hex = secrets.token_hex(20)  # 40 hex chars

    if chain == "stellar":
        # Stellar addresses start with G and are 56 chars
        return f"G{'A' * 15}{secrets.token_hex(20).upper()[:40]}"
    elif chain == "tron":
        # Tron addresses start with T
        return f"T{secrets.token_hex(16).upper()[:33]}"
    else:
        # EVM chains (ethereum, polygon, base) use 0x prefix + 40 hex chars
        return f"0x{random_hex}"
