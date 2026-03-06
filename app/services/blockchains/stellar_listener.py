"""
Stellar Blockchain Listener

Monitors Stellar network for USDC/XLM payments.
This is an adapter that integrates the existing Stellar listener with the new abstraction layer.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

from stellar_sdk import Server, Asset
from stellar_sdk.exceptions import BaseHorizonError

from .base import BlockchainListener, BlockchainConfig, TokenConfig, PaymentInfo, ListenerStatus
from app.core.config import settings

logger = logging.getLogger(__name__)


class StellarListener(BlockchainListener):
    """
    Stellar network payment listener.
    
    Monitors for USDC transfers using Horizon streaming API.
    Supports memo-based payment matching for sessions.
    """
    
    def __init__(self, config: BlockchainConfig, tokens: List[TokenConfig]):
        super().__init__(config, tokens)
        self.server = Server(horizon_url=config.rpc_url)
        self.cursor = "now"
        
    async def start(self):
        """Start listening for Stellar payments"""
        self.is_running = True
        self.status = ListenerStatus.STARTING
        logger.info(f"🚀 Starting Stellar listener on {self.config.rpc_url}")
        
        while self.is_running:
            try:
                self.status = ListenerStatus.RUNNING
                self._reset_retry_count()
                await self._listen_for_payments()
            except Exception as e:
                logger.error(f"Stellar listener error: {e}")
                await self._notify_error(e)
                
                if self.is_running:
                    should_retry = await self._handle_reconnection()
                    if not should_retry:
                        break
                        
    async def stop(self):
        """Stop the listener"""
        self.is_running = False
        self.status = ListenerStatus.STOPPED
        logger.info("Stellar listener stopped")
        
    async def _listen_for_payments(self):
        """Listen for payment operations on Stellar"""
        # Use polling approach for better reliability
        while self.is_running:
            try:
                # Get recent transactions
                transactions = self.server.transactions().order(
                    desc=False
                ).cursor(self.cursor).limit(100).call()
                
                records = transactions.get("_embedded", {}).get("records", [])
                
                for tx in records:
                    self.cursor = tx.get("paging_token", self.cursor)
                    await self._process_transaction(tx)
                    
                # Sleep before next poll
                await asyncio.sleep(self.config.poll_interval_seconds)
                
            except BaseHorizonError as e:
                logger.error(f"Horizon API error: {e}")
                raise
            except Exception as e:
                logger.error(f"Error in payment loop: {e}")
                raise
                
    async def _process_transaction(self, tx: Dict[str, Any]):
        """Process a single transaction"""
        try:
            tx_hash = tx.get("id")
            memo = tx.get("memo")
            
            if not memo:
                return  # Skip transactions without memo
                
            # Get operations for this transaction
            operations = self.server.operations().for_transaction(tx_hash).call()
            
            for op in operations.get("_embedded", {}).get("records", []):
                await self._process_operation(op, tx_hash, memo)
                
        except Exception as e:
            logger.error(f"Error processing transaction {tx.get('id')}: {e}")
            
    async def _process_operation(self, operation: Dict[str, Any], tx_hash: str, memo: str):
        """Process a payment operation"""
        op_type = operation.get("type")
        
        if op_type not in ["payment", "path_payment_strict_receive", "path_payment_strict_send"]:
            return
            
        # Extract payment details
        destination = operation.get("to") or operation.get("destination")
        amount = operation.get("amount")
        asset_type = operation.get("asset_type")
        asset_code = operation.get("asset_code", "XLM")
        asset_issuer = operation.get("asset_issuer", "")
        from_address = operation.get("from")
        
        if not destination or not amount:
            return
            
        # Determine token
        if asset_type == "native":
            token_symbol = "XLM"
            token_address = "native"
        else:
            token_symbol = asset_code
            token_address = asset_issuer
            
        # Check if this is a token we're tracking
        is_tracked = False
        for token in self.tokens.values():
            if token.symbol == token_symbol:
                is_tracked = True
                break
                
        if not is_tracked and token_symbol != "XLM":
            return
            
        # Create payment info
        payment = PaymentInfo(
            tx_hash=tx_hash,
            chain="stellar",
            token_symbol=token_symbol,
            token_address=token_address,
            from_address=from_address,
            to_address=destination,
            amount=amount,
            amount_raw=int(float(amount) * 10**7),  # Stellar uses 7 decimals
            block_number=0,  # Stellar doesn't have traditional blocks
            confirmations=1,  # Stellar has instant finality
            memo=memo,
            timestamp=datetime.utcnow()
        )
        
        logger.info(f"💫 Stellar payment detected: {amount} {token_symbol} to {destination[:8]}... memo={memo}")
        await self._notify_payment(payment)
        
    async def get_current_block(self) -> int:
        """Get current ledger sequence (Stellar's equivalent of block)"""
        try:
            root = self.server.root().call()
            return root.get("history_latest_ledger", 0)
        except Exception as e:
            logger.error(f"Error getting current ledger: {e}")
            return 0
            
    async def get_transaction(self, tx_hash: str) -> Optional[Dict[str, Any]]:
        """Get transaction details"""
        try:
            tx = self.server.transactions().transaction(tx_hash).call()
            return tx
        except Exception as e:
            logger.error(f"Error getting transaction {tx_hash}: {e}")
            return None
            
    async def verify_payment(
        self,
        tx_hash: str,
        expected_to: str,
        expected_amount: str,
        expected_token: str,
        memo: Optional[str] = None
    ) -> bool:
        """Verify a Stellar payment"""
        try:
            tx = await self.get_transaction(tx_hash)
            if not tx:
                return False
                
            # Check memo
            if memo and tx.get("memo") != memo:
                logger.warning(f"Memo mismatch: expected {memo}, got {tx.get('memo')}")
                return False
                
            # Get operations
            operations = self.server.operations().for_transaction(tx_hash).call()
            
            for op in operations.get("_embedded", {}).get("records", []):
                if op.get("type") not in ["payment", "path_payment_strict_receive"]:
                    continue
                    
                destination = op.get("to") or op.get("destination")
                amount = op.get("amount")
                asset_code = op.get("asset_code", "XLM")
                
                if destination == expected_to:
                    if asset_code == expected_token or expected_token == "XLM":
                        received = float(amount)
                        expected = float(expected_amount)
                        if abs(received - expected) < 0.01:
                            return True
                            
            return False
            
        except Exception as e:
            logger.error(f"Error verifying payment: {e}")
            return False
            
    async def get_token_balance(self, address: str, token_address: str) -> str:
        """Get token balance for an address"""
        try:
            account = self.server.accounts().account_id(address).call()
            balances = account.get("balances", [])
            
            for balance in balances:
                if token_address == "native" and balance.get("asset_type") == "native":
                    return balance.get("balance", "0")
                elif balance.get("asset_issuer") == token_address:
                    return balance.get("balance", "0")
                    
            return "0"
        except Exception as e:
            logger.error(f"Error getting balance: {e}")
            return "0"


def create_stellar_listener(config: Dict[str, Any] = None) -> StellarListener:
    """
    Create Stellar listener with configuration.
    
    Args:
        config: Optional configuration override
        
    Returns:
        Configured StellarListener
    """
    config = config or {}
    
    blockchain_config = BlockchainConfig(
        chain="stellar",
        rpc_url=config.get("horizon_url", settings.STELLAR_HORIZON_URL),
        confirmations_required=1,  # Instant finality
        poll_interval_seconds=config.get("poll_interval", 5),
        is_active=True
    )
    
    # Configure USDC token on Stellar
    tokens = [
        TokenConfig(
            symbol="USDC",
            chain="stellar",
            contract_address=config.get("usdc_issuer", settings.USDC_ASSET_ISSUER),
            decimals=7,
            is_active=True
        )
    ]
    
    return StellarListener(blockchain_config, tokens)
