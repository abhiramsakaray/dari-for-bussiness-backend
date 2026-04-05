"""
Solana Subscription Relayer

Manages subscription payment execution on Solana using the Anchor
dari_subscriptions program. Mirrors the EVM GaslessRelayer pattern.

Responsibilities:
  - Build, sign, and submit transactions to the Anchor program
  - Derive PDAs for config and subscription accounts
  - Track all transactions in the RelayerTransaction table
  - Return uniform result dicts: {tx_hash, status, gas_used, block_number}
"""

import asyncio
import hashlib
import logging
import struct
import time
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any, List

from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.system_program import ID as SYSTEM_PROGRAM_ID
from solders.instruction import Instruction, AccountMeta
from solders.transaction import Transaction
from solders.message import Message
from solders.hash import Hash as Blockhash
from solana.rpc.api import Client as SolanaClient
from solana.rpc.commitment import Confirmed

from app.core.config import settings
from app.models.models import RelayerTransaction, RelayerTxStatus

logger = logging.getLogger(__name__)

# SPL Token program ID
TOKEN_PROGRAM_ID = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")

# Anchor instruction discriminators (first 8 bytes of SHA-256 hash)
def _anchor_discriminator(name: str) -> bytes:
    """Compute Anchor instruction discriminator: sha256('global:<name>')[:8]"""
    return hashlib.sha256(f"global:{name}".encode()).digest()[:8]

DISC_INITIALIZE = _anchor_discriminator("initialize")
DISC_CREATE_SUBSCRIPTION = _anchor_discriminator("create_subscription")
DISC_EXECUTE_PAYMENT = _anchor_discriminator("execute_payment")
DISC_CANCEL_SUBSCRIPTION = _anchor_discriminator("cancel_subscription")
DISC_UPDATE_SUBSCRIPTION = _anchor_discriminator("update_subscription")


class SolanaRelayer:
    """
    Subscription relayer for Solana.

    Uses solders + solana-py to build transactions targeting the Anchor
    dari_subscriptions program.
    """

    def __init__(self):
        self._keypair: Optional[Keypair] = None
        self._client: Optional[SolanaClient] = None
        self._program_id: Optional[Pubkey] = None

        # Initialize from settings
        pk_hex = getattr(settings, "SOLANA_RELAYER_PRIVATE_KEY", "")
        if pk_hex:
            try:
                key_bytes = bytes.fromhex(pk_hex)
                self._keypair = Keypair.from_bytes(key_bytes)
                logger.info(f"✅ Solana relayer initialized: {self._keypair.pubkey()}")
            except Exception as e:
                logger.error(f"❌ Failed to initialize Solana relayer key: {e}")
        else:
            logger.warning("⚠️  SOLANA_RELAYER_PRIVATE_KEY not set — Solana relayer disabled")

        program_id_str = getattr(settings, "SUBSCRIPTION_PROGRAM_SOLANA", "")
        if program_id_str:
            try:
                self._program_id = Pubkey.from_string(program_id_str)
            except Exception as e:
                logger.error(f"❌ Invalid SUBSCRIPTION_PROGRAM_SOLANA: {e}")

    @property
    def address(self) -> Optional[str]:
        """Get relayer wallet address"""
        return str(self._keypair.pubkey()) if self._keypair else None

    def _get_client(self) -> SolanaClient:
        """Get or create Solana RPC client"""
        if self._client is not None:
            return self._client

        rpc_url = getattr(settings, "SOLANA_RPC_URL", "")
        if not rpc_url:
            raise ValueError("SOLANA_RPC_URL not configured")

        self._client = SolanaClient(rpc_url)
        return self._client

    def _get_config_pda(self) -> tuple:
        """Derive config PDA"""
        return Pubkey.find_program_address([b"config"], self._program_id)

    def _get_subscription_pda(self, subscriber: Pubkey, subscription_id: int) -> tuple:
        """Derive subscription PDA"""
        return Pubkey.find_program_address(
            [b"subscription", bytes(subscriber), struct.pack("<Q", subscription_id)],
            self._program_id,
        )

    async def _send_transaction(
        self,
        function_name: str,
        instruction: Instruction,
        db=None,
        subscription_id=None,
    ) -> Dict[str, Any]:
        """
        Build, sign, send a transaction and wait for confirmation.

        Returns:
            Dict matching the EVM relayer shape.
        """
        if not self._keypair:
            raise RuntimeError("Solana relayer not initialized — SOLANA_RELAYER_PRIVATE_KEY not set")

        client = self._get_client()

        # Create relayer transaction record
        relayer_tx = None
        if db:
            relayer_tx = RelayerTransaction(
                chain="solana",
                function_name=function_name,
                relayer_address=str(self._keypair.pubkey()),
                nonce=0,
                status=RelayerTxStatus.PENDING,
            )
            if subscription_id:
                relayer_tx.subscription_id = subscription_id
            db.add(relayer_tx)
            db.flush()

        try:
            # Get recent blockhash
            blockhash_resp = await asyncio.to_thread(
                client.get_latest_blockhash, Confirmed
            )
            recent_blockhash = blockhash_resp.value.blockhash

            # Build and sign transaction
            msg = Message.new_with_blockhash(
                [instruction],
                self._keypair.pubkey(),
                recent_blockhash,
            )
            tx = Transaction.new_unsigned(msg)
            tx.sign([self._keypair], recent_blockhash)

            # Send
            send_resp = await asyncio.to_thread(
                client.send_transaction, tx
            )
            tx_sig = str(send_resp.value)

            logger.info(f"[solana] 📤 Tx sent: {function_name} | sig={tx_sig[:16]}...")

            if relayer_tx:
                relayer_tx.tx_hash = tx_sig

            # Confirm
            confirm_resp = await asyncio.to_thread(
                client.confirm_transaction, send_resp.value, Confirmed
            )

            # Get transaction details for compute units
            tx_detail = await asyncio.to_thread(
                client.get_transaction, send_resp.value, "json"
            )

            compute_units = 0
            slot = None
            is_success = True

            if tx_detail and tx_detail.value:
                tx_meta = tx_detail.value.transaction.meta
                if tx_meta:
                    compute_units = getattr(tx_meta, "compute_units_consumed", 0) or 0
                    if tx_meta.err is not None:
                        is_success = False
                slot = tx_detail.value.slot

            if relayer_tx:
                relayer_tx.gas_used = compute_units
                relayer_tx.confirmed_at = datetime.utcnow()
                relayer_tx.status = (
                    RelayerTxStatus.CONFIRMED if is_success else RelayerTxStatus.REVERTED
                )
                if not is_success:
                    relayer_tx.error_message = "Transaction failed"

            if db:
                db.commit()

            status_str = "confirmed" if is_success else "reverted"

            if is_success:
                logger.info(f"[solana] ✅ Tx confirmed: {function_name} | CU={compute_units}")
            else:
                logger.error(f"[solana] ❌ Tx failed: {function_name}")

            return {
                "tx_hash": tx_sig,
                "status": status_str,
                "gas_used": compute_units,
                "gas_cost_native": "0",  # Solana fees are fixed per signature
                "block_number": slot,
            }

        except Exception as e:
            logger.error(f"[solana] ❌ Tx failed: {function_name} | error={e}")
            if relayer_tx:
                relayer_tx.status = RelayerTxStatus.FAILED
                relayer_tx.error_message = str(e)[:500]
                if db:
                    db.commit()
            raise

    # ============= PUBLIC METHODS =============

    async def create_subscription_onchain(
        self,
        subscriber: str,
        merchant: str,
        mint: str,
        subscriber_token_account: str,
        amount: int,
        interval: int,
        start_time: int,
        subscription_id_num: int,
        db=None,
        subscription_id=None,
    ) -> Dict[str, Any]:
        """
        Create a subscription on Solana.

        Args:
            subscriber: Subscriber pubkey (base58)
            merchant: Merchant pubkey (base58)
            mint: SPL Token mint pubkey (base58)
            subscriber_token_account: Subscriber's ATA pubkey (base58)
            amount: Token amount in raw decimals
            interval: Billing interval in seconds
            start_time: First payment timestamp
            subscription_id_num: Sequential subscription ID
        """
        subscriber_pk = Pubkey.from_string(subscriber)
        merchant_pk = Pubkey.from_string(merchant)
        mint_pk = Pubkey.from_string(mint)
        sub_ata = Pubkey.from_string(subscriber_token_account)

        config_pda, _ = self._get_config_pda()
        sub_pda, _ = self._get_subscription_pda(subscriber_pk, subscription_id_num)

        # Use on-chain time for safety
        client = self._get_client()
        try:
            slot_resp = await asyncio.to_thread(client.get_slot)
            block_time_resp = await asyncio.to_thread(
                client.get_block_time, slot_resp.value
            )
            onchain_ts = block_time_resp.value or int(time.time())
        except Exception:
            onchain_ts = int(time.time())

        safe_start_time = onchain_ts + 5

        # Encode instruction data: discriminator + subscription_id(u64) + amount(u64) + interval(i64) + start_time(i64)
        data = (
            DISC_CREATE_SUBSCRIPTION
            + struct.pack("<Q", subscription_id_num)
            + struct.pack("<Q", amount)
            + struct.pack("<q", interval)
            + struct.pack("<q", safe_start_time)
        )

        accounts = [
            AccountMeta(config_pda, is_signer=False, is_writable=True),
            AccountMeta(sub_pda, is_signer=False, is_writable=True),
            AccountMeta(self._keypair.pubkey(), is_signer=True, is_writable=True),
            AccountMeta(subscriber_pk, is_signer=False, is_writable=False),
            AccountMeta(merchant_pk, is_signer=False, is_writable=False),
            AccountMeta(mint_pk, is_signer=False, is_writable=False),
            AccountMeta(sub_ata, is_signer=False, is_writable=False),
            AccountMeta(TOKEN_PROGRAM_ID, is_signer=False, is_writable=False),
            AccountMeta(SYSTEM_PROGRAM_ID, is_signer=False, is_writable=False),
        ]

        ix = Instruction(self._program_id, data, accounts)

        result = await self._send_transaction(
            "create_subscription", ix, db=db, subscription_id=subscription_id,
        )
        result["start_time"] = safe_start_time
        return result

    async def execute_payment(
        self,
        onchain_subscription_id: int,
        subscriber: str,
        mint: str,
        subscriber_token_account: str,
        merchant_token_account: str,
        db=None,
        subscription_id=None,
    ) -> Dict[str, Any]:
        """
        Execute a due payment on Solana.

        Args:
            onchain_subscription_id: Subscription ID number
            subscriber: Subscriber pubkey (base58)
            mint: SPL Token mint (base58)
            subscriber_token_account: Subscriber's ATA (base58)
            merchant_token_account: Merchant's ATA (base58)
        """
        subscriber_pk = Pubkey.from_string(subscriber)

        config_pda, _ = self._get_config_pda()
        sub_pda, _ = self._get_subscription_pda(subscriber_pk, onchain_subscription_id)

        data = DISC_EXECUTE_PAYMENT  # No additional args needed

        accounts = [
            AccountMeta(config_pda, is_signer=False, is_writable=False),
            AccountMeta(sub_pda, is_signer=False, is_writable=True),
            AccountMeta(self._keypair.pubkey(), is_signer=True, is_writable=False),
            AccountMeta(Pubkey.from_string(subscriber_token_account), is_signer=False, is_writable=True),
            AccountMeta(Pubkey.from_string(merchant_token_account), is_signer=False, is_writable=True),
            AccountMeta(TOKEN_PROGRAM_ID, is_signer=False, is_writable=False),
        ]

        ix = Instruction(self._program_id, data, accounts)
        return await self._send_transaction(
            "execute_payment", ix, db=db, subscription_id=subscription_id,
        )

    async def cancel_subscription_onchain(
        self,
        onchain_subscription_id: int,
        subscriber: str,
        db=None,
        subscription_id=None,
    ) -> Dict[str, Any]:
        """Cancel a subscription on Solana."""
        subscriber_pk = Pubkey.from_string(subscriber)

        config_pda, _ = self._get_config_pda()
        sub_pda, _ = self._get_subscription_pda(subscriber_pk, onchain_subscription_id)

        data = DISC_CANCEL_SUBSCRIPTION

        accounts = [
            AccountMeta(config_pda, is_signer=False, is_writable=False),
            AccountMeta(sub_pda, is_signer=False, is_writable=True),
            AccountMeta(self._keypair.pubkey(), is_signer=True, is_writable=False),
        ]

        ix = Instruction(self._program_id, data, accounts)
        return await self._send_transaction(
            "cancel_subscription", ix, db=db, subscription_id=subscription_id,
        )

    async def update_subscription_onchain(
        self,
        onchain_subscription_id: int,
        subscriber: str,
        new_amount: int,
        new_interval: int,
        db=None,
        subscription_id=None,
    ) -> Dict[str, Any]:
        """Update a subscription on Solana (amount can only decrease)."""
        subscriber_pk = Pubkey.from_string(subscriber)

        config_pda, _ = self._get_config_pda()
        sub_pda, _ = self._get_subscription_pda(subscriber_pk, onchain_subscription_id)

        data = (
            DISC_UPDATE_SUBSCRIPTION
            + struct.pack("<Q", new_amount)
            + struct.pack("<q", new_interval)
        )

        accounts = [
            AccountMeta(config_pda, is_signer=False, is_writable=False),
            AccountMeta(sub_pda, is_signer=False, is_writable=True),
            AccountMeta(self._keypair.pubkey(), is_signer=True, is_writable=False),
        ]

        ix = Instruction(self._program_id, data, accounts)
        return await self._send_transaction(
            "update_subscription", ix, db=db, subscription_id=subscription_id,
        )

    # ============= READ-ONLY METHODS =============

    def get_relayer_balance(self) -> Dict[str, str]:
        """Get relayer's SOL balance"""
        if not self._keypair:
            return {"balance": "0", "address": ""}

        client = self._get_client()
        balance_resp = client.get_balance(self._keypair.pubkey())
        balance_lamports = balance_resp.value
        balance_sol = Decimal(str(balance_lamports)) / Decimal("1e9")

        return {
            "chain": "solana",
            "address": str(self._keypair.pubkey()),
            "balance_native": str(balance_sol),
        }


# Singleton instance
solana_relayer = SolanaRelayer()
