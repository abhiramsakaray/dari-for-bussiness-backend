"""
Soroban Subscription Relayer

Manages subscription payment execution on Stellar using Soroban smart
contracts. Mirrors the EVM GaslessRelayer pattern.

Responsibilities:
  - Build, sign, and submit Soroban transactions
  - Track all transactions in the RelayerTransaction table
  - Return uniform result dicts: {tx_hash, status, gas_used, block_number}
"""

import asyncio
import logging
import time
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any

from stellar_sdk import (
    SorobanServer,
    Keypair,
    TransactionBuilder,
    Network,
    scval,
    Address as StellarAddress,
)
from stellar_sdk.soroban_rpc import GetTransactionStatus
from stellar_sdk.exceptions import BaseHorizonError

from app.core.config import settings
from app.models.models import RelayerTransaction, RelayerTxStatus

logger = logging.getLogger(__name__)


class SorobanRelayer:
    """
    Subscription relayer for Stellar/Soroban.

    Uses stellar_sdk to invoke DariSubscriptionsContract functions.
    Follows the same pattern as soroban_escrow.py but tailored for
    recurring subscription pull-payments.
    """

    def __init__(self):
        self._server: Optional[SorobanServer] = None
        self._keypair: Optional[Keypair] = None
        self._contract_id: Optional[str] = None

        # Initialize from settings
        secret_key = getattr(settings, "SOROBAN_RELAYER_SECRET_KEY", "")
        if secret_key:
            try:
                self._keypair = Keypair.from_secret(secret_key)
                logger.info(f"✅ Soroban relayer initialized: {self._keypair.public_key}")
            except Exception as e:
                logger.error(f"❌ Failed to initialize Soroban relayer key: {e}")
        else:
            logger.warning(
                "⚠️  SOROBAN_RELAYER_SECRET_KEY not set — Soroban relayer disabled"
            )

        self._contract_id = getattr(settings, "SUBSCRIPTION_CONTRACT_SOROBAN", "")
        if not self._contract_id:
            logger.warning(
                "⚠️  SUBSCRIPTION_CONTRACT_SOROBAN not set — Soroban relayer disabled"
            )

    @property
    def address(self) -> Optional[str]:
        """Get relayer public key"""
        return self._keypair.public_key if self._keypair else None

    def _get_server(self) -> SorobanServer:
        """Get or create Soroban RPC server"""
        if self._server is not None:
            return self._server

        rpc_url = getattr(settings, "SOROBAN_RPC_URL", "")
        if not rpc_url:
            raise ValueError("SOROBAN_RPC_URL not configured")

        self._server = SorobanServer(rpc_url)
        return self._server

    def _get_network_passphrase(self) -> str:
        """Get the network passphrase based on config"""
        stellar_network = getattr(settings, "STELLAR_NETWORK", "testnet")
        if stellar_network == "public":
            return Network.PUBLIC_NETWORK_PASSPHRASE
        return Network.TESTNET_NETWORK_PASSPHRASE

    async def _invoke_contract(
        self,
        function_name: str,
        args: list,
        db=None,
        subscription_id=None,
    ) -> Dict[str, Any]:
        """
        Build, simulate, sign, submit, and poll a Soroban contract invocation.

        Returns:
            Dict matching the EVM relayer shape.
        """
        if not self._keypair:
            raise RuntimeError(
                "Soroban relayer not initialized — SOROBAN_RELAYER_SECRET_KEY not set"
            )
        if not self._contract_id:
            raise RuntimeError(
                "Soroban relayer not initialized — SUBSCRIPTION_CONTRACT_SOROBAN not set"
            )

        server = self._get_server()
        network_passphrase = self._get_network_passphrase()

        # Create relayer transaction record
        relayer_tx = None
        if db:
            relayer_tx = RelayerTransaction(
                chain="stellar",
                function_name=function_name,
                relayer_address=self._keypair.public_key,
                nonce=0,
                status=RelayerTxStatus.PENDING,
            )
            if subscription_id:
                relayer_tx.subscription_id = subscription_id
            db.add(relayer_tx)
            db.flush()

        try:
            # Load source account for sequence number
            source_account = await asyncio.to_thread(
                server.load_account, self._keypair.public_key
            )

            # Build the transaction
            builder = (
                TransactionBuilder(
                    source_account=source_account,
                    network_passphrase=network_passphrase,
                    base_fee=100,
                )
                .append_invoke_contract_function_op(
                    contract_id=self._contract_id,
                    function_name=function_name,
                    parameters=args,
                )
                .set_timeout(300)
            )
            tx = builder.build()

            # Simulate to get resource requirements
            simulate_resp = await asyncio.to_thread(server.simulate_transaction, tx)

            if simulate_resp.error:
                raise RuntimeError(
                    f"Simulation failed: {simulate_resp.error}"
                )

            # Prepare the transaction with simulation results
            tx = server.prepare_transaction(tx, simulate_resp)

            # Sign
            tx.sign(self._keypair)

            # Submit
            send_resp = await asyncio.to_thread(server.send_transaction, tx)
            tx_hash = send_resp.hash

            logger.info(f"[stellar] 📤 Tx sent: {function_name} | hash={tx_hash[:16]}...")

            if relayer_tx:
                relayer_tx.tx_hash = tx_hash

            # Poll for result
            is_success = False
            ledger_num = None

            for _ in range(30):
                await asyncio.sleep(2)
                get_resp = await asyncio.to_thread(
                    server.get_transaction, tx_hash
                )

                if get_resp.status == GetTransactionStatus.SUCCESS:
                    is_success = True
                    ledger_num = getattr(get_resp, "ledger", None)
                    break
                elif get_resp.status == GetTransactionStatus.FAILED:
                    is_success = False
                    break
                # NOT_FOUND means still pending, keep polling

            if relayer_tx:
                relayer_tx.confirmed_at = datetime.utcnow()
                relayer_tx.status = (
                    RelayerTxStatus.CONFIRMED if is_success else RelayerTxStatus.REVERTED
                )
                if not is_success:
                    relayer_tx.error_message = "Soroban transaction failed"

            if db:
                db.commit()

            status_str = "confirmed" if is_success else "reverted"

            if is_success:
                logger.info(f"[stellar] ✅ Tx confirmed: {function_name} | ledger={ledger_num}")
            else:
                logger.error(f"[stellar] ❌ Tx failed: {function_name}")

            return {
                "tx_hash": tx_hash,
                "status": status_str,
                "gas_used": 0,  # Soroban charges in resource fees, not gas
                "gas_cost_native": "0",
                "block_number": ledger_num,
            }

        except Exception as e:
            logger.error(f"[stellar] ❌ Tx failed: {function_name} | error={e}")
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
        token_address: str,
        amount: int,
        interval: int,
        start_time: int,
        db=None,
        subscription_id=None,
    ) -> Dict[str, Any]:
        """
        Create a subscription on Soroban.

        Args:
            subscriber: Subscriber Stellar address (G...)
            merchant: Merchant Stellar address (G...)
            token_address: Token contract ID
            amount: Token amount in smallest unit (e.g. stroops for USDC)
            interval: Billing interval in seconds
            start_time: First payment timestamp
        """
        # Use ledger timestamp for safety
        server = self._get_server()
        try:
            latest = await asyncio.to_thread(server.get_latest_ledger)
            # Soroban doesn't expose timestamp directly in get_latest_ledger
            # Use current time with small buffer
            onchain_ts = int(time.time())
        except Exception:
            onchain_ts = int(time.time())

        safe_start_time = onchain_ts + 5

        args = [
            scval.to_address(subscriber),
            scval.to_address(merchant),
            scval.to_address(token_address),
            scval.to_int128(amount),
            scval.to_uint64(interval),
            scval.to_uint64(safe_start_time),
        ]

        result = await self._invoke_contract(
            "create_subscription", args, db=db, subscription_id=subscription_id,
        )
        result["start_time"] = safe_start_time
        return result

    async def execute_payment(
        self,
        onchain_subscription_id: int,
        db=None,
        subscription_id=None,
    ) -> Dict[str, Any]:
        """
        Execute a due payment on Soroban.

        Args:
            onchain_subscription_id: Subscription ID in the contract
        """
        args = [scval.to_uint64(onchain_subscription_id)]
        return await self._invoke_contract(
            "execute_payment", args, db=db, subscription_id=subscription_id,
        )

    async def cancel_subscription_onchain(
        self,
        onchain_subscription_id: int,
        db=None,
        subscription_id=None,
    ) -> Dict[str, Any]:
        """Cancel a subscription on Soroban."""
        args = [scval.to_uint64(onchain_subscription_id)]
        return await self._invoke_contract(
            "cancel_subscription", args, db=db, subscription_id=subscription_id,
        )

    async def update_subscription_onchain(
        self,
        onchain_subscription_id: int,
        new_amount: int,
        new_interval: int,
        db=None,
        subscription_id=None,
    ) -> Dict[str, Any]:
        """Update a subscription on Soroban (amount can only decrease)."""
        args = [
            scval.to_uint64(onchain_subscription_id),
            scval.to_int128(new_amount),
            scval.to_uint64(new_interval),
        ]
        return await self._invoke_contract(
            "update_subscription", args, db=db, subscription_id=subscription_id,
        )

    # ============= READ-ONLY METHODS =============

    def get_relayer_balance(self) -> Dict[str, str]:
        """Get relayer's XLM balance"""
        if not self._keypair:
            return {"balance": "0", "address": ""}

        # Use Horizon for balance check (more reliable than Soroban RPC)
        try:
            from stellar_sdk import Server as HorizonServer
            horizon_url = getattr(settings, "STELLAR_HORIZON_URL", "")
            if horizon_url:
                horizon = HorizonServer(horizon_url)
                account = horizon.accounts().account_id(self._keypair.public_key).call()
                for balance in account.get("balances", []):
                    if balance.get("asset_type") == "native":
                        return {
                            "chain": "stellar",
                            "address": self._keypair.public_key,
                            "balance_native": balance.get("balance", "0"),
                        }
        except Exception as e:
            logger.warning(f"Failed to get Soroban relayer balance: {e}")

        return {
            "chain": "stellar",
            "address": self._keypair.public_key,
            "balance_native": "0",
        }


# Singleton instance
soroban_relayer = SorobanRelayer()
