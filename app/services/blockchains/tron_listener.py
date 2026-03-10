"""
Tron Blockchain Listener

Monitors Tron network for TRC20 token transfers.
Filters by merchant wallet addresses loaded from DB.
Two-phase flow: PENDING on first detect → PAID after confirmations.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Set
from decimal import Decimal
import httpx
from sqlalchemy.orm import Session

from .base import BlockchainListener, BlockchainConfig, TokenConfig, PaymentInfo, ListenerStatus
from app.core.config import settings
from app.core.database import SessionLocal
from app.models import MerchantWallet
from app.models import PaymentSession, PaymentStatus
from app.services.webhook_service import send_webhook

logger = logging.getLogger(__name__)

# Tron configuration
TRON_CONFIGS = {
    "mainnet": {
        "api_url": "https://api.trongrid.io",
        "tokens": {
            "USDT": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
            "USDC": "TEkxiTehnzSmSe2XqrBj4w32RUN966rdz8"
        }
    },
    "testnet": {
        "api_url": "https://nile.trongrid.io",
        "tokens": {
            "USDT": "TXLAQ63Xg1NAzckPwKHvzw7CSEmLMEqcdj",
            "USDC": "TSdZwNqpHofzP6BsBKGQUWdBeJphLmF6id"
        }
    }
}


def _match_session(candidates, payment: PaymentInfo):
    """Find the best matching PaymentSession for a detected Tron transfer."""
    paid_amount = Decimal(str(payment.amount))
    to_addr = payment.to_address

    wallet_matches = []
    for session in candidates:
        session_addr = session.merchant_wallet or session.deposit_address or ""
        if not session_addr or session_addr != to_addr:
            continue
        wallet_matches.append(session)

    if not wallet_matches:
        return None

    # Try amount match (±2 % tolerance)
    for session in wallet_matches:
        expected = Decimal(str(session.amount_token or session.amount_usdc or "0"))
        if expected == 0:
            continue
        diff_pct = abs(expected - paid_amount) / expected * 100 if expected else 100
        if diff_pct <= Decimal("2"):
            return session

    # Fallback: single session for this wallet
    if len(wallet_matches) == 1:
        logger.info(f"Fuzzy match: single open session {wallet_matches[0].id} for wallet {to_addr[:10]}...")
        return wallet_matches[0]

    return None


async def _mark_session_pending(payment: PaymentInfo):
    """Mark a matching session as PENDING on first detection."""
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
                f"No open session to mark PENDING for tron tx {payment.tx_hash} "
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
            f"(tron tx {payment.tx_hash[:16]}..., {payment.confirmations} conf)"
        )
    except Exception as e:
        logger.error(f"Error marking session PENDING: {e}")
        db.rollback()
    finally:
        db.close()


async def process_tron_payment(payment: PaymentInfo):
    """Match confirmed Tron transfer to an open session and mark it PAID."""
    db = SessionLocal()
    try:
        candidates = db.query(PaymentSession).filter(
            PaymentSession.status.in_([PaymentStatus.CREATED, PaymentStatus.PENDING]),
            PaymentSession.chain == payment.chain,
            PaymentSession.token == payment.token_symbol,
        ).order_by(PaymentSession.created_at.desc()).all()

        matched_session = _match_session(candidates, payment)

        if not matched_session:
            logger.info(
                f"No matching open session for confirmed tron tx {payment.tx_hash} "
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
            f"from tron tx {payment.tx_hash}"
        )

        # Credit merchant balance
        try:
            from app.services.payment_utils import credit_merchant_balance
            payment_token = matched_session.token or "USDC"
            credit_amount = matched_session.amount_token or matched_session.amount_usdc or "0"
            credit_merchant_balance(db, matched_session.merchant_id, payment_token, credit_amount)
        except Exception as be:
            logger.error(f"Error crediting balance for session {matched_session.id}: {be}")

        await send_webhook(matched_session, db)

    except Exception as e:
        logger.error(f"Error processing Tron payment callback: {e}")
        db.rollback()
    finally:
        db.close()


class TronListener(BlockchainListener):
    """
    Tron network payment listener.

    Monitors for TRC20 transfers using TronGrid API.
    Filters by merchant wallet addresses loaded from DB.
    """

    def __init__(self, config: BlockchainConfig, tokens: List[TokenConfig]):
        super().__init__(config, tokens)
        self._api_key = None
        self._last_timestamp = 0
        self._watched_addresses: Set[str] = set()
        self._http_client = None
        self._pending_payments: Dict[str, PaymentInfo] = {}
        self._last_watch_refresh = 0
        self._watch_refresh_interval_seconds = 60
        self._warned_no_wallets = False

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

    def get_db(self) -> Session:
        return SessionLocal()

    async def _refresh_watched_addresses(self):
        """Load active merchant wallets for tron from DB."""
        db = self.get_db()
        try:
            wallets = db.query(MerchantWallet).filter(
                MerchantWallet.chain == self.config.chain,
                MerchantWallet.is_active.is_(True),
                MerchantWallet.wallet_address.isnot(None),
                MerchantWallet.wallet_address != ""
            ).all()

            self._watched_addresses = {w.wallet_address for w in wallets}
            self._last_watch_refresh = datetime.now(timezone.utc).timestamp()

            if self._watched_addresses:
                self._warned_no_wallets = False
                logger.info(f"👥 [tron] Watching {len(self._watched_addresses)} merchant wallet(s)")
            elif not self._warned_no_wallets:
                self._warned_no_wallets = True
                logger.warning("⚠️ [tron] No active merchant wallets found.")
        finally:
            db.close()

    def add_watched_address(self, address: str):
        self._watched_addresses.add(address)

    def remove_watched_address(self, address: str):
        self._watched_addresses.discard(address)

    async def start(self):
        """Start listening for Tron payments"""
        self.is_running = True
        self.status = ListenerStatus.STARTING
        logger.info(f"🚀 Starting Tron listener on {self.config.rpc_url}")

        await self._refresh_watched_addresses()
        self._last_timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)

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
                # Refresh watched addresses periodically
                now = datetime.now(timezone.utc).timestamp()
                if now - self._last_watch_refresh >= self._watch_refresh_interval_seconds:
                    await self._refresh_watched_addresses()

                if not self._watched_addresses:
                    await asyncio.sleep(self.config.poll_interval_seconds)
                    continue

                # Check pending confirmations
                await self._process_pending_confirmations()

                # Poll transfers for each watched address
                for address in list(self._watched_addresses):
                    await self._check_address_transfers(address)

                await asyncio.sleep(self.config.poll_interval_seconds)

            except Exception as e:
                logger.error(f"Error polling for transfers: {e}")
                raise

    async def _process_pending_confirmations(self):
        """Promote pending transfers to confirmed once threshold is reached."""
        if not self._pending_payments:
            return

        try:
            current_block = await self.get_current_block()
            if current_block == 0:
                return

            for tx_hash, payment in list(self._pending_payments.items()):
                # For Tron, estimate confirmations from block number
                if payment.block_number > 0:
                    confirmations = current_block - payment.block_number
                else:
                    confirmations = payment.confirmations + 1
                payment.confirmations = confirmations

                if confirmations >= self.config.confirmations_required:
                    logger.info(
                        f"✅ TRON confirmed: {payment.amount} {payment.token_symbol} "
                        f"to {payment.to_address[:10]}... (tx: {tx_hash[:12]}..., conf: {confirmations})"
                    )
                    await self._notify_payment(payment)
                    self._pending_payments.pop(tx_hash, None)
        except Exception as e:
            logger.error(f"Error processing pending confirmations: {e}")
                
    async def _check_address_transfers(self, address: str):
        """Check TRC20 transfers to a specific address"""
        try:
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

            if transfers:
                latest = max(t.get("block_timestamp", 0) for t in transfers)
                self._last_timestamp = max(self._last_timestamp, latest + 1)

        except Exception as e:
            logger.error(f"Error checking transfers for {address}: {e}")

    async def _process_transfer(self, transfer: Dict[str, Any]):
        """Process a TRC20 transfer with PENDING → PAID flow."""
        try:
            token_info = transfer.get("token_info", {})
            token_address = token_info.get("address", "")

            token = self.get_token_by_address(token_address)
            if not token:
                return

            tx_hash = transfer.get("transaction_id")
            from_address = transfer.get("from")
            to_address = transfer.get("to")
            value = transfer.get("value", "0")
            block_timestamp = transfer.get("block_timestamp", 0)

            # Skip if already tracked
            if tx_hash in self._pending_payments:
                return

            decimals = int(token_info.get("decimals", token.decimals))
            amount_raw = int(value)
            amount = str(Decimal(amount_raw) / Decimal(10 ** decimals))

            # Get block number for confirmation tracking
            block_number = 0
            try:
                tx_info = await self.get_transaction(tx_hash)
                if tx_info:
                    block_number = tx_info.get("blockNumber", 0)
            except Exception:
                pass

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
                confirmations=0,
                timestamp=datetime.fromtimestamp(block_timestamp / 1000, tz=timezone.utc) if block_timestamp else datetime.now(timezone.utc)
            )

            logger.info(
                f"🔷 TRON transfer: {amount} {token.symbol} "
                f"to {to_address[:10]}..."
            )

            # Check if already confirmed
            current_block = await self.get_current_block()
            if block_number > 0 and current_block > 0:
                confirmations = current_block - block_number
                payment.confirmations = confirmations
                if confirmations >= self.config.confirmations_required:
                    await self._notify_payment(payment)
                    return

            # Mark session PENDING and track for confirmation
            await _mark_session_pending(payment)
            if tx_hash:
                self._pending_payments[tx_hash] = payment
            logger.info(f"Waiting for confirmations: {payment.confirmations}/{self.config.confirmations_required}")

        except Exception as e:
            logger.error(f"Error processing transfer: {e}")
            
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
                items = data.get("data", [])
                return items[0] if items else None
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
            response = await self.client.get(f"/v1/transactions/{tx_hash}/events")
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

                token = self.get_token_by_address(contract_address)
                if not token or token.symbol != expected_token:
                    continue

                if to_address != expected_to:
                    continue

                amount_raw = int(value)
                amount = Decimal(amount_raw) / Decimal(10 ** token.decimals)
                expected = Decimal(expected_amount)

                diff_pct = abs(amount - expected) / expected * 100 if expected else 100
                if diff_pct <= Decimal("2"):
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
    """Create Tron listener with configuration."""
    config = config or {}

    # Determine network from settings
    net = "mainnet" if settings.USE_MAINNET else "testnet"
    network_config = TRON_CONFIGS.get(net, TRON_CONFIGS["testnet"])

    # Use settings-resolved URL, fall back to hardcoded config
    api_url = config.get("api_url") or settings.TRON_API_URL or network_config["api_url"]

    blockchain_config = BlockchainConfig(
        chain="tron",
        rpc_url=api_url,
        confirmations_required=config.get("confirmations", settings.TRON_CONFIRMATIONS),
        poll_interval_seconds=config.get("poll_interval", 10),
        is_active=True
    )

    # Configure tokens - prefer settings values
    tokens = []
    token_addresses = dict(network_config.get("tokens", {}))

    # Override with settings-resolved addresses
    if settings.TRON_USDT_ADDRESS:
        token_addresses["USDT"] = settings.TRON_USDT_ADDRESS
    if settings.TRON_USDC_ADDRESS:
        token_addresses["USDC"] = settings.TRON_USDC_ADDRESS

    for symbol, address in token_addresses.items():
        tokens.append(TokenConfig(
            symbol=symbol,
            chain="tron",
            contract_address=address,
            decimals=6,
            is_active=True
        ))

    listener = TronListener(blockchain_config, tokens)

    api_key = config.get("api_key") or settings.TRON_API_KEY
    if api_key and api_key != "your-trongrid-api-key-here":
        listener.set_api_key(api_key)

    logger.info(f"Created tron listener ({net}) - API: {api_url}")
    return listener


# Run listener as standalone script
if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    async def run():
        listener = create_tron_listener()
        listener.set_payment_callback(process_tron_payment)
        logger.info("Created Tron listener")
        try:
            await listener.start()
        except asyncio.CancelledError:
            pass
        finally:
            await listener.stop()

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down...")
