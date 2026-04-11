"""
EVM Blockchain Listener

Monitors EVM-compatible chains (Ethereum, Polygon, Base) for ERC20 token transfers.
Supports USDC, USDT, and PYUSD.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Set
from decimal import Decimal
from sqlalchemy.orm import Session

from .base import BlockchainListener, BlockchainConfig, TokenConfig, PaymentInfo, ListenerStatus
from app.core.config import settings
from app.core.database import SessionLocal
from app.models import MerchantWallet
from app.models import PaymentSession, PaymentStatus
from app.services.webhook_service import send_webhook

logger = logging.getLogger(__name__)


def _match_session(candidates, payment: PaymentInfo):
    """Find the best matching PaymentSession for a detected transfer.

    Matching rules (in priority order):
    1. Wallet match + amount match (±2 %)
    2. Wallet match only (single candidate – accept any amount)
    """
    paid_amount = Decimal(str(payment.amount))
    to_addr = payment.to_address.lower()

    wallet_matches = []
    for session in candidates:
        # Match on merchant_wallet OR deposit_address
        session_addr = (session.merchant_wallet or session.deposit_address or "").lower()
        if not session_addr or session_addr != to_addr:
            continue
        wallet_matches.append(session)

    if not wallet_matches:
        return None

    # Try amount match first (±2 % tolerance)
    for session in wallet_matches:
        expected = Decimal(str(session.amount_token or session.amount_usdc or "0"))
        if expected == 0:
            continue
        diff_pct = abs(expected - paid_amount) / expected * 100 if expected else 100
        if diff_pct <= Decimal("2"):
            return session

    # Fallback: if only one session for this wallet, take it
    if len(wallet_matches) == 1:
        logger.info(
            f"Fuzzy match: single open session {wallet_matches[0].id} for wallet {to_addr[:10]}..."
        )
        return wallet_matches[0]

    return None


async def _mark_session_pending(payment: PaymentInfo):
    """Mark a matching session as PENDING on first detection (0-conf)."""
    db = SessionLocal()
    try:
        candidates = db.query(PaymentSession).filter(
            PaymentSession.status == PaymentStatus.CREATED,
            PaymentSession.chain == payment.chain,
            PaymentSession.token == payment.token_symbol,
        ).order_by(PaymentSession.created_at.desc()).all()

        session = _match_session(candidates, payment)
        if not session:
            logger.info(
                f"No open session to mark PENDING for tx {payment.tx_hash} "
                f"({payment.amount} {payment.token_symbol} to {payment.to_address[:10]}...)"
            )
            return

        session.status = PaymentStatus.PENDING
        session.tx_hash = payment.tx_hash
        session.block_number = payment.block_number
        session.confirmations = payment.confirmations
        db.commit()
        logger.info(
            f"⏳ Marked session {session.id} as PENDING "
            f"(tx {payment.tx_hash[:16]}..., {payment.confirmations} conf)"
        )
    except Exception as e:
        logger.error(f"Error marking session PENDING: {e}")
        db.rollback()
    finally:
        db.close()


async def process_evm_payment(payment: PaymentInfo):
    """Match confirmed EVM transfer to an open session and mark it PAID."""
    db = SessionLocal()
    try:
        # Look at CREATED *and* PENDING sessions (PENDING = already detected at 0-conf)
        candidates = db.query(PaymentSession).filter(
            PaymentSession.status.in_([PaymentStatus.CREATED, PaymentStatus.PENDING]),
            PaymentSession.chain == payment.chain,
            PaymentSession.token == payment.token_symbol,
        ).order_by(PaymentSession.created_at.desc()).all()

        matched_session = _match_session(candidates, payment)

        if not matched_session:
            logger.info(
                f"No matching open session for confirmed tx {payment.tx_hash} "
                f"({payment.amount} {payment.token_symbol} to {payment.to_address[:10]}...)"
            )
            return

        matched_session.status = PaymentStatus.PAID
        matched_session.tx_hash = payment.tx_hash
        matched_session.block_number = payment.block_number
        matched_session.confirmations = payment.confirmations
        matched_session.paid_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(matched_session)

        logger.info(
            f"✅ Marked session {matched_session.id} as PAID "
            f"from {payment.chain} tx {payment.tx_hash}"
        )

        # Credit merchant balance
        try:
            from app.services.payment_utils import credit_merchant_balance
            payment_token = matched_session.token or "USDC"
            credit_amount = matched_session.amount_token or matched_session.amount_usdc or "0"
            credit_merchant_balance(db, matched_session.merchant_id, payment_token, credit_amount)
        except Exception as be:
            logger.error(f"Error crediting balance for session {matched_session.id}: {be}")

        # Trigger merchant webhook for the confirmed payment.
        await send_webhook(matched_session, db)

    except Exception as e:
        logger.error(f"Error processing EVM payment callback: {e}")
        db.rollback()
    finally:
        db.close()

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

# Chain configurations for mainnet and testnet
EVM_CHAIN_CONFIGS = {
    "ethereum": {
        "mainnet": {
            "chain_id": 1,
            "rpc_urls": [
                "https://eth.llamarpc.com",
                "https://rpc.ankr.com/eth",
                "https://ethereum.publicnode.com"
            ],
            "tokens": {
                "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
                "PYUSD": "0x6c3ea9036406852006290770BEdFcAbA0e23A0e8"
            }
        },
        "testnet": {
            "chain_id": 11155111,
            "rpc_urls": [
                "https://rpc.sepolia.org",
                "https://rpc2.sepolia.org",
                "https://ethereum-sepolia.publicnode.com"
            ],
            "tokens": {
                "USDC": "0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238",
                "USDT": "0x7169D38820dfd117C3FA1f22a697dBA58d90BA06",
                "PYUSD": "0xCaC524BcA292aaade2DF8A05cC58F0a65B1B3bB9"
            }
        },
        "confirmations": 12,
        "poll_interval": 15,
    },
    "polygon": {
        "mainnet": {
            "chain_id": 137,
            "rpc_urls": [
                "https://polygon-rpc.com",
                "https://rpc.ankr.com/polygon",
                "https://polygon.llamarpc.com"
            ],
            "tokens": {
                "USDC": "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359",
                "USDT": "0xc2132D05D31c914a87C6611C10748AEb04B58e8F"
            }
        },
        "testnet": {
            "chain_id": 80002,
            "rpc_urls": [
                "https://rpc-amoy.polygon.technology",
                "https://polygon-amoy.drpc.org"
            ],
            "tokens": {
                "USDC": "0x8B0180f2101c8260d49339abfEe87927412494B4",
                "USDT": "0xcab2F429509bFe666d5524D7268EBee24f55B089"
            }
        },
        "confirmations": 64,
        "poll_interval": 5,
    },
    "base": {
        "mainnet": {
            "chain_id": 8453,
            "rpc_urls": [
                "https://mainnet.base.org",
                "https://base.llamarpc.com",
                "https://rpc.ankr.com/base"
            ],
            "tokens": {
                "USDC": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
            }
        },
        "testnet": {
            "chain_id": 84532,
            "rpc_urls": [
                "https://sepolia.base.org",
                "https://base-sepolia.drpc.org"
            ],
            "tokens": {
                "USDC": "0x036CbD53842c5426634e7929541eC2318f3dCF7e"
            }
        },
        "confirmations": 12,
        "poll_interval": 5,
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
        self._pending_payments: Dict[str, PaymentInfo] = {}
        self._last_watch_refresh = 0
        self._watch_refresh_interval_seconds = 60
        self._warned_no_wallets = False

    def get_db(self) -> Session:
        """Get database session."""
        return SessionLocal()

    async def _refresh_watched_addresses(self):
        """Load active merchant wallets for this chain from DB."""
        db = self.get_db()
        try:
            wallets = db.query(MerchantWallet).filter(
                MerchantWallet.chain == self.config.chain,
                MerchantWallet.is_active.is_(True),
                MerchantWallet.wallet_address.isnot(None),
                MerchantWallet.wallet_address != ""
            ).all()

            self._watched_addresses = {w.wallet_address.lower() for w in wallets}
            self._last_watch_refresh = datetime.now(timezone.utc).timestamp()

            if self._watched_addresses:
                self._warned_no_wallets = False
                logger.info(
                    f"👥 [{self.config.chain}] Watching {len(self._watched_addresses)} merchant wallet(s)"
                )
            elif not self._warned_no_wallets:
                self._warned_no_wallets = True
                logger.warning(
                    f"⚠️ [{self.config.chain}] No active merchant wallets found. "
                    "Listener will not scan until wallets are added."
                )
        finally:
            db.close()
        
    @property
    def w3(self):
        """Lazy load web3 instance"""
        if self._web3 is None:
            try:
                from web3 import Web3
                from web3.middleware import ExtraDataToPOAMiddleware
                
                self._web3 = Web3(Web3.HTTPProvider(self.config.rpc_url))
                
                # Add PoA middleware for Polygon/Base
                if self.config.chain in ["polygon", "base"]:
                    self._web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
                    
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

        # Load merchant wallets before polling
        try:
            await asyncio.wait_for(self._refresh_watched_addresses(), timeout=10)
        except asyncio.TimeoutError:
            logger.error(f"Timeout loading merchant wallets for {self.config.chain}")
            self.is_running = False
            return
        except Exception as e:
            logger.error(f"Error loading merchant wallets: {e}")
            self.is_running = False
            return
        
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
                now = datetime.now(timezone.utc).timestamp()
                if now - self._last_watch_refresh >= self._watch_refresh_interval_seconds:
                    await self._refresh_watched_addresses()

                # Explicitly skip chain-wide scanning when no merchant wallets are configured
                if not self._watched_addresses:
                    await asyncio.sleep(self.config.poll_interval_seconds)
                    continue

                current_block = self.w3.eth.block_number

                # Re-check confirmations for already detected transfers.
                await self._process_pending_confirmations(current_block)
                
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

    async def _process_pending_confirmations(self, current_block: int):
        """Promote pending transfers to confirmed once threshold is reached."""
        if not self._pending_payments:
            return

        for tx_hash, payment in list(self._pending_payments.items()):
            confirmations = current_block - payment.block_number
            payment.confirmations = confirmations

            if confirmations >= self.config.confirmations_required:
                logger.info(
                    f"✅ {self.config.chain.upper()} confirmed: {payment.amount} {payment.token_symbol} "
                    f"to {payment.to_address[:10]}... (tx: {tx_hash[:12]}..., conf: {confirmations})"
                )
                await self._notify_payment(payment)
                self._pending_payments.pop(tx_hash, None)
                
    async def _scan_blocks(self, from_block: int, to_block: int):
        """Scan block range for token transfers"""
        try:
            # Web3 v7 enforces checksum format for contract addresses in get_logs filters.
            token_addresses = [
                self.w3.to_checksum_address(addr)
                for addr in self.tokens.keys()
            ]
            
            if not token_addresses:
                logger.debug(f"No token addresses configured for {self.config.chain}")
                return

            if not self._watched_addresses:
                logger.debug(f"No watched addresses for {self.config.chain}")
                return

            # Encode watched destination addresses for indexed `to` topic filtering
            to_topics = ["0x" + address[2:].rjust(64, "0") for address in self._watched_addresses]
            
            logger.debug(f"Scanning {self.config.chain} blocks {from_block}-{to_block} for transfers to {len(self._watched_addresses)} wallets")
                
            # Build filter for Transfer events
            filter_params = {
                "fromBlock": from_block,
                "toBlock": to_block,
                # Limit to our tracked token contracts and merchant destination addresses only
                "address": token_addresses,
                "topics": [ERC20_TRANSFER_TOPIC, None, to_topics]
            }
            
            # Get logs
            logs = self.w3.eth.get_logs(filter_params)
            
            if logs:
                logger.info(f"Found {len(logs)} matching transfer(s) in blocks {from_block}-{to_block}")
            
            for log in logs:
                await self._process_transfer_log(log, to_block)
                
        except Exception as e:
            logger.error(f"Error scanning blocks {from_block}-{to_block}: {e}", exc_info=True)
            raise
            
    async def _process_transfer_log(self, log: Dict[str, Any], current_block: int):
        """Process a single Transfer event log"""
        try:
            # Get token address
            token_address = log["address"].lower()
            
            # Check if this is a token we're tracking
            token = self.get_token_by_address(token_address)
            if not token:
                logger.debug(f"Unknown token address in log: {token_address}")
                return
                
            # Decode topics
            topics = log.get("topics", [])
            if len(topics) < 3:
                logger.debug(f"Log missing required topics: {len(topics)}")
                return
            
            # Handle both bytes and hex string topics
            def get_topic_addr(topic) -> str:
                """Extract address from topic, handling both bytes and str"""
                if isinstance(topic, bytes):
                    return "0x" + topic.hex()[-40:]
                elif isinstance(topic, str):
                    return "0x" + topic[-40:]
                else:
                    return "0x" + str(topic)[-40:]
                
            # Extract from and to addresses (remove padding)
            from_address = get_topic_addr(topics[1])
            to_address = get_topic_addr(topics[2])
            
            logger.debug(f"Transfer log: {from_address[:10]}...  -> {to_address[:10]}... token={token.symbol}")
            
            # Check if to_address is one we're watching
            # If no addresses are being watched, process all transfers
            if self._watched_addresses and to_address.lower() not in self._watched_addresses:
                logger.debug(f"To address {to_address} not in watched addresses")
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
                timestamp=datetime.now(timezone.utc)
            )
            
            logger.info(
                f"💎 {self.config.chain.upper()} transfer: "
                f"{amount} {token.symbol} to {to_address[:10]}... "
                f"(block: {block_number}, confirmations: {confirmations})"
            )
            
            # Enough confirmations → mark PAID immediately
            if confirmations >= self.config.confirmations_required:
                await self._notify_payment(payment)
            else:
                # First detection → mark session PENDING (0-conf) for fast UI
                await _mark_session_pending(payment)
                if tx_hash:
                    self._pending_payments[tx_hash] = payment
                logger.info(f"Waiting for confirmations: {confirmations}/{self.config.confirmations_required}")
                
        except Exception as e:
            logger.error(f"Error processing transfer log: {e}", exc_info=True)
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            
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
    
    # Pick mainnet or testnet based on settings
    net = "mainnet" if settings.USE_MAINNET else "testnet"
    net_config = chain_defaults.get(net, {})
    
    # Determine RPC URL
    rpc_url = config.get("rpc_url")
    if not rpc_url:
        env_var = f"{chain.upper()}_RPC_URL"
        rpc_url = getattr(settings, env_var, None) or net_config.get("rpc_urls", [""])[0]
    
    env_confirmations = getattr(settings, f"{chain.upper()}_CONFIRMATIONS", None)

    blockchain_config = BlockchainConfig(
        chain=chain,
        rpc_url=rpc_url,
        chain_id=net_config.get("chain_id"),
        confirmations_required=config.get(
            "confirmations",
            env_confirmations if env_confirmations is not None else chain_defaults.get("confirmations", 12)
        ),
        poll_interval_seconds=config.get("poll_interval", chain_defaults.get("poll_interval", 10)),
        is_active=True
    )
    
    # Configure tokens - prefer settings values over hardcoded defaults
    tokens = []
    token_addresses = config.get("tokens", net_config.get("tokens", {}))
    
    # Override with .env settings if available
    chain_upper = chain.upper()
    for symbol in list(token_addresses.keys()):
        env_attr = f"{chain_upper}_{symbol}_ADDRESS"
        env_val = getattr(settings, env_attr, None)
        if env_val:
            token_addresses[symbol] = env_val
    
    for symbol, address in token_addresses.items():
        tokens.append(TokenConfig(
            symbol=symbol,
            chain=chain,
            contract_address=address,
            decimals=6,  # Most stablecoins use 6 decimals
            is_active=True
        ))
    
    logger.info(f"Created {chain} listener ({net}) - RPC: {rpc_url}")
    return EVMListener(blockchain_config, tokens)


# Run listener as standalone script
if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    # Determine which chains to listen on
    chains = sys.argv[1:] if len(sys.argv) > 1 else ["ethereum", "polygon", "base"]

    async def run_listeners():
        listeners = []
        for chain in chains:
            try:
                listener = create_evm_listener(chain)
                listener.set_payment_callback(process_evm_payment)
                listeners.append(listener)
                logger.info(f"Created listener for {chain}")
            except Exception as e:
                logger.error(f"Failed to create listener for {chain}: {e}")

        if not listeners:
            logger.error("No listeners created, exiting")
            return

        tasks = [asyncio.create_task(l.start()) for l in listeners]
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            pass
        finally:
            for l in listeners:
                await l.stop()

    try:
        asyncio.run(run_listeners())
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down...")
