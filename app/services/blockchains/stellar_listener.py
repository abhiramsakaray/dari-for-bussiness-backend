"""
Stellar Blockchain Listener

Monitors Stellar network for USDC/XLM payments.
Filters by merchant wallet addresses loaded from DB.
Two-phase flow: PENDING on detect → PAID (instant finality).
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Set
from decimal import Decimal
from sqlalchemy.orm import Session

from stellar_sdk import Server, Asset, Keypair
from stellar_sdk.exceptions import BaseHorizonError, Ed25519PublicKeyInvalidError

from .base import BlockchainListener, BlockchainConfig, TokenConfig, PaymentInfo, ListenerStatus
from app.core.config import settings
from app.core.database import SessionLocal
from app.models import MerchantWallet
from app.models import PaymentSession, PaymentStatus
from app.services.webhook_service import send_webhook

logger = logging.getLogger(__name__)


def _match_session(candidates, payment: PaymentInfo):
    """Find the best matching PaymentSession for a detected Stellar transfer."""
    paid_amount = Decimal(str(payment.amount))
    to_addr = payment.to_address  # Stellar addresses are case-sensitive

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


async def process_stellar_payment(payment: PaymentInfo):
    """Match a Stellar transfer to an open session and mark it PAID.

    Stellar has instant finality, so we go directly to PAID.
    """
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
                f"No matching open session for Stellar tx {payment.tx_hash} "
                f"({payment.amount} {payment.token_symbol} to {payment.to_address[:10]}...)"
            )
            return

        matched_session.status = PaymentStatus.PAID
        matched_session.tx_hash = payment.tx_hash
        matched_session.block_number = payment.block_number
        matched_session.confirmations = 1  # instant finality
        matched_session.paid_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(matched_session)

        logger.info(
            f"✅ Marked session {matched_session.id} as PAID "
            f"from stellar tx {payment.tx_hash}"
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
        logger.error(f"Error processing Stellar payment callback: {e}")
        db.rollback()
    finally:
        db.close()


class StellarListener(BlockchainListener):
    """
    Stellar network payment listener.

    Monitors for USDC transfers using Horizon polling API.
    Filters by merchant wallet addresses loaded from DB.
    """

    def __init__(self, config: BlockchainConfig, tokens: List[TokenConfig]):
        super().__init__(config, tokens)
        self.server = Server(horizon_url=config.rpc_url)
        self.cursor = "now"
        self._watched_addresses: Set[str] = set()
        self._seen_tx_hashes: Set[str] = set()
        self._last_watch_refresh = 0
        self._watch_refresh_interval_seconds = 60
        self._warned_no_wallets = False

    def get_db(self) -> Session:
        return SessionLocal()

    async def _refresh_watched_addresses(self):
        """Load active merchant wallets for stellar from DB."""
        db = self.get_db()
        try:
            wallets = db.query(MerchantWallet).filter(
                MerchantWallet.chain == self.config.chain,
                MerchantWallet.is_active.is_(True),
                MerchantWallet.wallet_address.isnot(None),
                MerchantWallet.wallet_address != ""
            ).all()

            valid = set()
            for w in wallets:
                addr = w.wallet_address.strip()
                try:
                    Keypair.from_public_key(addr)
                    valid.add(addr)
                except (Ed25519PublicKeyInvalidError, Exception):
                    logger.warning(f"⚠️ [stellar] Skipping invalid wallet address: {addr[:16]}...")

            self._watched_addresses = valid
            self._last_watch_refresh = datetime.now(timezone.utc).timestamp()

            if self._watched_addresses:
                self._warned_no_wallets = False
                logger.info(f"👥 [stellar] Watching {len(self._watched_addresses)} merchant wallet(s)")
            elif not self._warned_no_wallets:
                self._warned_no_wallets = True
                logger.warning("⚠️ [stellar] No active merchant wallets found.")
        finally:
            db.close()

    async def start(self):
        """Start listening for Stellar payments"""
        self.is_running = True
        self.status = ListenerStatus.STARTING
        logger.info(f"🚀 Starting Stellar listener on {self.config.rpc_url}")

        await self._refresh_watched_addresses()

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
        while self.is_running:
            try:
                # Refresh watched addresses periodically
                now = datetime.now(timezone.utc).timestamp()
                if now - self._last_watch_refresh >= self._watch_refresh_interval_seconds:
                    await self._refresh_watched_addresses()

                if not self._watched_addresses:
                    await asyncio.sleep(self.config.poll_interval_seconds)
                    continue

                # Poll for each watched address
                for address in list(self._watched_addresses):
                    await self._check_address_payments(address)

                await asyncio.sleep(self.config.poll_interval_seconds)

            except BaseHorizonError as e:
                logger.error(f"Horizon API error: {e}")
                raise
            except Exception as e:
                logger.error(f"Error in payment loop: {e}")
                raise

    async def _check_address_payments(self, address: str):
        """Check recent payments to a specific merchant address."""
        try:
            payments_call = self.server.payments().for_account(address).order(
                desc=True
            ).limit(20).call()

            records = payments_call.get("_embedded", {}).get("records", [])

            for op in records:
                await self._process_operation(op)

        except BaseHorizonError as e:
            if "404" in str(e):
                pass  # Account not found / not funded on testnet
            else:
                logger.error(f"Horizon error for {address[:10]}...: {e}")
        except Exception as e:
            logger.error(f"Error checking payments for {address[:10]}...: {e}")

    async def _process_operation(self, operation: Dict[str, Any]):
        """Process a payment operation"""
        op_type = operation.get("type")

        if op_type not in ["payment", "path_payment_strict_receive", "path_payment_strict_send"]:
            return

        destination = operation.get("to") or operation.get("destination")
        amount = operation.get("amount")
        asset_type = operation.get("asset_type")
        asset_code = operation.get("asset_code", "XLM")
        asset_issuer = operation.get("asset_issuer", "")
        from_address = operation.get("from")
        tx_hash = operation.get("transaction_hash", "")
        op_id = operation.get("id", tx_hash)

        if not destination or not amount:
            return

        # Skip already-seen operations
        if op_id in self._seen_tx_hashes:
            return
        self._seen_tx_hashes.add(op_id)

        # Cap memory: keep only last 5000 entries
        if len(self._seen_tx_hashes) > 5000:
            self._seen_tx_hashes = set(list(self._seen_tx_hashes)[-2500:])

        # Only process payments TO our watched addresses
        if destination not in self._watched_addresses:
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

        payment = PaymentInfo(
            tx_hash=tx_hash,
            chain="stellar",
            token_symbol=token_symbol,
            token_address=token_address,
            from_address=from_address,
            to_address=destination,
            amount=amount,
            amount_raw=int(float(amount) * 10**7),
            block_number=0,
            confirmations=1,  # instant finality
            timestamp=datetime.now(timezone.utc)
        )

        logger.info(f"💫 Stellar payment detected: {amount} {token_symbol} to {destination[:8]}...")
        await self._notify_payment(payment)
        
    async def get_current_block(self) -> int:
        """Get current ledger sequence"""
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

            if memo and tx.get("memo") != memo:
                return False

            operations = self.server.operations().for_transaction(tx_hash).call()

            for op in operations.get("_embedded", {}).get("records", []):
                if op.get("type") not in ["payment", "path_payment_strict_receive"]:
                    continue

                destination = op.get("to") or op.get("destination")
                amount = op.get("amount")
                asset_code = op.get("asset_code", "XLM")

                if destination == expected_to:
                    if asset_code == expected_token or expected_token == "XLM":
                        received = Decimal(amount)
                        expected = Decimal(expected_amount)
                        diff_pct = abs(received - expected) / expected * 100 if expected else 100
                        if diff_pct <= Decimal("2"):
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
    """Create Stellar listener with configuration."""
    config = config or {}

    blockchain_config = BlockchainConfig(
        chain="stellar",
        rpc_url=config.get("horizon_url", settings.STELLAR_HORIZON_URL),
        confirmations_required=1,  # Instant finality
        poll_interval_seconds=config.get("poll_interval", 5),
        is_active=True
    )

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


# Run listener as standalone script
if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    async def run():
        listener = create_stellar_listener()
        listener.set_payment_callback(process_stellar_payment)
        logger.info("Created Stellar listener")
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
