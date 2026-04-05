"""
Tron Subscription Relayer

Manages subscription payment execution on Tron (TVM) using tronpy.
Mirrors the EVM GaslessRelayer pattern with identical return shapes
so the scheduler can treat all chains uniformly.

Responsibilities:
  - Build, sign, and submit transactions to the DariSubscriptionsTron contract
  - Track all transactions in the RelayerTransaction table
  - Return uniform result dicts: {tx_hash, status, gas_used, block_number}
"""

import asyncio
import logging
import time
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any

from tronpy import Tron
from tronpy.keys import PrivateKey
from tronpy.exceptions import TransactionError, BadAddress

from app.core.config import settings
from app.models.models import RelayerTransaction, RelayerTxStatus

logger = logging.getLogger(__name__)


# ABI for DariSubscriptionsTron (only the functions we call)
TRON_SUBSCRIPTION_ABI = [
    {
        "inputs": [
            {"name": "subscriber", "type": "address"},
            {"name": "merchant", "type": "address"},
            {"name": "token", "type": "address"},
            {"name": "amount", "type": "uint128"},
            {"name": "interval", "type": "uint64"},
            {"name": "startTime", "type": "uint64"},
        ],
        "name": "createSubscription",
        "outputs": [{"name": "subscriptionId", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"name": "subscriptionId", "type": "uint256"}],
        "name": "executePayment",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"name": "subscriptionId", "type": "uint256"}],
        "name": "cancelSubscription",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "subscriptionId", "type": "uint256"},
            {"name": "newAmount", "type": "uint128"},
            {"name": "newInterval", "type": "uint64"},
        ],
        "name": "updateSubscription",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"name": "subscriptionId", "type": "uint256"}],
        "name": "getSubscription",
        "outputs": [
            {
                "components": [
                    {"name": "subscriber", "type": "address"},
                    {"name": "interval", "type": "uint64"},
                    {"name": "active", "type": "bool"},
                    {"name": "merchant", "type": "address"},
                    {"name": "nextPayment", "type": "uint64"},
                    {"name": "paymentCount", "type": "uint32"},
                    {"name": "token", "type": "address"},
                    {"name": "amount", "type": "uint128"},
                ],
                "name": "",
                "type": "tuple",
            }
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "subscriptionId", "type": "uint256"}],
        "name": "isPaymentDue",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "subscriptionCount",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]


class TronRelayer:
    """
    Subscription relayer for Tron (TVM).

    Uses tronpy to build, sign, and broadcast transactions to the
    DariSubscriptionsTron smart contract.
    """

    def __init__(self):
        self._client: Optional[Tron] = None
        self._private_key: Optional[PrivateKey] = None
        self._address: Optional[str] = None
        self._contract = None

        # Initialize from settings
        pk_hex = getattr(settings, "TRON_RELAYER_PRIVATE_KEY", "")
        if pk_hex:
            try:
                self._private_key = PrivateKey(bytes.fromhex(pk_hex))
                self._address = self._private_key.public_key.to_base58check_address()
                logger.info(f"✅ Tron relayer initialized: {self._address}")
            except Exception as e:
                logger.error(f"❌ Failed to initialize Tron relayer key: {e}")
        else:
            logger.warning("⚠️  TRON_RELAYER_PRIVATE_KEY not set — Tron relayer disabled")

    @property
    def address(self) -> Optional[str]:
        """Get relayer wallet address (base58)"""
        return self._address

    def _get_client(self) -> Tron:
        """Get or create Tron client"""
        if self._client is not None:
            return self._client

        api_url = getattr(settings, "TRON_API_URL", "")
        if not api_url:
            raise ValueError("TRON_API_URL not configured")

        # Determine network from URL
        if "nile" in api_url or "shasta" in api_url:
            self._client = Tron(network="nile")
        else:
            self._client = Tron()

        # Set API key if available
        api_key = getattr(settings, "TRON_API_KEY", None)
        if api_key:
            self._client.conf["headers"] = {"TRON-PRO-API-KEY": api_key}

        return self._client

    def _get_contract(self):
        """Get or create contract instance"""
        if self._contract is not None:
            return self._contract

        contract_address = getattr(settings, "SUBSCRIPTION_CONTRACT_TRON", "")
        if not contract_address:
            raise ValueError("SUBSCRIPTION_CONTRACT_TRON not configured")

        client = self._get_client()
        self._contract = client.get_contract(contract_address)
        return self._contract

    async def _send_transaction(
        self,
        function_name: str,
        contract_call,
        fee_limit: int = 100_000_000,  # 100 TRX default fee limit
        db=None,
        subscription_id=None,
    ) -> Dict[str, Any]:
        """
        Build, sign, send a transaction and wait for confirmation.

        Returns:
            Dict with tx_hash, status, gas_used, block_number matching
            the EVM relayer's format.
        """
        if not self._private_key:
            raise RuntimeError("Tron relayer not initialized — TRON_RELAYER_PRIVATE_KEY not set")

        # Create RelayerTransaction record
        relayer_tx = None
        if db:
            relayer_tx = RelayerTransaction(
                chain="tron",
                function_name=function_name,
                relayer_address=self._address or "",
                nonce=0,  # Tron doesn't use sequential nonces like EVM
                status=RelayerTxStatus.PENDING,
            )
            if subscription_id:
                relayer_tx.subscription_id = subscription_id
            db.add(relayer_tx)
            db.flush()

        try:
            # Build and sign the transaction
            # tronpy uses a builder pattern: contract_call already has the function + args
            txn = (
                contract_call
                .with_owner(self._address)
                .fee_limit(fee_limit)
                .build()
                .sign(self._private_key)
            )

            # Broadcast
            result = txn.broadcast()
            tx_hash = result.get("txid", "")

            logger.info(f"[tron] 📤 Tx sent: {function_name} | hash={tx_hash[:16]}...")

            if relayer_tx:
                relayer_tx.tx_hash = tx_hash

            # Wait for confirmation
            receipt = await asyncio.to_thread(result.wait, timeout=120)

            # Parse result
            energy_used = receipt.get("receipt", {}).get("energy_usage_total", 0)
            net_used = receipt.get("receipt", {}).get("net_usage", 0)
            block_number = receipt.get("blockNumber", None)
            tx_status = receipt.get("receipt", {}).get("result", "")

            is_success = tx_status in ("SUCCESS", "") and receipt.get("result") != "FAILED"

            if relayer_tx:
                relayer_tx.gas_used = energy_used
                relayer_tx.confirmed_at = datetime.utcnow()

                if is_success:
                    relayer_tx.status = RelayerTxStatus.CONFIRMED
                else:
                    relayer_tx.status = RelayerTxStatus.REVERTED
                    relayer_tx.error_message = f"Tron tx reverted: {tx_status}"

            if db:
                db.commit()

            status_str = "confirmed" if is_success else "reverted"

            if is_success:
                logger.info(f"[tron] ✅ Tx confirmed: {function_name} | energy={energy_used}")
            else:
                logger.error(f"[tron] ❌ Tx reverted: {function_name} | status={tx_status}")

            return {
                "tx_hash": tx_hash,
                "status": status_str,
                "gas_used": energy_used,
                "gas_cost_native": str(Decimal(energy_used) * Decimal("0.000420")),  # ~energy price
                "block_number": block_number,
            }

        except Exception as e:
            logger.error(f"[tron] ❌ Tx failed: {function_name} | error={e}")
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
        token: str,
        amount: int,
        interval: int,
        start_time: int,
        db=None,
        subscription_id=None,
    ) -> Dict[str, Any]:
        """
        Create a subscription on Tron.

        Args:
            subscriber: Subscriber wallet address (base58)
            merchant: Merchant wallet address (base58)
            token: TRC20 token contract address (base58)
            amount: Amount in token decimals (uint128)
            interval: Billing interval in seconds
            start_time: First payment timestamp
        """
        contract = self._get_contract()

        # Use latest block timestamp for safety (like EVM relayer)
        client = self._get_client()
        try:
            block = client.get_latest_block()
            onchain_ts = int(block.get("block_header", {}).get("raw_data", {}).get("timestamp", 0)) // 1000
        except Exception:
            onchain_ts = int(time.time())

        safe_start_time = onchain_ts + 5

        logger.info(
            f"[tron] createSubscription startTime={safe_start_time} "
            f"(onchain_ts={onchain_ts}, caller_start_time={start_time})"
        )

        contract_call = contract.functions.createSubscription(
            subscriber, merchant, token, amount, interval, safe_start_time
        )

        result = await self._send_transaction(
            "createSubscription", contract_call, db=db, subscription_id=subscription_id
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
        Execute a due payment on Tron.

        Args:
            onchain_subscription_id: Smart contract subscription ID
        """
        contract = self._get_contract()
        contract_call = contract.functions.executePayment(onchain_subscription_id)
        return await self._send_transaction(
            "executePayment", contract_call, db=db, subscription_id=subscription_id
        )

    async def cancel_subscription_onchain(
        self,
        onchain_subscription_id: int,
        db=None,
        subscription_id=None,
    ) -> Dict[str, Any]:
        """Cancel a subscription on Tron."""
        contract = self._get_contract()
        contract_call = contract.functions.cancelSubscription(onchain_subscription_id)
        return await self._send_transaction(
            "cancelSubscription", contract_call, db=db, subscription_id=subscription_id
        )

    async def update_subscription_onchain(
        self,
        onchain_subscription_id: int,
        new_amount: int,
        new_interval: int,
        db=None,
        subscription_id=None,
    ) -> Dict[str, Any]:
        """Update a subscription on Tron (amount can only decrease)."""
        contract = self._get_contract()
        contract_call = contract.functions.updateSubscription(
            onchain_subscription_id, new_amount, new_interval
        )
        return await self._send_transaction(
            "updateSubscription", contract_call, db=db, subscription_id=subscription_id
        )

    # ============= READ-ONLY METHODS =============

    def get_onchain_subscription(self, onchain_id: int) -> Dict:
        """Read subscription data from smart contract"""
        contract = self._get_contract()
        data = contract.functions.getSubscription(onchain_id)
        return {
            "subscriber": data[0],
            "interval": data[1],
            "active": data[2],
            "merchant": data[3],
            "nextPayment": data[4],
            "paymentCount": data[5],
            "token": data[6],
            "amount": data[7],
        }

    def is_payment_due_onchain(self, onchain_id: int) -> bool:
        """Check if payment is due on-chain"""
        contract = self._get_contract()
        return contract.functions.isPaymentDue(onchain_id)

    def get_relayer_balance(self) -> Dict[str, str]:
        """Get relayer's TRX balance"""
        if not self._address:
            return {"balance": "0", "address": ""}

        client = self._get_client()
        balance_sun = client.get_account_balance(self._address)

        return {
            "chain": "tron",
            "address": self._address,
            "balance_native": str(balance_sun),
        }


# Singleton instance
tron_relayer = TronRelayer()
