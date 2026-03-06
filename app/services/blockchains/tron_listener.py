"""
Tron Blockchain Listener

Monitors Tron network for TRC20 token transfers.
Primarily used for USDT on Tron (TRC20-USDT).
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List, Set
from decimal import Decimal
import httpx

from .base import BlockchainListener, BlockchainConfig, TokenConfig, PaymentInfo, ListenerStatus
from app.core.config import settings

logger = logging.getLogger(__name__)

# Tron configuration
TRON_CONFIGS = {
    "mainnet": {
        "api_url": "https://api.trongrid.io",
        "tokens": {
            "USDT": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"  # TRC20 USDT
        }
    },
    "testnet": {
        "api_url": "https://api.shasta.trongrid.io",
        "tokens": {
            "USDT": "TG3XXyExBkPp9nzdajDZsozEu4BkaSJozs"  # Testnet USDT
        }
    }
}


class TronListener(BlockchainListener):
    """
    Tron network payment listener.
    
    Monitors for TRC20 transfers using TronGrid API.
    """
    
    def __init__(self, config: BlockchainConfig, tokens: List[TokenConfig]):
        super().__init__(config, tokens)
        self._api_key = None
        self._last_timestamp = 0
        self._watched_addresses: Set[str] = set()
        self._http_client = None
        
    @property
    def client(self) -> httpx.AsyncClient:
        """Get async HTTP client"""
        if self._http_client is None or self._http_client.is_closed:
            headers = {}
            if self._api_key:
                headers["TRON-PRO-API-KEY"] = self._api_key
            self._http_client = httpx.AsyncClient(
                base_url=self.config.rpc_url,
                headers=headers,
                timeout=30.0
            )
        return self._http_client
        
    def set_api_key(self, api_key: str):
        """Set TronGrid API key for higher rate limits"""
        self._api_key = api_key
        
    def add_watched_address(self, address: str):
        """Add address to watch for incoming transfers"""
        self._watched_addresses.add(address)
        
    def remove_watched_address(self, address: str):
        """Remove address from watch list"""
        self._watched_addresses.discard(address)
        
    async def start(self):
        """Start listening for Tron payments"""
        self.is_running = True
        self.status = ListenerStatus.STARTING
        logger.info(f"🚀 Starting Tron listener on {self.config.rpc_url}")
        
        # Set initial timestamp
        self._last_timestamp = int(datetime.utcnow().timestamp() * 1000)
        
        while self.is_running:
            try:
                self.status = ListenerStatus.RUNNING
                self._reset_retry_count()
                await self._poll_for_transfers()
            except Exception as e:
                logger.error(f"Tron listener error: {e}")
                await self._notify_error(e)
                
                if self.is_running:
                    should_retry = await self._handle_reconnection()
                    if not should_retry:
                        break
                        
    async def stop(self):
        """Stop the listener"""
        self.is_running = False
        self.status = ListenerStatus.STOPPED
        if self._http_client:
            await self._http_client.aclose()
        logger.info("Tron listener stopped")
        
    async def _poll_for_transfers(self):
        """Poll for TRC20 transfers"""
        while self.is_running:
            try:
                # Poll transfers for each watched address
                for address in list(self._watched_addresses):
                    await self._check_address_transfers(address)
                    
                # Also poll for all token contracts if no specific addresses
                if not self._watched_addresses:
                    for token in self.tokens.values():
                        await self._check_token_transfers(token.contract_address)
                        
                await asyncio.sleep(self.config.poll_interval_seconds)
                
            except Exception as e:
                logger.error(f"Error polling for transfers: {e}")
                raise
                
    async def _check_address_transfers(self, address: str):
        """Check TRC20 transfers to a specific address"""
        try:
            # Get TRC20 transfers for this address
            response = await self.client.get(
                f"/v1/accounts/{address}/transactions/trc20",
                params={
                    "only_to": "true",
                    "min_timestamp": self._last_timestamp,
                    "limit": 50
                }
            )
            
            if response.status_code != 200:
                logger.error(f"TronGrid API error: {response.text}")
                return
                
            data = response.json()
            transfers = data.get("data", [])
            
            for transfer in transfers:
                await self._process_transfer(transfer)
                
            # Update timestamp
            if transfers:
                latest = max(t.get("block_timestamp", 0) for t in transfers)
                self._last_timestamp = max(self._last_timestamp, latest + 1)
                
        except Exception as e:
            logger.error(f"Error checking transfers for {address}: {e}")
            
    async def _check_token_transfers(self, token_address: str):
        """Check recent transfers for a token contract"""
        try:
            response = await self.client.get(
                f"/v1/contracts/{token_address}/events",
                params={
                    "event_name": "Transfer",
                    "min_block_timestamp": self._last_timestamp,
                    "limit": 50
                }
            )
            
            if response.status_code != 200:
                return
                
            data = response.json()
            events = data.get("data", [])
            
            for event in events:
                await self._process_event(event, token_address)
                
        except Exception as e:
            logger.error(f"Error checking token transfers: {e}")
            
    async def _process_transfer(self, transfer: Dict[str, Any]):
        """Process a TRC20 transfer from /transactions/trc20 endpoint"""
        try:
            token_info = transfer.get("token_info", {})
            token_address = token_info.get("address", "")
            
            # Check if this is a token we're tracking
            token = self.get_token_by_address(token_address)
            if not token:
                return
                
            # Extract transfer details
            tx_hash = transfer.get("transaction_id")
            from_address = transfer.get("from")
            to_address = transfer.get("to")
            value = transfer.get("value", "0")
            block_number = transfer.get("block_timestamp", 0)
            
            # Convert value
            decimals = int(token_info.get("decimals", token.decimals))
            amount_raw = int(value)
            amount = str(Decimal(amount_raw) / Decimal(10 ** decimals))
            
            # Create payment info
            payment = PaymentInfo(
                tx_hash=tx_hash,
                chain="tron",
                token_symbol=token.symbol,
                token_address=token_address,
                from_address=from_address,
                to_address=to_address,
                amount=amount,
                amount_raw=amount_raw,
                block_number=block_number,
                confirmations=19,  # Tron has ~19 block finality
                timestamp=datetime.fromtimestamp(block_number / 1000) if block_number else datetime.utcnow()
            )
            
            logger.info(
                f"🔷 TRON transfer: {amount} {token.symbol} "
                f"to {to_address[:10]}..."
            )
            
            await self._notify_payment(payment)
            
        except Exception as e:
            logger.error(f"Error processing transfer: {e}")
            
    async def _process_event(self, event: Dict[str, Any], token_address: str):
        """Process a Transfer event"""
        try:
            token = self.get_token_by_address(token_address)
            if not token:
                return
                
            result = event.get("result", {})
            
            # Extract addresses (convert from hex if needed)
            from_address = result.get("from") or result.get("_from")
            to_address = result.get("to") or result.get("_to")
            value = result.get("value") or result.get("_value", "0")
            
            # Check if to_address is one we're watching
            if self._watched_addresses and to_address not in self._watched_addresses:
                return
                
            # Convert value
            amount_raw = int(value)
            amount = str(Decimal(amount_raw) / Decimal(10 ** token.decimals))
            
            tx_hash = event.get("transaction_id")
            block_number = event.get("block_number", 0)
            
            payment = PaymentInfo(
                tx_hash=tx_hash,
                chain="tron",
                token_symbol=token.symbol,
                token_address=token_address,
                from_address=from_address,
                to_address=to_address,
                amount=amount,
                amount_raw=amount_raw,
                block_number=block_number,
                confirmations=19,
                timestamp=datetime.utcnow()
            )
            
            await self._notify_payment(payment)
            
        except Exception as e:
            logger.error(f"Error processing event: {e}")
            
    async def get_current_block(self) -> int:
        """Get current block number"""
        try:
            response = await self.client.get("/wallet/getnowblock")
            if response.status_code == 200:
                data = response.json()
                return data.get("block_header", {}).get("raw_data", {}).get("number", 0)
            return 0
        except Exception as e:
            logger.error(f"Error getting current block: {e}")
            return 0
            
    async def get_transaction(self, tx_hash: str) -> Optional[Dict[str, Any]]:
        """Get transaction details"""
        try:
            response = await self.client.get(f"/v1/transactions/{tx_hash}")
            if response.status_code == 200:
                data = response.json()
                return data.get("data", [{}])[0]
            return None
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
        """Verify a Tron payment"""
        try:
            # Get transaction info
            response = await self.client.get(
                f"/v1/transactions/{tx_hash}/events"
            )
            
            if response.status_code != 200:
                return False
                
            data = response.json()
            events = data.get("data", [])
            
            for event in events:
                if event.get("event_name") != "Transfer":
                    continue
                    
                result = event.get("result", {})
                to_address = result.get("to") or result.get("_to")
                value = result.get("value") or result.get("_value", "0")
                contract_address = event.get("contract_address")
                
                # Check token
                token = self.get_token_by_address(contract_address)
                if not token or token.symbol != expected_token:
                    continue
                    
                # Check destination
                if to_address != expected_to:
                    continue
                    
                # Check amount
                amount_raw = int(value)
                amount = Decimal(amount_raw) / Decimal(10 ** token.decimals)
                expected = Decimal(expected_amount)
                
                if abs(amount - expected) < Decimal("0.01"):
                    logger.info(f"✅ Tron payment verified: {amount} {token.symbol}")
                    return True
                    
            return False
            
        except Exception as e:
            logger.error(f"Error verifying payment: {e}")
            return False
            
    async def get_token_balance(self, address: str, token_address: str) -> str:
        """Get TRC20 token balance"""
        try:
            response = await self.client.get(
                f"/v1/accounts/{address}/tokens",
                params={"token_id": token_address}
            )
            
            if response.status_code == 200:
                data = response.json()
                for token_data in data.get("data", []):
                    if token_data.get("token_id") == token_address:
                        balance = token_data.get("balance", "0")
                        decimals = token_data.get("token_decimal", 6)
                        return str(Decimal(balance) / Decimal(10 ** int(decimals)))
                        
            return "0"
            
        except Exception as e:
            logger.error(f"Error getting balance: {e}")
            return "0"


def create_tron_listener(config: Dict[str, Any] = None) -> TronListener:
    """
    Create Tron listener with configuration.
    
    Args:
        config: Optional configuration override
        
    Returns:
        Configured TronListener
    """
    config = config or {}
    
    # Determine network
    network = config.get("network", "mainnet")
    network_config = TRON_CONFIGS.get(network, TRON_CONFIGS["mainnet"])
    
    blockchain_config = BlockchainConfig(
        chain="tron",
        rpc_url=config.get("api_url", network_config["api_url"]),
        confirmations_required=config.get("confirmations", 19),
        poll_interval_seconds=config.get("poll_interval", 10),
        is_active=True
    )
    
    # Configure tokens
    tokens = []
    token_addresses = config.get("tokens", network_config.get("tokens", {}))
    
    for symbol, address in token_addresses.items():
        tokens.append(TokenConfig(
            symbol=symbol,
            chain="tron",
            contract_address=address,
            decimals=6,
            is_active=True
        ))
    
    listener = TronListener(blockchain_config, tokens)
    
    # Set API key if provided
    api_key = config.get("api_key") or getattr(settings, "TRON_API_KEY", None)
    if api_key:
        listener.set_api_key(api_key)
    
    return listener
