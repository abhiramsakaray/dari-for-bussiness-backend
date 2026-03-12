"""
On-Chain Balance Service

Fetches real token balances from blockchain RPCs for merchant wallets.
Supports Stellar, EVM chains (Ethereum, Polygon, Base), and Tron.

Improvements:
  - Multiple fallback RPC endpoints per chain (tries next on failure)
  - In-memory cache (60s TTL) to avoid spamming RPCs on every dashboard load
  - Reusable httpx.AsyncClient (connection pooling)
  - Shorter timeouts (4s per request, 6s per chain) for fast dashboard loads
  - Graceful degradation: returns cached/zero balances on failure
"""

import asyncio
import logging
import time
import httpx
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from app.core.config import settings

logger = logging.getLogger(__name__)

# Standard ERC-20 balanceOf(address) selector
ERC20_BALANCE_OF = "0x70a08231"

# Timeouts — kept short so dashboard loads fast even when RPCs are down
HTTP_TIMEOUT = 4       # seconds per HTTP request
CHAIN_TIMEOUT = 6      # seconds per chain (total)
CACHE_TTL = 60         # seconds to cache balances


@dataclass
class TokenBalance:
    """Single token balance on a specific chain."""
    chain: str
    token: str
    balance: Decimal
    wallet_address: str


# ─────────────────────────  In-Memory Cache  ──────────────────────────────

_balance_cache: Dict[str, Tuple[float, List[TokenBalance]]] = {}


def _cache_key(chain: str, wallet: str) -> str:
    return f"{chain}:{wallet.lower()}"


def _get_cached(chain: str, wallet: str) -> Optional[List[TokenBalance]]:
    key = _cache_key(chain, wallet)
    entry = _balance_cache.get(key)
    if entry and (time.time() - entry[0]) < CACHE_TTL:
        return entry[1]
    return None


def _set_cached(chain: str, wallet: str, balances: List[TokenBalance]):
    _balance_cache[_cache_key(chain, wallet)] = (time.time(), balances)


# ─────────────────────────  Fallback RPC Endpoints  ──────────────────────

# Multiple free public RPCs per chain — if one fails, try the next
EVM_FALLBACK_RPCS = {
    "ethereum": {
        "testnet": [
            "https://rpc.sepolia.org",
            "https://ethereum-sepolia-rpc.publicnode.com",
            "https://rpc2.sepolia.org",
        ],
        "mainnet": [
            "https://eth.llamarpc.com",
            "https://ethereum-rpc.publicnode.com",
            "https://rpc.ankr.com/eth",
            "https://1rpc.io/eth",
        ],
    },
    "polygon": {
        "testnet": [
            "https://rpc-amoy.polygon.technology",
            "https://polygon-amoy-bor-rpc.publicnode.com",
        ],
        "mainnet": [
            "https://polygon-rpc.com",
            "https://polygon-bor-rpc.publicnode.com",
            "https://rpc.ankr.com/polygon",
            "https://1rpc.io/matic",
        ],
    },
    "base": {
        "testnet": [
            "https://sepolia.base.org",
            "https://base-sepolia-rpc.publicnode.com",
        ],
        "mainnet": [
            "https://mainnet.base.org",
            "https://base-rpc.publicnode.com",
            "https://1rpc.io/base",
        ],
    },
}


def _get_rpc_urls(chain: str) -> List[str]:
    """Get ordered list of RPC URLs for a chain (configured first, then fallbacks)."""
    net = "mainnet" if settings.USE_MAINNET else "testnet"
    
    # Start with the configured RPC URL
    configured_url = ""
    if chain == "ethereum":
        configured_url = settings.ETHEREUM_RPC_URL
    elif chain == "polygon":
        configured_url = settings.POLYGON_RPC_URL
    elif chain == "base":
        configured_url = settings.BASE_RPC_URL
    
    urls = []
    if configured_url:
        urls.append(configured_url)
    
    # Add fallbacks (skip duplicates)
    fallbacks = EVM_FALLBACK_RPCS.get(chain, {}).get(net, [])
    for fb in fallbacks:
        if fb not in urls:
            urls.append(fb)
    
    return urls


def _get_evm_chain_config(chain: str) -> Optional[dict]:
    """Return RPC URLs and token contract addresses for an EVM chain."""
    configs = {
        "ethereum": {
            "enabled": settings.ETHEREUM_ENABLED,
            "tokens": {
                "USDC": {"address": settings.ETHEREUM_USDC_ADDRESS, "decimals": 6},
                "USDT": {"address": settings.ETHEREUM_USDT_ADDRESS, "decimals": 6},
                "PYUSD": {"address": settings.ETHEREUM_PYUSD_ADDRESS, "decimals": 6},
            },
        },
        "polygon": {
            "enabled": settings.POLYGON_ENABLED,
            "tokens": {
                "USDC": {"address": settings.POLYGON_USDC_ADDRESS, "decimals": 6},
                "USDT": {"address": settings.POLYGON_USDT_ADDRESS, "decimals": 6},
            },
        },
        "base": {
            "enabled": settings.BASE_ENABLED,
            "tokens": {
                "USDC": {"address": settings.BASE_USDC_ADDRESS, "decimals": 6},
            },
        },
    }
    cfg = configs.get(chain.lower())
    if cfg and cfg["enabled"]:
        return cfg
    return None


# ─────────────────────────  EVM (Ethereum / Polygon / Base)  ──────────────

async def _fetch_erc20_balance(
    client: httpx.AsyncClient,
    rpc_url: str,
    token_address: str,
    wallet_address: str,
    decimals: int,
) -> Decimal:
    """Call balanceOf via eth_call and decode the uint256 result."""
    padded = wallet_address.lower().replace("0x", "").zfill(64)
    data = f"{ERC20_BALANCE_OF}{padded}"

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "eth_call",
        "params": [{"to": token_address, "data": data}, "latest"],
    }

    resp = await client.post(rpc_url, json=payload)
    resp.raise_for_status()
    body = resp.json()

    result = body.get("result", "0x0")
    raw = int(result, 16) if result and result != "0x" else 0
    return Decimal(raw) / Decimal(10 ** decimals)


async def _fetch_erc20_balance_with_fallback(
    client: httpx.AsyncClient,
    chain: str,
    token_address: str,
    wallet_address: str,
    decimals: int,
) -> Decimal:
    """Try fetching balance from multiple RPC endpoints until one works."""
    rpc_urls = _get_rpc_urls(chain)
    
    for rpc_url in rpc_urls:
        try:
            return await _fetch_erc20_balance(
                client, rpc_url, token_address, wallet_address, decimals
            )
        except Exception:
            continue  # Try next RPC
    
    # All RPCs failed
    raise ConnectionError(f"All {len(rpc_urls)} RPCs failed for {chain}")


async def get_evm_balances(chain: str, wallet_address: str) -> List[TokenBalance]:
    """Fetch all token balances on a single EVM chain for a wallet."""
    # Check cache first
    cached = _get_cached(chain, wallet_address)
    if cached is not None:
        return cached

    cfg = _get_evm_chain_config(chain)
    if not cfg:
        return []

    results: List[TokenBalance] = []
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        for symbol, token_cfg in cfg["tokens"].items():
            if not token_cfg["address"]:
                continue
            try:
                bal = await _fetch_erc20_balance_with_fallback(
                    client,
                    chain,
                    token_cfg["address"],
                    wallet_address,
                    token_cfg["decimals"],
                )
                results.append(TokenBalance(
                    chain=chain, token=symbol, balance=bal,
                    wallet_address=wallet_address,
                ))
            except Exception as e:
                logger.warning(f"Failed to fetch {symbol} on {chain} for {wallet_address[:10]}...: {e}")
                results.append(TokenBalance(
                    chain=chain, token=symbol, balance=Decimal(0),
                    wallet_address=wallet_address,
                ))

    # Cache the results
    _set_cached(chain, wallet_address, results)
    return results


# ─────────────────────────  Stellar  ──────────────────────────────────────

STELLAR_FALLBACK_HORIZONS = {
    "testnet": [
        "https://horizon-testnet.stellar.org",
    ],
    "mainnet": [
        "https://horizon.stellar.org",
    ],
}


async def get_stellar_balances(wallet_address: str) -> List[TokenBalance]:
    """Fetch USDC (and native XLM) balances from Horizon."""
    # Check cache first
    cached = _get_cached("stellar", wallet_address)
    if cached is not None:
        return cached

    net = "mainnet" if settings.USE_MAINNET else "testnet"
    horizons = []
    if settings.STELLAR_HORIZON_URL:
        horizons.append(settings.STELLAR_HORIZON_URL)
    horizons.extend(STELLAR_FALLBACK_HORIZONS.get(net, []))

    results: List[TokenBalance] = []

    for horizon in horizons:
        try:
            url = f"{horizon}/accounts/{wallet_address}"
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                resp = await client.get(url)
                if resp.status_code in (400, 404):
                    results = [TokenBalance(chain="stellar", token="USDC", balance=Decimal(0), wallet_address=wallet_address)]
                    break
                resp.raise_for_status()
                account = resp.json()

            for bal_entry in account.get("balances", []):
                asset_type = bal_entry.get("asset_type", "")
                if asset_type == "credit_alphanum4" and bal_entry.get("asset_code") == "USDC":
                    results.append(TokenBalance(
                        chain="stellar", token="USDC",
                        balance=Decimal(bal_entry["balance"]),
                        wallet_address=wallet_address,
                    ))
            break  # Success — stop trying more horizons
        except Exception as e:
            logger.warning(f"Stellar Horizon {horizon} failed for {wallet_address[:10]}...: {e}")
            continue

    if not any(tb.token == "USDC" for tb in results):
        results.append(TokenBalance(chain="stellar", token="USDC", balance=Decimal(0), wallet_address=wallet_address))

    _set_cached("stellar", wallet_address, results)
    return results


# ─────────────────────────  Tron  ─────────────────────────────────────────

TRON_FALLBACK_APIS = {
    "testnet": [
        "https://nile.trongrid.io",
    ],
    "mainnet": [
        "https://api.trongrid.io",
        "https://api.tronstack.io",
    ],
}


async def get_tron_balances(wallet_address: str) -> List[TokenBalance]:
    """Fetch TRC-20 USDT / USDC balances from TronGrid."""
    # Check cache first
    cached = _get_cached("tron", wallet_address)
    if cached is not None:
        return cached

    if not settings.TRON_ENABLED:
        return []

    net = "mainnet" if settings.USE_MAINNET else "testnet"
    api_urls = []
    if settings.TRON_API_URL:
        api_urls.append(settings.TRON_API_URL)
    api_urls.extend(TRON_FALLBACK_APIS.get(net, []))

    results: List[TokenBalance] = []
    tokens = {
        "USDT": settings.TRON_USDT_ADDRESS,
        "USDC": settings.TRON_USDC_ADDRESS,
    }

    for symbol, contract in tokens.items():
        if not contract:
            continue
        fetched = False
        for api_url in api_urls:
            try:
                url = f"{api_url}/wallet/triggerconstantcontract"
                payload = {
                    "owner_address": wallet_address,
                    "contract_address": contract,
                    "function_selector": "balanceOf(address)",
                    "parameter": _tron_address_to_parameter(wallet_address),
                    "visible": True,
                }
                headers = {}
                if settings.TRON_API_KEY and settings.TRON_API_KEY != "your-trongrid-api-key-here":
                    headers["TRON-PRO-API-KEY"] = settings.TRON_API_KEY

                async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                    resp = await client.post(url, json=payload, headers=headers)
                    resp.raise_for_status()
                    body = resp.json()

                constant_result = body.get("constant_result", ["0"])
                raw = int(constant_result[0], 16) if constant_result and constant_result[0] else 0
                bal = Decimal(raw) / Decimal(10 ** 6)

                results.append(TokenBalance(chain="tron", token=symbol, balance=bal, wallet_address=wallet_address))
                fetched = True
                break  # Success — stop trying more APIs
            except Exception as e:
                logger.warning(f"Tron API {api_url} failed for {symbol}: {e}")
                continue

        if not fetched:
            results.append(TokenBalance(chain="tron", token=symbol, balance=Decimal(0), wallet_address=wallet_address))

    _set_cached("tron", wallet_address, results)
    return results


def _tron_address_to_parameter(address: str) -> str:
    """Convert a Tron base58 address to a 64-char hex-padded parameter.
    
    Falls back to zero-padding if decoding fails (e.g. already hex).
    """
    import base58
    try:
        decoded = base58.b58decode_check(address)
        return decoded[1:].hex().zfill(64)
    except Exception:
        clean = address.replace("0x", "").replace("41", "", 1) if address.startswith("41") else address
        return clean.zfill(64)


# ─────────────────────────  Aggregator  ───────────────────────────────────

async def _with_chain_timeout(coro, chain: str, wallet_address: str) -> List[TokenBalance]:
    """Wrap a chain fetch coroutine with CHAIN_TIMEOUT. Returns empty list on timeout."""
    try:
        return await asyncio.wait_for(coro, timeout=CHAIN_TIMEOUT)
    except asyncio.TimeoutError:
        logger.warning(f"Timeout fetching {chain} balance for {wallet_address[:10]}... (>{CHAIN_TIMEOUT}s)")
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
