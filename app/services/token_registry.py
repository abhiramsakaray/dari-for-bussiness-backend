"""
Token Registry Service

Manages supported tokens across all blockchain networks.
Provides centralized token configuration and lookup.
"""

import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ChainType(str, Enum):
    """Blockchain network types"""
    STELLAR = "stellar"
    ETHEREUM = "ethereum"
    POLYGON = "polygon"
    BASE = "base"
    TRON = "tron"
    SOLANA = "solana"


@dataclass
class TokenInfo:
    """Token information"""
    symbol: str
    name: str
    chain: str
    contract_address: str
    decimals: int
    icon_url: Optional[str] = None
    is_active: bool = True
    coingecko_id: Optional[str] = None  # For price lookups

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "chain": self.chain,
            "contract_address": self.contract_address,
            "decimals": self.decimals,
            "icon_url": self.icon_url,
            "is_active": self.is_active
        }


# Default supported tokens
DEFAULT_TOKENS = [
    # Stellar
    TokenInfo(
        symbol="USDC",
        name="USD Coin",
        chain="stellar",
        contract_address="GBBD47IF6LWK7P7MDEVSCWR7DPUWV3NY3DTQEVFL4NAT4AQH3ZLLFLA5",
        decimals=7,
        coingecko_id="usd-coin"
    ),
    
    # Ethereum
    TokenInfo(
        symbol="USDC",
        name="USD Coin",
        chain="ethereum",
        contract_address="0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        decimals=6,
        coingecko_id="usd-coin"
    ),
    TokenInfo(
        symbol="USDT",
        name="Tether USD",
        chain="ethereum",
        contract_address="0xdAC17F958D2ee523a2206206994597C13D831ec7",
        decimals=6,
        coingecko_id="tether"
    ),
    TokenInfo(
        symbol="PYUSD",
        name="PayPal USD",
        chain="ethereum",
        contract_address="0x6c3ea9036406852006290770BEdFcAbA0e23A0e8",
        decimals=6,
        coingecko_id="paypal-usd"
    ),
    
    # Polygon
    TokenInfo(
        symbol="USDC",
        name="USD Coin",
        chain="polygon",
        contract_address="0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359",  # Native USDC
        decimals=6,
        coingecko_id="usd-coin"
    ),
    TokenInfo(
        symbol="USDT",
        name="Tether USD",
        chain="polygon",
        contract_address="0xc2132D05D31c914a87C6611C10748AEb04B58e8F",
        decimals=6,
        coingecko_id="tether"
    ),
    
    # Base
    TokenInfo(
        symbol="USDC",
        name="USD Coin",
        chain="base",
        contract_address="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        decimals=6,
        coingecko_id="usd-coin"
    ),
    
    # Tron
    TokenInfo(
        symbol="USDT",
        name="Tether USD (TRC20)",
        chain="tron",
        contract_address="TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
        decimals=6,
        coingecko_id="tether"
    ),
]


class TokenRegistry:
    """
    Token registry for managing supported tokens.
    
    Provides lookup and validation for tokens across all chains.
    """
    
    def __init__(self):
        self._tokens: Dict[str, TokenInfo] = {}
        self._load_default_tokens()
        
    def _load_default_tokens(self):
        """Load default token configurations"""
        for token in DEFAULT_TOKENS:
            key = self._make_key(token.chain, token.symbol)
            self._tokens[key] = token
            
    def _make_key(self, chain: str, symbol: str) -> str:
        """Create lookup key"""
        return f"{chain.lower()}:{symbol.upper()}"
        
    def register_token(self, token: TokenInfo):
        """Register a new token"""
        key = self._make_key(token.chain, token.symbol)
        self._tokens[key] = token
        logger.info(f"Registered token: {token.symbol} on {token.chain}")
        
    def get_token(self, chain: str, symbol: str) -> Optional[TokenInfo]:
        """Get token by chain and symbol"""
        key = self._make_key(chain, symbol)
        return self._tokens.get(key)
        
    def get_token_by_address(self, chain: str, address: str) -> Optional[TokenInfo]:
        """Get token by contract address"""
        address_lower = address.lower()
        for token in self._tokens.values():
            if token.chain.lower() == chain.lower():
                if token.contract_address.lower() == address_lower:
                    return token
        return None
        
    def get_tokens_for_chain(self, chain: str) -> List[TokenInfo]:
        """Get all tokens for a specific chain"""
        return [t for t in self._tokens.values() if t.chain.lower() == chain.lower() and t.is_active]
        
    def get_chains_for_token(self, symbol: str) -> List[str]:
        """Get all chains that support a token"""
        return [t.chain for t in self._tokens.values() if t.symbol.upper() == symbol.upper() and t.is_active]
        
    def get_all_tokens(self) -> List[TokenInfo]:
        """Get all registered tokens"""
        return list(self._tokens.values())
        
    def get_active_tokens(self) -> List[TokenInfo]:
        """Get all active tokens"""
        return [t for t in self._tokens.values() if t.is_active]
        
    def get_supported_chains(self) -> List[str]:
        """Get list of all supported chains"""
        return list(set(t.chain for t in self._tokens.values() if t.is_active))
        
    def get_supported_symbols(self) -> List[str]:
        """Get list of all supported token symbols"""
        return list(set(t.symbol for t in self._tokens.values() if t.is_active))
        
    def is_valid_combination(self, chain: str, symbol: str) -> bool:
        """Check if chain/token combination is valid"""
        token = self.get_token(chain, symbol)
        return token is not None and token.is_active
        
    def get_payment_options(
        self,
        accepted_tokens: Optional[List[str]] = None,
        accepted_chains: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Get available payment options based on accepted tokens and chains.
        
        Args:
            accepted_tokens: List of accepted token symbols (e.g., ["USDC", "USDT"])
            accepted_chains: List of accepted chains (e.g., ["polygon", "ethereum"])
            
        Returns:
            List of payment options
        """
        options = []
        
        for token in self.get_active_tokens():
            # Filter by accepted tokens
            if accepted_tokens and token.symbol not in accepted_tokens:
                continue
                
            # Filter by accepted chains
            if accepted_chains and token.chain not in accepted_chains:
                continue
                
            options.append({
                "symbol": token.symbol,
                "name": token.name,
                "chain": token.chain,
                "chain_display": self._get_chain_display_name(token.chain),
                "contract_address": token.contract_address,
                "decimals": token.decimals,
                "icon_url": token.icon_url,
                "label": f"{token.symbol} ({token.chain.capitalize()})"
            })
            
        return options
        
    def _get_chain_display_name(self, chain: str) -> str:
        """Get display name for chain"""
        names = {
            "stellar": "Stellar",
            "ethereum": "Ethereum",
            "polygon": "Polygon",
            "base": "Base",
            "tron": "Tron",
            "solana": "Solana"
        }
        return names.get(chain.lower(), chain.capitalize())


# Singleton instance
_registry: Optional[TokenRegistry] = None


def get_token_registry() -> TokenRegistry:
    """Get singleton token registry"""
    global _registry
    if _registry is None:
        _registry = TokenRegistry()
    return _registry
