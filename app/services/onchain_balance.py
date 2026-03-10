"""
On-Chain Balance Service

Fetches real token balances from blockchain RPCs for merchant wallets.
Supports Stellar, EVM chains (Ethereum, Polygon, Base), and Tron.
Results are cached briefly to avoid spamming RPCs on every dashboard load.
"""

import asyncio
import logging
import httpx
from decimal import Decimal
from typing import Dict, List, Optional
from dataclasses import dataclass

from app.core.config import settings

logger = logging.getLogger(__name__)

# Standard ERC-20 balanceOf(address) selector
ERC20_BALANCE_OF = "0x70a08231"

# Hard per-request HTTP timeout (seconds) — keeps slow RPCs from stalling everything
HTTP_TIMEOUT = 8

# Per-chain asyncio timeout — even if HTTP hangs, we give up after this many seconds
CHAIN_TIMEOUT = 10


@dataclass
class TokenBalance:
    """Single token balance on a specific chain."""
    chain: str
    token: str
    balance: Decimal
    wallet_address: str


def _get_evm_chain_config(chain: str) -> Optional[dict]:
    """Return RPC URL and token contract addresses for an EVM chain."""
    configs = {
        "ethereum": {
            "rpc_url": settings.ETHEREUM_RPC_URL,
            "enabled": settings.ETHEREUM_ENABLED,
            "tokens": {
                "USDC": {"address": settings.ETHEREUM_USDC_ADDRESS, "decimals": 6},
                "USDT": {"address": settings.ETHEREUM_USDT_ADDRESS, "decimals": 6},
                "PYUSD": {"address": settings.ETHEREUM_PYUSD_ADDRESS, "decimals": 6},
            },
        },
        "polygon": {
            "rpc_url": settings.POLYGON_RPC_URL,
            "enabled": settings.POLYGON_ENABLED,
            "tokens": {
                "USDC": {"address": settings.POLYGON_USDC_ADDRESS, "decimals": 6},
                "USDT": {"address": settings.POLYGON_USDT_ADDRESS, "decimals": 6},
            },
        },
        "base": {
            "rpc_url": settings.BASE_RPC_URL,
            "enabled": settings.BASE_ENABLED,
            "tokens": {
                "USDC": {"address": settings.BASE_USDC_ADDRESS, "decimals": 6},
            },
        },
    }
    cfg = configs.get(chain.lower())
    if cfg and cfg["enabled"] and cfg["rpc_url"]:
        return cfg
    return None


# ─────────────────────────  EVM (Ethereum / Polygon / Base)  ──────────────

async def _fetch_erc20_balance(
    rpc_url: str,
    token_address: str,
    wallet_address: str,
    decimals: int,
) -> Decimal:
    """Call balanceOf via eth_call and decode the uint256 result."""
    # ABI-encode balanceOf(address): pad address to 32 bytes
    padded = wallet_address.lower().replace("0x", "").zfill(64)
    data = f"{ERC20_BALANCE_OF}{padded}"

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "eth_call",
        "params": [{"to": token_address, "data": data}, "latest"],
    }

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.post(rpc_url, json=payload)
        resp.raise_for_status()
        body = resp.json()

    result = body.get("result", "0x0")
    raw = int(result, 16) if result and result != "0x" else 0
    return Decimal(raw) / Decimal(10 ** decimals)


async def get_evm_balances(chain: str, wallet_address: str) -> List[TokenBalance]:
    """Fetch all token balances on a single EVM chain for a wallet."""
    cfg = _get_evm_chain_config(chain)
    if not cfg:
        return []

    results: List[TokenBalance] = []
    for symbol, token_cfg in cfg["tokens"].items():
        if not token_cfg["address"]:
            continue
        try:
            bal = await _fetch_erc20_balance(
                cfg["rpc_url"],
                token_cfg["address"],
                wallet_address,
                token_cfg["decimals"],
            )
            results.append(TokenBalance(
                chain=chain,
                token=symbol,
                balance=bal,
                wallet_address=wallet_address,
            ))
        except Exception as e:
            logger.warning(f"Failed to fetch {symbol} balance on {chain} for {wallet_address}: {e}")
            results.append(TokenBalance(chain=chain, token=symbol, balance=Decimal(0), wallet_address=wallet_address))
    return results


# ─────────────────────────  Stellar  ──────────────────────────────────────

async def get_stellar_balances(wallet_address: str) -> List[TokenBalance]:
    """Fetch USDC (and native XLM) balances from Horizon."""
    horizon = settings.STELLAR_HORIZON_URL
    if not horizon:
        return []

    url = f"{horizon}/accounts/{wallet_address}"
    results: List[TokenBalance] = []

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            resp = await client.get(url)
            # 404 = unfunded account, 400 = invalid/test address — both mean zero balance
            if resp.status_code in (400, 404):
                return [TokenBalance(chain="stellar", token="USDC", balance=Decimal(0), wallet_address=wallet_address)]
            resp.raise_for_status()
            account = resp.json()

        for bal_entry in account.get("balances", []):
            asset_type = bal_entry.get("asset_type", "")
            if asset_type == "credit_alphanum4" and bal_entry.get("asset_code") == "USDC":
                results.append(TokenBalance(
                    chain="stellar",
                    token="USDC",
                    balance=Decimal(bal_entry["balance"]),
                    wallet_address=wallet_address,
                ))

    except Exception as e:
        logger.warning(f"Failed to fetch Stellar balances for {wallet_address}: {e}")
        results.append(TokenBalance(chain="stellar", token="USDC", balance=Decimal(0), wallet_address=wallet_address))

    if not any(tb.token == "USDC" for tb in results):
        results.append(TokenBalance(chain="stellar", token="USDC", balance=Decimal(0), wallet_address=wallet_address))

    return results


# ─────────────────────────  Tron  ─────────────────────────────────────────

async def get_tron_balances(wallet_address: str) -> List[TokenBalance]:
    """Fetch TRC-20 USDT / USDC balances from TronGrid."""
    api_url = settings.TRON_API_URL
    if not api_url or not settings.TRON_ENABLED:
        return []

    results: List[TokenBalance] = []
    tokens = {
        "USDT": settings.TRON_USDT_ADDRESS,
        "USDC": settings.TRON_USDC_ADDRESS,
    }

    for symbol, contract in tokens.items():
        if not contract:
            continue
        try:
            # TronGrid /wallet/triggerconstantcontract
            url = f"{api_url}/wallet/triggerconstantcontract"
            # Convert base58 wallet address to hex for parameter
            # TronGrid accepts base58 owner_address and parameter as hex-padded address
            payload = {
                "owner_address": wallet_address,
                "contract_address": contract,
                "function_selector": "balanceOf(address)",
                "parameter": _tron_address_to_parameter(wallet_address),
                "visible": True,
            }
            headers = {}
            if settings.TRON_API_KEY:
                headers["TRON-PRO-API-KEY"] = settings.TRON_API_KEY

            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                body = resp.json()

            constant_result = body.get("constant_result", ["0"])
            raw = int(constant_result[0], 16) if constant_result and constant_result[0] else 0
            bal = Decimal(raw) / Decimal(10 ** 6)

            results.append(TokenBalance(chain="tron", token=symbol, balance=bal, wallet_address=wallet_address))
        except Exception as e:
            logger.warning(f"Failed to fetch {symbol} balance on Tron for {wallet_address}: {e}")
            results.append(TokenBalance(chain="tron", token=symbol, balance=Decimal(0), wallet_address=wallet_address))

    return results


def _tron_address_to_parameter(address: str) -> str:
    """Convert a Tron base58 address to a 64-char hex-padded parameter.
    
    Falls back to zero-padding if decoding fails (e.g. already hex).
    """
    import base58
    try:
        decoded = base58.b58decode_check(address)
        # Drop the 0x41 prefix byte, hex-encode, pad to 64 chars
        return decoded[1:].hex().zfill(64)
    except Exception:
        # If already hex or bad format, just pad it
        clean = address.replace("0x", "").replace("41", "", 1) if address.startswith("41") else address
        return clean.zfill(64)


# ─────────────────────────  Aggregator  ───────────────────────────────────

async def _with_chain_timeout(coro, chain: str, wallet_address: str) -> List[TokenBalance]:
    """Wrap a chain fetch coroutine with CHAIN_TIMEOUT. Returns empty list on timeout."""
    try:
        return await asyncio.wait_for(coro, timeout=CHAIN_TIMEOUT)
    except asyncio.TimeoutError:
        logger.warning(f"Timeout fetching {chain} balance for {wallet_address[:10]}... (>{CHAIN_TIMEOUT}s) — skipping")
        return []


async def fetch_all_wallet_balances(
    wallets: List[dict],
) -> Dict[str, Decimal]:
    """
    Fetch on-chain balances for all merchant wallets and aggregate by token.

    Args:
        wallets: list of {"chain": "ethereum", "wallet_address": "0x...", "is_active": True}

    Returns:
        {"USDC": Decimal("123.45"), "USDT": Decimal("67.89"), "PYUSD": Decimal("0")}
    """
    aggregated: Dict[str, Decimal] = {"USDC": Decimal(0), "USDT": Decimal(0), "PYUSD": Decimal(0)}

    tasks = []
    for w in wallets:
        if not w.get("is_active", True):
            continue
        chain = w["chain"].lower()
        addr = w["wallet_address"]

        if chain == "stellar":
            tasks.append(_with_chain_timeout(get_stellar_balances(addr), chain, addr))
        elif chain == "tron":
            tasks.append(_with_chain_timeout(get_tron_balances(addr), chain, addr))
        elif chain in ("ethereum", "polygon", "base"):
            tasks.append(_with_chain_timeout(get_evm_balances(chain, addr), chain, addr))

    if not tasks:
        return aggregated

    results = await asyncio.gather(*tasks, return_exceptions=True)

    for result in results:
        if isinstance(result, Exception):
            logger.warning(f"Balance fetch error: {result}")
            continue
        for tb in result:
            token = tb.token.upper()
            if token in aggregated:
                aggregated[token] += tb.balance

    return aggregated
