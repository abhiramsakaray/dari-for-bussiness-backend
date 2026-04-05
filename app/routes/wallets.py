"""
Merchant Wallet Management Routes

Endpoints for managing merchant wallets across different blockchain networks.
Includes a balance dashboard with dual-currency (USDC + local) display.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from decimal import Decimal
from typing import List
import uuid
from app.core import get_db, require_merchant
from app.core.cache import cache, make_cache_key
from app.models import Merchant, MerchantWallet, BlockchainNetwork, Withdrawal
from app.schemas import (
    MerchantWalletCreate, MerchantWalletResponse, MerchantWalletList,
    BalanceDashboardResponse, CoinBalance, WalletBalance, LocalCurrencyAmount,
)
from app.services.currency_service import get_currency_for_country, build_local_amount
import logging

router = APIRouter(prefix="/merchant/wallets", tags=["Merchant Wallets"])
logger = logging.getLogger(__name__)

SUPPORTED_TOKENS = ["USDC", "USDT", "PYUSD"]
BALANCE_COLUMNS = {"USDC": "balance_usdc", "USDT": "balance_usdt", "PYUSD": "balance_pyusd"}


@router.get("", response_model=MerchantWalletList)
async def list_wallets(
    current_user: dict = Depends(require_merchant),
    db: Session = Depends(get_db)
):
    """
    List all wallets for the current merchant.
    
    Returns wallets for all configured blockchain networks.
    """
    try:
        merchant_uuid = uuid.UUID(current_user["id"]) if isinstance(current_user["id"], str) else current_user["id"]
        logger.info(f"Fetching wallets for merchant {merchant_uuid}")
        
        # Check cache
        ck = make_cache_key("wallets", merchant_uuid)
        cached = cache.get(ck, region="wallets")
        if cached is not None:
            return cached
        
        wallets = db.query(MerchantWallet).filter(
            MerchantWallet.merchant_id == merchant_uuid,
            MerchantWallet.is_active == True
        ).all()
        
        wallet_list = [
            MerchantWalletResponse(
                id=str(w.id),
                chain=w.chain.value if hasattr(w.chain, 'value') else str(w.chain),
                wallet_address=w.wallet_address,
                is_active=w.is_active,
                created_at=w.created_at
            ) for w in wallets
        ]
        
        logger.info(f"Found {len(wallet_list)} wallets for merchant {merchant_uuid}")
        
        result = MerchantWalletList(wallets=wallet_list)
        cache.set(ck, result, region="wallets")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching wallets: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch wallets: {str(e)}"
        )


@router.get("/dashboard", response_model=BalanceDashboardResponse)
async def get_balance_dashboard(
    current_user: dict = Depends(require_merchant),
    db: Session = Depends(get_db),
):
    """
    Get a complete balance dashboard with **live on-chain balances**.

    Balances are fetched directly from blockchain RPCs (Stellar Horizon,
    EVM eth_call, TronGrid). Falls back to DB-stored balances if all
    RPC calls fail.

    Returns:
    - **Total balance** in USDC and merchant's local currency
    - **Per-coin breakdown** (USDC, USDT, PYUSD) with local equivalents
    - **Per-chain detail** for each coin
    - **All wallets** with chain and address
    - **Pending withdrawals** total
    - **Net available** (total minus pending)
    """
    from app.services.onchain_balance import get_evm_balances, get_stellar_balances, get_tron_balances, _with_chain_timeout
    import asyncio

    merchant_uuid = uuid.UUID(current_user["id"]) if isinstance(current_user["id"], str) else current_user["id"]
    merchant = db.query(Merchant).filter(Merchant.id == merchant_uuid).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    currency_code, currency_symbol, _ = get_currency_for_country(merchant.country)

    # ── Wallet list ──
    wallets_db = db.query(MerchantWallet).filter(
        MerchantWallet.merchant_id == merchant.id,
    ).all()
    wallet_items = [
        WalletBalance(
            chain=w.chain.value if hasattr(w.chain, 'value') else str(w.chain),
            wallet_address=w.wallet_address,
            is_active=w.is_active,
        )
        for w in wallets_db
    ]

    # ── Fetch on-chain balances ──
    wallet_dicts = [
        {"chain": wi.chain, "wallet_address": wi.wallet_address, "is_active": wi.is_active}
        for wi in wallet_items
    ]
    balance_source = "onchain"

    try:
        # Gather per-chain balances in parallel
        all_chain_balances = []  # List[TokenBalance]
        tasks = []
        for wd in wallet_dicts:
            if not wd["is_active"]:
                continue
            chain = wd["chain"].lower()
            addr = wd["wallet_address"]
            if chain == "stellar":
                tasks.append(_with_chain_timeout(get_stellar_balances(addr), chain, addr))
            elif chain == "tron":
                tasks.append(_with_chain_timeout(get_tron_balances(addr), chain, addr))
            elif chain in ("ethereum", "polygon", "base"):
                tasks.append(_with_chain_timeout(get_evm_balances(chain, addr), chain, addr))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    logger.warning(f"Balance fetch error: {result}")
                    continue
                all_chain_balances.extend(result)

        # Aggregate by token + build chain-level detail
        from collections import defaultdict
        token_totals = defaultdict(float)
        chain_detail = defaultdict(list)  # token -> [ChainTokenBalance, ...]
        from app.schemas import ChainTokenBalance

        for tb in all_chain_balances:
            token_upper = tb.token.upper()
            bal_float = float(tb.balance)
            token_totals[token_upper] += bal_float
            chain_detail[token_upper].append(ChainTokenBalance(
                chain=tb.chain,
                token=tb.token,
                balance=bal_float,
                wallet_address=tb.wallet_address,
            ))

    except Exception as e:
        logger.error(f"On-chain balance fetch failed, falling back to DB: {e}")
        balance_source = "database"
        token_totals = {}
        chain_detail = {}
        for token in SUPPORTED_TOKENS:
            col = BALANCE_COLUMNS[token]
            token_totals[token] = float(getattr(merchant, col, 0) or 0)

    # ── Per-coin balances ──
    coins = []
    total_usdc = 0.0
    for token in SUPPORTED_TOKENS:
        raw = token_totals.get(token, 0.0)
        total_usdc += raw
        coin_local = await build_local_amount(raw, currency_code, currency_symbol)
        coins.append(CoinBalance(
            token=token,
            balance_usdc=raw,
            balance_local=LocalCurrencyAmount(**coin_local),
            chain_balances=chain_detail.get(token),
        ))

    # ── Pending withdrawals ──
    pending_usdc = float(
        db.query(func.coalesce(func.sum(Withdrawal.amount), 0)).filter(
            Withdrawal.merchant_id == merchant.id,
            Withdrawal.status.in_(["pending", "processing"]),
        ).scalar()
    )

    net_usdc = max(total_usdc - pending_usdc, 0.0)

    # ── Local currency conversions ──
    total_local = await build_local_amount(total_usdc, currency_code, currency_symbol)
    pending_local = await build_local_amount(pending_usdc, currency_code, currency_symbol)
    net_local = await build_local_amount(net_usdc, currency_code, currency_symbol)

    return BalanceDashboardResponse(
        total_balance_usdc=total_usdc,
        total_balance_local=LocalCurrencyAmount(**total_local),
        local_currency=currency_code,
        local_symbol=currency_symbol,
        exchange_rate=total_local["exchange_rate"],
        coins=coins,
        wallets=wallet_items,
        pending_withdrawals_usdc=pending_usdc,
        pending_withdrawals_local=LocalCurrencyAmount(**pending_local),
        net_available_usdc=net_usdc,
        net_available_local=LocalCurrencyAmount(**net_local),
        balance_source=balance_source,
    )


@router.post("", response_model=MerchantWalletResponse, status_code=status.HTTP_201_CREATED)
async def add_wallet(
    wallet_data: MerchantWalletCreate,
    current_user: dict = Depends(require_merchant),
    db: Session = Depends(get_db)
):
    """
    Add a new wallet for a blockchain network.
    
    Each merchant can have one active wallet per chain.
    Adding a new wallet for an existing chain will replace the old one.
    """
    merchant_id = uuid.UUID(current_user["id"])
    
    # Validate wallet address format based on chain
    chain = wallet_data.chain.value if hasattr(wallet_data.chain, 'value') else wallet_data.chain
    address = wallet_data.wallet_address
    
    if not _validate_address(chain, address):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid wallet address format for {chain}"
        )
    
    # Check for existing wallet on this chain
    existing = db.query(MerchantWallet).filter(
        MerchantWallet.merchant_id == merchant_id,
        MerchantWallet.chain == chain
    ).first()
    
    if existing:
        # Update existing wallet
        existing.wallet_address = address
        existing.is_active = True
        db.commit()
        db.refresh(existing)
        wallet = existing
        logger.info(f"Updated wallet for merchant {merchant_id} on {chain}")
    else:
        # Create new wallet
        wallet = MerchantWallet(
            merchant_id=merchant_id,
            chain=chain,
            wallet_address=address,
            is_active=True
        )
        db.add(wallet)
        db.commit()
        db.refresh(wallet)
        logger.info(f"Created wallet for merchant {merchant_id} on {chain}")
    
    # Also update legacy stellar_address if chain is Stellar
    if chain == "stellar" or chain == BlockchainNetwork.STELLAR:
        merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
        if merchant:
            merchant.stellar_address = address
            db.commit()
    
    # Invalidate wallet cache
    cache.invalidate_prefix(make_cache_key("wallets", merchant_id), region="wallets")
    
    return MerchantWalletResponse(
        id=str(wallet.id),
        chain=wallet.chain.value if hasattr(wallet.chain, 'value') else str(wallet.chain),
        wallet_address=wallet.wallet_address,
        is_active=wallet.is_active,
        created_at=wallet.created_at
    )


@router.get("/{chain}", response_model=MerchantWalletResponse)
async def get_wallet(
    chain: str,
    current_user: dict = Depends(require_merchant),
    db: Session = Depends(get_db)
):
    """
    Get wallet for a specific blockchain network.
    """
    merchant_uuid = uuid.UUID(current_user["id"])
    wallet = db.query(MerchantWallet).filter(
        MerchantWallet.merchant_id == merchant_uuid,
        MerchantWallet.chain == chain.lower(),
        MerchantWallet.is_active == True
    ).first()
    
    if not wallet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No wallet configured for {chain}"
        )
    
    return MerchantWalletResponse(
        id=str(wallet.id),
        chain=wallet.chain.value if hasattr(wallet.chain, 'value') else str(wallet.chain),
        wallet_address=wallet.wallet_address,
        is_active=wallet.is_active,
        created_at=wallet.created_at
    )


@router.delete("/{chain}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_wallet(
    chain: str,
    current_user: dict = Depends(require_merchant),
    db: Session = Depends(get_db)
):
    """
    Deactivate wallet for a specific blockchain network.
    
    The wallet is not deleted, just marked as inactive.
    """
    merchant_uuid = uuid.UUID(current_user["id"])
    wallet = db.query(MerchantWallet).filter(
        MerchantWallet.merchant_id == merchant_uuid,
        MerchantWallet.chain == chain.lower()
    ).first()
    
    if not wallet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No wallet configured for {chain}"
        )
    
    wallet.is_active = False
    db.commit()
    
    logger.info(f"Deactivated wallet for merchant {current_user['id']} on {chain}")


def _validate_address(chain: str, address: str) -> bool:
    """
    Validate wallet address format for a specific chain.
    
    Basic validation - can be extended with more rigorous checks.
    """
    chain = chain.lower() if isinstance(chain, str) else chain.value.lower()
    
    if chain == "stellar":
        # Stellar addresses start with G and are 56 characters
        return address.startswith("G") and len(address) == 56
        
    elif chain in ["ethereum", "polygon", "base"]:
        # EVM addresses are 42 characters starting with 0x
        return address.startswith("0x") and len(address) == 42
        
    elif chain == "tron":
        # Tron addresses start with T and are 34 characters
        return address.startswith("T") and len(address) == 34
        
    elif chain == "solana":
        # Solana addresses are 32-44 characters base58
        return 32 <= len(address) <= 44
        
    return False
