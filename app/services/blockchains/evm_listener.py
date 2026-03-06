"""
EVM Blockchain Listener

Monitors EVM-compatible chains (Ethereum, Polygon, Base) for ERC20 token transfers.
Supports USDC, USDT, and PYUSD.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List, Set
from decimal import Decimal

from .base import BlockchainListener, BlockchainConfig, TokenConfig, PaymentInfo, ListenerStatus
from app.core.config import settings

logger = logging.getLogger(__name__)

# ERC20 Transfer event signature
ERC20_TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

# Standard ERC20 ABI for Transfer event
ERC20_ABI = [
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "from", "type": "address"},
            {"indexed": True, "name": "to", "type": "address"},
            {"indexed": False, "name": "value", "type": "uint256"}
        ],
        "name": "Transfer",
        "type": "event"
    },
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function"
    }
]

# Chain configurations with default RPC URLs
EVM_CHAIN_CONFIGS = {
    "ethereum": {
        "chain_id": 1,
        "rpc_urls": [
            "https://eth.llamarpc.com",
            "https://rpc.ankr.com/eth",
            "https://ethereum.publicnode.com"
        ],
        "confirmations": 12,
        "poll_interval": 15,
        "tokens": {
            "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
            "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
            "PYUSD": "0x6c3ea9036406852006290770BEdFcAbA0e23A0e8"
        }
    },
    "polygon": {
        "chain_id": 137,
        "rpc_urls": [
            "https://polygon-rpc.com",
            "https://rpc.ankr.com/polygon",
            "https://polygon.llamarpc.com"
        ],
        "confirmations": 64,
        "poll_interval": 5,
        "tokens": {
            "USDC": "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359",  # Native USDC
            "USDT": "0xc2132D05D31c914a87C6611C10748AEb04B58e8F"
        }
    },
    "base": {
        "chain_id": 8453,
        "rpc_urls": [
            "https://mainnet.base.org",
            "https://base.llamarpc.com",
            "https://rpc.ankr.com/base"
        ],
        "confirmations": 12,
        "poll_interval": 5,
        "tokens": {
            "USDC": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
        }
    }
}


class EVMListener(BlockchainListener):
    """
    EVM-compatible blockchain listener.
    
    Monitors for ERC20 Transfer events on Ethereum, Polygon, and Base.
    """
    
    def __init__(self, config: BlockchainConfig, tokens: List[TokenConfig]):
        super().__init__(config, tokens)
        self._web3 = None
        self._last_block = 0
        self._watched_addresses: Set[str] = set()
        
    @property
    def w3(self):
        """Lazy load web3 instance"""
        if self._web3 is None:
            try:
                from web3 import Web3
                from web3.middleware import geth_poa_middleware
                
                self._web3 = Web3(Web3.HTTPProvider(self.config.rpc_url))
                
                # Add PoA middleware for Polygon
                if self.config.chain in ["polygon", "base"]:
                    self._web3.middleware_onion.inject(geth_poa_middleware, layer=0)
                    
            except ImportError:
                logger.error("web3 package not installed. Run: pip install web3")
                raise
                
        return self._web3
        
    def add_watched_address(self, address: str):
        """Add address to watch for incoming transfers"""
        self._watched_addresses.add(address.lower())
        
    def remove_watched_address(self, address: str):
        """Remove address from watch list"""
        self._watched_addresses.discard(address.lower())
        
    async def start(self):
        """Start listening for EVM payments"""
        self.is_running = True
        self.status = ListenerStatus.STARTING
        logger.info(f"🚀 Starting {self.config.chain} listener on {self.config.rpc_url}")
        
        # Get starting block
        try:
            self._last_block = self.w3.eth.block_number - 10  # Start 10 blocks back
            logger.info(f"Starting from block {self._last_block}")
        except Exception as e:
            logger.error(f"Failed to get starting block: {e}")
            self._last_block = 0
            
        while self.is_running:
            try:
                self.status = ListenerStatus.RUNNING
                self._reset_retry_count()
                await self._poll_for_transfers()
            except Exception as e:
                logger.error(f"{self.config.chain} listener error: {e}")
                await self._notify_error(e)
                
                if self.is_running:
                    should_retry = await self._handle_reconnection()
                    if not should_retry:
                        break
                        
    async def stop(self):
        """Stop the listener"""
        self.is_running = False
        self.status = ListenerStatus.STOPPED
        logger.info(f"{self.config.chain} listener stopped")
        
    async def _poll_for_transfers(self):
        """Poll for ERC20 Transfer events"""
        while self.is_running:
            try:
                current_block = self.w3.eth.block_number
                
                if current_block <= self._last_block:
                    await asyncio.sleep(self.config.poll_interval_seconds)
                    continue
                    
                # Scan for transfers
                await self._scan_blocks(self._last_block + 1, current_block)
                self._last_block = current_block
                
                await asyncio.sleep(self.config.poll_interval_seconds)
                
            except Exception as e:
                logger.error(f"Error polling for transfers: {e}")
                raise
                
    async def _scan_blocks(self, from_block: int, to_block: int):
        """Scan block range for token transfers"""
        try:
            # Get token contract addresses
            token_addresses = list(self.tokens.keys())
            
            if not token_addresses:
                return
                
            # Build filter for Transfer events
            # Filter by token contracts we're interested in
            filter_params = {
                "fromBlock": from_block,
                "toBlock": to_block,
                "topics": [ERC20_TRANSFER_TOPIC]
            }
            
            # Get logs
            logs = self.w3.eth.get_logs(filter_params)
            
            for log in logs:
                await self._process_transfer_log(log, to_block)
                
        except Exception as e:
            logger.error(f"Error scanning blocks {from_block}-{to_block}: {e}")
            raise
            
    async def _process_transfer_log(self, log: Dict[str, Any], current_block: int):
        """Process a single Transfer event log"""
        try:
            # Get token address
            token_address = log["address"].lower()
            
            # Check if this is a token we're tracking
            token = self.get_token_by_address(token_address)
            if not token:
                return
                
            # Decode topics
            topics = log.get("topics", [])
            if len(topics) < 3:
                return
                
            # Extract from and to addresses (remove padding)
            from_address = "0x" + topics[1].hex()[-40:]
            to_address = "0x" + topics[2].hex()[-40:]
            
            # Check if to_address is one we're watching
            # If no addresses are being watched, process all transfers
            if self._watched_addresses and to_address.lower() not in self._watched_addresses:
                return
                
            # Decode amount from data
            data = log.get("data", "0x")
            if isinstance(data, bytes):
                data = data.hex()
            if data.startswith("0x"):
                data = data[2:]
                
            amount_raw = int(data, 16) if data else 0
            amount = str(Decimal(amount_raw) / Decimal(10 ** token.decimals))
            
            # Calculate confirmations
            block_number = log.get("blockNumber", 0)
            confirmations = current_block - block_number
            
            # Get transaction hash
            tx_hash = log.get("transactionHash")
            if isinstance(tx_hash, bytes):
                tx_hash = "0x" + tx_hash.hex()
                
            # Create payment info
            payment = PaymentInfo(
                tx_hash=tx_hash,
                chain=self.config.chain,
                token_symbol=token.symbol,
                token_address=token_address,
                from_address=from_address,
                to_address=to_address,
                amount=amount,
                amount_raw=amount_raw,
                block_number=block_number,
                confirmations=confirmations,
                timestamp=datetime.utcnow()
            )
            
            logger.info(
                f"💎 {self.config.chain.upper()} transfer: "
                f"{amount} {token.symbol} to {to_address[:10]}... "
                f"(block: {block_number}, confirmations: {confirmations})"
            )
            
            # Only notify if enough confirmations
            if confirmations >= self.config.confirmations_required:
                await self._notify_payment(payment)
            else:
                logger.info(f"Waiting for confirmations: {confirmations}/{self.config.confirmations_required}")
                
        except Exception as e:
            logger.error(f"Error processing transfer log: {e}")
            
    async def get_current_block(self) -> int:
        """Get current block number"""
        try:
            return self.w3.eth.block_number
        except Exception as e:
            logger.error(f"Error getting current block: {e}")
            return 0
            
    async def get_transaction(self, tx_hash: str) -> Optional[Dict[str, Any]]:
        """Get transaction details"""
        try:
            tx = self.w3.eth.get_transaction(tx_hash)
            receipt = self.w3.eth.get_transaction_receipt(tx_hash)
            
            return {
                "hash": tx_hash,
                "from": tx["from"],
                "to": tx["to"],
                "value": tx["value"],
                "blockNumber": tx["blockNumber"],
                "status": receipt["status"],
                "logs": receipt["logs"]
            }
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
        """Verify an EVM payment"""
        try:
            receipt = self.w3.eth.get_transaction_receipt(tx_hash)
            
            if not receipt or receipt["status"] != 1:
                logger.warning(f"Transaction {tx_hash} failed or not found")
                return False
                
            # Get current block for confirmation check
            current_block = self.w3.eth.block_number
            confirmations = current_block - receipt["blockNumber"]
            
            if confirmations < self.config.confirmations_required:
                logger.warning(
                    f"Insufficient confirmations: {confirmations}/{self.config.confirmations_required}"
                )
                return False
                
            # Find matching transfer in logs 
            for log in receipt["logs"]:
                # Check if it's a Transfer event
                if len(log["topics"]) < 3:
                    continue
                if log["topics"][0].hex() != ERC20_TRANSFER_TOPIC[2:]:
                    continue
                    
                # Get token info
                token_address = log["address"].lower()
                token = self.get_token_by_address(token_address)
                if not token or token.symbol != expected_token:
                    continue
                    
                # Check destination
                to_address = "0x" + log["topics"][2].hex()[-40:]
                if to_address.lower() != expected_to.lower():
                    continue
                    
                # Check amount
                data = log["data"]
                if isinstance(data, bytes):
                    data = data.hex()
                if data.startswith("0x"):
                    data = data[2:]
                    
                amount_raw = int(data, 16) if data else 0
                amount = Decimal(amount_raw) / Decimal(10 ** token.decimals)
                expected = Decimal(expected_amount)
                
                # Allow small difference for rounding
                if abs(amount - expected) < Decimal("0.01"):
                    logger.info(f"✅ Payment verified: {amount} {token.symbol}")
                    return True
                    
            logger.warning(f"No matching transfer found in transaction {tx_hash}")
            return False
            
        except Exception as e:
            logger.error(f"Error verifying payment: {e}")
            return False
            
    async def get_token_balance(self, address: str, token_address: str) -> str:
        """Get ERC20 token balance"""
        try:
            # Create contract instance
            contract = self.w3.eth.contract(
                address=self.w3.to_checksum_address(token_address),
                abi=ERC20_ABI
            )
            
            # Get balance
            balance_raw = contract.functions.balanceOf(
                self.w3.to_checksum_address(address)
            ).call()
            
            # Get decimals
            token = self.get_token_by_address(token_address)
            decimals = token.decimals if token else 6
            
            return str(Decimal(balance_raw) / Decimal(10 ** decimals))
            
        except Exception as e:
            logger.error(f"Error getting balance: {e}")
            return "0"


def create_evm_listener(chain: str, config: Dict[str, Any] = None) -> EVMListener:
    """
    Create EVM listener for a specific chain.
    
    Args:
        chain: Chain identifier (ethereum, polygon, base)
        config: Optional configuration override
        
    Returns:
        Configured EVMListener
    """
    config = config or {}
    chain = chain.lower()
    
    # Get default chain config
    chain_defaults = EVM_CHAIN_CONFIGS.get(chain, {})
    
    # Determine RPC URL
    rpc_url = config.get("rpc_url")
    if not rpc_url:
        env_var = f"{chain.upper()}_RPC_URL"
        rpc_url = getattr(settings, env_var, None) or chain_defaults.get("rpc_urls", [""])[0]
    
    blockchain_config = BlockchainConfig(
        chain=chain,
        rpc_url=rpc_url,
        chain_id=chain_defaults.get("chain_id"),
        confirmations_required=config.get("confirmations", chain_defaults.get("confirmations", 12)),
        poll_interval_seconds=config.get("poll_interval", chain_defaults.get("poll_interval", 10)),
        is_active=True
    )
    
    # Configure tokens
    tokens = []
    token_addresses = config.get("tokens", chain_defaults.get("tokens", {}))
    
    for symbol, address in token_addresses.items():
        tokens.append(TokenConfig(
            symbol=symbol,
            chain=chain,
            contract_address=address,
            decimals=6,  # Most stablecoins use 6 decimals
            is_active=True
        ))
    
    return EVMListener(blockchain_config, tokens)
