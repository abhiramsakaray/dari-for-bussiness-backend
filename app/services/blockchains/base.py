"""
Base classes for blockchain listeners

Abstract base class that all blockchain-specific listeners must implement.
Provides common functionality for payment detection, validation, and processing.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any, List, Callable
from enum import Enum

logger = logging.getLogger(__name__)


@dataclass
class BlockchainConfig:
    """Configuration for a blockchain network"""
    chain: str
    rpc_url: str
    chain_id: Optional[int] = None
    confirmations_required: int = 1
    poll_interval_seconds: int = 10
    is_active: bool = True


@dataclass
class TokenConfig:
    """Configuration for a token on a specific chain"""
    symbol: str  # USDC, USDT, PYUSD
    chain: str
    contract_address: str
    decimals: int = 6
    is_active: bool = True


@dataclass
class PaymentInfo:
    """Information about a detected payment"""
    tx_hash: str
    chain: str
    token_symbol: str
    token_address: str
    from_address: str
    to_address: str
    amount: str  # Human-readable amount
    amount_raw: int  # Raw amount in smallest unit
    block_number: int
    confirmations: int
    memo: Optional[str] = None  # For Stellar-like chains
    timestamp: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "tx_hash": self.tx_hash,
            "chain": self.chain,
            "token_symbol": self.token_symbol,
            "token_address": self.token_address,
            "from_address": self.from_address,
            "to_address": self.to_address,
            "amount": self.amount,
            "amount_raw": self.amount_raw,
            "block_number": self.block_number,
            "confirmations": self.confirmations,
            "memo": self.memo,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "metadata": self.metadata
        }


class ListenerStatus(Enum):
    """Status of a blockchain listener"""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    RECONNECTING = "reconnecting"
    ERROR = "error"


class BlockchainListener(ABC):
    """
    Abstract base class for blockchain payment listeners.
    
    Each blockchain implementation must:
    1. Monitor for incoming token transfers
    2. Match transactions to payment sessions  
    3. Verify amount and token
    4. Call the payment callback when valid payment detected
    """
    
    def __init__(self, config: BlockchainConfig, tokens: List[TokenConfig]):
        self.config = config
        self.tokens = {t.contract_address.lower(): t for t in tokens}
        self.status = ListenerStatus.STOPPED
        self.is_running = False
        self.cursor: Optional[str] = None  # For pagination/streaming
        self._payment_callback: Optional[Callable] = None
        self._error_callback: Optional[Callable] = None
        self._retry_count = 0
        self._max_retries = 5
        self._retry_delay = 5  # seconds
        
    @property
    def chain(self) -> str:
        """Get chain identifier"""
        return self.config.chain
    
    def set_payment_callback(self, callback: Callable[[PaymentInfo], Any]):
        """Set callback for when a payment is detected"""
        self._payment_callback = callback
        
    def set_error_callback(self, callback: Callable[[Exception], Any]):
        """Set callback for when an error occurs"""
        self._error_callback = callback
    
    @abstractmethod
    async def start(self):
        """Start listening for payments"""
        pass
    
    @abstractmethod
    async def stop(self):
        """Stop listening for payments"""
        pass
    
    @abstractmethod
    async def get_current_block(self) -> int:
        """Get current block number"""
        pass
    
    @abstractmethod
    async def get_transaction(self, tx_hash: str) -> Optional[Dict[str, Any]]:
        """Get transaction details by hash"""
        pass
    
    @abstractmethod
    async def verify_payment(
        self,
        tx_hash: str,
        expected_to: str,
        expected_amount: str,
        expected_token: str,
        memo: Optional[str] = None
    ) -> bool:
        """
        Verify a specific payment transaction.
        
        Args:
            tx_hash: Transaction hash
            expected_to: Expected destination address
            expected_amount: Expected amount (human-readable)
            expected_token: Expected token symbol
            memo: Expected memo (for Stellar)
            
        Returns:
            True if payment is valid
        """
        pass
    
    @abstractmethod
    async def get_token_balance(self, address: str, token_address: str) -> str:
        """Get token balance for an address"""
        pass
    
    async def _notify_payment(self, payment: PaymentInfo):
        """Notify about detected payment"""
        if self._payment_callback:
            try:
                if asyncio.iscoroutinefunction(self._payment_callback):
                    await self._payment_callback(payment)
                else:
                    self._payment_callback(payment)
            except Exception as e:
                logger.error(f"Error in payment callback: {e}")
                
    async def _notify_error(self, error: Exception):
        """Notify about error"""
        if self._error_callback:
            try:
                if asyncio.iscoroutinefunction(self._error_callback):
                    await self._error_callback(error)
                else:
                    self._error_callback(error)
            except Exception as e:
                logger.error(f"Error in error callback: {e}")
    
    async def _handle_reconnection(self):
        """Handle reconnection with exponential backoff"""
        self._retry_count += 1
        if self._retry_count > self._max_retries:
            self.status = ListenerStatus.ERROR
            logger.error(f"[{self.chain}] Max retries exceeded, stopping listener")
            return False
            
        delay = self._retry_delay * (2 ** (self._retry_count - 1))
        logger.warning(f"[{self.chain}] Reconnecting in {delay}s (attempt {self._retry_count}/{self._max_retries})")
        self.status = ListenerStatus.RECONNECTING
        await asyncio.sleep(delay)
        return True
    
    def _reset_retry_count(self):
        """Reset retry count after successful connection"""
        self._retry_count = 0
        
    def get_token_by_address(self, address: str) -> Optional[TokenConfig]:
        """Get token config by contract address"""
        return self.tokens.get(address.lower())
    
    def get_token_by_symbol(self, symbol: str) -> Optional[TokenConfig]:
        """Get token config by symbol"""
        for token in self.tokens.values():
            if token.symbol.upper() == symbol.upper():
                return token
        return None
    
    def format_amount(self, raw_amount: int, decimals: int) -> str:
        """Convert raw amount to human-readable format"""
        return str(raw_amount / (10 ** decimals))
    
    def parse_amount(self, amount: str, decimals: int) -> int:
        """Convert human-readable amount to raw format"""
        return int(float(amount) * (10 ** decimals))
