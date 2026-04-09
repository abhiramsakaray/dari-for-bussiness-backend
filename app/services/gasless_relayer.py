"""
Gasless Relayer Service

Manages transaction execution on behalf of users. The relayer is a funded EOA
wallet that signs and submits blockchain transactions, paying gas fees so users
don't have to.

Responsibilities:
  - Build, sign, and submit transactions to smart contracts
  - Manage nonces (max of chain nonce vs local pending nonce)
  - Estimate gas with safety buffer
  - Track all transactions in the RelayerTransaction table
  - Monitor relayer balance for alerts
"""

import asyncio
import logging
import time
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any

from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from eth_account import Account

from app.core.config import settings
from app.models.models import RelayerTransaction, RelayerTxStatus

logger = logging.getLogger(__name__)

# DariSubscriptions ABI (only the functions we call)
SUBSCRIPTION_ABI = [
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

# Chain RPC endpoints and config
CHAIN_CONFIG = {
    "ethereum": {
        "rpc_url_setting": "ETHEREUM_RPC_URL",
        "chain_id_setting": "ETHEREUM_CHAIN_ID",
        "contract_setting": "SUBSCRIPTION_CONTRACT_ETHEREUM",
        "is_poa": False,
    },
    "polygon": {
        "rpc_url_setting": "POLYGON_RPC_URL",
        "chain_id_setting": "POLYGON_CHAIN_ID",
        "contract_setting": "SUBSCRIPTION_CONTRACT_POLYGON",
        "is_poa": True,
    },
    "base": {
        "rpc_url_setting": "BASE_RPC_URL",
        "chain_id_setting": "BASE_CHAIN_ID",
        "contract_setting": "SUBSCRIPTION_CONTRACT_BASE",
        "is_poa": True,
    },
    "arbitrum": {
        "rpc_url_setting": "ARBITRUM_MAINNET_RPC_URL",
        "chain_id_setting": None,
        "contract_setting": "SUBSCRIPTION_CONTRACT_ARBITRUM",
        "is_poa": True,
    },
}


class GaslessRelayer:
    """
    Gasless transaction relayer for Dari for Business.
    
    Manages a funded EOA wallet per chain that signs and submits
    transactions to the DariSubscriptions smart contract.
    """

    def __init__(self):
        self._account = None
        self._w3_instances: Dict[str, Web3] = {}
        self._contracts: Dict[str, Any] = {}
        self._nonce_locks: Dict[str, asyncio.Lock] = {}
        self._local_nonces: Dict[str, int] = {}
        
        # Initialize account from private key
        private_key = getattr(settings, "RELAYER_PRIVATE_KEY", "")
        if private_key:
            self._account = Account.from_key(private_key)
            logger.info(f"✅ Relayer initialized: {self._account.address}")
        else:
            logger.warning("⚠️  RELAYER_PRIVATE_KEY not set — relayer disabled")

    @property
    def address(self) -> Optional[str]:
        """Get relayer wallet address"""
        return self._account.address if self._account else None

    def _get_w3(self, chain: str) -> Web3:
        """Get or create Web3 instance for a chain"""
        if chain in self._w3_instances:
            return self._w3_instances[chain]

        config = CHAIN_CONFIG.get(chain)
        if not config:
            raise ValueError(f"Unsupported chain: {chain}")

        rpc_url = getattr(settings, config["rpc_url_setting"], "")
        if not rpc_url:
            raise ValueError(f"No RPC URL configured for chain: {chain}")

        w3 = Web3(Web3.HTTPProvider(rpc_url))

        # Add POA middleware for Polygon, Base, Arbitrum
        if config.get("is_poa"):
            w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

        self._w3_instances[chain] = w3
        return w3

    def _get_contract(self, chain: str):
        """Get or create contract instance for a chain"""
        if chain in self._contracts:
            return self._contracts[chain]

        config = CHAIN_CONFIG.get(chain)
        if not config:
            raise ValueError(f"Unsupported chain: {chain}")

        contract_address = getattr(settings, config["contract_setting"], "")
        if not contract_address:
            raise ValueError(f"No contract address configured for chain: {chain}")

        w3 = self._get_w3(chain)
        contract = w3.eth.contract(
            address=Web3.to_checksum_address(contract_address),
            abi=SUBSCRIPTION_ABI,
        )
        self._contracts[chain] = contract
        return contract

    async def _get_nonce(self, chain: str) -> int:
        """
        Get the next nonce, using max(chain_nonce, local_pending_nonce).
        This prevents issues with stale RPC nonce responses.
        """
        if chain not in self._nonce_locks:
            self._nonce_locks[chain] = asyncio.Lock()

        async with self._nonce_locks[chain]:
            w3 = self._get_w3(chain)
            chain_nonce = w3.eth.get_transaction_count(self._account.address, "pending")
            local_nonce = self._local_nonces.get(chain, 0)
            nonce = max(chain_nonce, local_nonce)
            self._local_nonces[chain] = nonce + 1
            return nonce

    def _estimate_gas_price(self, chain: str) -> int:
        """Estimate gas price with safety cap"""
        w3 = self._get_w3(chain)
        gas_price = w3.eth.gas_price

        # Apply 20% buffer
        buffered = int(gas_price * 1.2)

        # Apply max cap from settings
        max_gwei = getattr(settings, "RELAYER_MAX_GAS_PRICE_GWEI", 100)
        max_wei = int(max_gwei * 1e9)

        return min(buffered, max_wei)

    async def _send_transaction(
        self,
        chain: str,
        function_name: str,
        tx_func,
        db=None,
        subscription_id=None,
    ) -> Dict[str, Any]:
        """
        Build, sign, send a transaction and wait for receipt.
        
        Returns:
            Dict with tx_hash, status, gas_used, etc.
        """
        if not self._account:
            raise RuntimeError("Relayer not initialized — RELAYER_PRIVATE_KEY not set")

        w3 = self._get_w3(chain)
        nonce = await self._get_nonce(chain)
        gas_price = self._estimate_gas_price(chain)

        # Estimate gas
        try:
            gas_estimate = tx_func.estimate_gas({"from": self._account.address})
            gas_limit = int(gas_estimate * 1.3)  # 30% safety buffer
        except Exception as e:
            # Extract detailed error info
            error_msg = str(e)
            error_type = type(e).__name__
            
            # Log detailed error for debugging (don't raise yet, provide context)
            logger.error(
                f"[{chain}] ❌ Gas estimation failed for {function_name}:\n"
                f"  Error Type: {error_type}\n"
                f"  Error Message: {error_msg}\n"
                f"  Relayer Address: {self._account.address}\n"
                f"  Subscription ID: {subscription_id if subscription_id else 'N/A'}"
            )
            
            # If it's a contract revert, try to provide more context
            if "revert" in error_msg.lower() or "0x" in error_msg:
                logger.warning(
                    f"[{chain}] ⚠️  Contract revert during gas estimation. "
                    f"Possible causes: subscription not found, relayer not approved, "
                    f"subscription not due yet, or already executed."
                )
            
            raise

        # Build transaction
        config = CHAIN_CONFIG.get(chain)
        chain_id = getattr(settings, config["chain_id_setting"], 1) if config.get("chain_id_setting") else 1

        tx = tx_func.build_transaction({
            "from": self._account.address,
            "nonce": nonce,
            "gas": gas_limit,
            "gasPrice": gas_price,
            "chainId": chain_id,
        })

        # Sign transaction
        signed_tx = w3.eth.account.sign_transaction(tx, self._account.key)

        # Create RelayerTransaction record
        relayer_tx = None
        if db:
            relayer_tx = RelayerTransaction(
                chain=chain,
                function_name=function_name,
                relayer_address=self._account.address,
                nonce=nonce,
                status=RelayerTxStatus.PENDING,
            )
            if subscription_id:
                relayer_tx.subscription_id = subscription_id
            db.add(relayer_tx)
            db.flush()

        # Send transaction
        try:
            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            tx_hash_hex = tx_hash.hex()
            logger.info(f"[{chain}] 📤 Tx sent: {function_name} | hash={tx_hash_hex}")

            if relayer_tx:
                relayer_tx.tx_hash = tx_hash_hex

            # Wait for receipt (with timeout)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

            # Update record
            gas_used = receipt.get("gasUsed", 0)
            effective_price = receipt.get("effectiveGasPrice", gas_price)
            gas_cost_wei = gas_used * effective_price
            gas_cost_native = Decimal(str(gas_cost_wei)) / Decimal("1e18")

            if relayer_tx:
                relayer_tx.gas_used = gas_used
                relayer_tx.gas_price = effective_price
                relayer_tx.gas_cost_native = gas_cost_native
                relayer_tx.confirmed_at = datetime.utcnow()

                if receipt["status"] == 1:
                    relayer_tx.status = RelayerTxStatus.CONFIRMED
                else:
                    relayer_tx.status = RelayerTxStatus.REVERTED
                    relayer_tx.error_message = "Transaction reverted"

            if db:
                db.commit()

            result = {
                "tx_hash": tx_hash_hex,
                "status": "confirmed" if receipt["status"] == 1 else "reverted",
                "gas_used": gas_used,
                "gas_cost_native": str(gas_cost_native),
                "block_number": receipt.get("blockNumber"),
            }

            if receipt["status"] == 1:
                logger.info(f"[{chain}] ✅ Tx confirmed: {function_name} | gas={gas_used}")
            else:
                logger.error(f"[{chain}] ❌ Tx reverted: {function_name}")

            return result

        except Exception as e:
            logger.error(f"[{chain}] ❌ Tx failed: {function_name} | error={e}")
            if relayer_tx:
                relayer_tx.status = RelayerTxStatus.FAILED
                relayer_tx.error_message = str(e)[:500]
                if db:
                    db.commit()
            raise

    # ============= PUBLIC METHODS =============

    async def create_subscription_onchain(
        self,
        chain: str,
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
        Create a subscription on-chain.
        
        Args:
            chain: Target blockchain
            subscriber: Subscriber wallet address
            merchant: Merchant wallet address
            token: ERC20 token contract address
            amount: Amount in token decimals (uint128)
            interval: Billing interval in seconds (uint64)
            start_time: First payment timestamp (uint64)
        """
        contract = self._get_contract(chain)
        w3 = self._get_w3(chain)

        # Use on-chain block.timestamp so gas estimation never sees a past startTime.
        # Python's clock can drift vs the RPC node, causing InvalidStartTime() reverts.
        try:
            latest_block = w3.eth.get_block("latest")
            onchain_ts = int(latest_block["timestamp"])
        except Exception:
            onchain_ts = int(time.time())

        # Allow minimal buffer (5 s) so the tx lands safely in the future regardless
        # of node-clock drift or slow mempool inclusion.
        safe_start_time = onchain_ts + 5

        logger.info(
            f"[{chain}] createSubscription startTime={safe_start_time} "
            f"(onchain_ts={onchain_ts}, caller_start_time={start_time})"
        )

        tx_func = contract.functions.createSubscription(
            Web3.to_checksum_address(subscriber),
            Web3.to_checksum_address(merchant),
            Web3.to_checksum_address(token),
            amount,
            interval,
            safe_start_time,
        )
        result = await self._send_transaction(
            chain, "createSubscription", tx_func, db, subscription_id
        )
        # Include the actual startTime used so callers can sync next_payment_at in DB
        result["start_time"] = safe_start_time
        return result

    async def execute_payment(
        self,
        chain: str,
        onchain_subscription_id: int,
        db=None,
        subscription_id=None,
    ) -> Dict[str, Any]:
        """
        Execute a due payment on-chain.
        
        Args:
            chain: Target blockchain
            onchain_subscription_id: Smart contract subscription ID
        """
        contract = self._get_contract(chain)
        tx_func = contract.functions.executePayment(onchain_subscription_id)
        return await self._send_transaction(
            chain, "executePayment", tx_func, db, subscription_id
        )

    async def cancel_subscription_onchain(
        self,
        chain: str,
        onchain_subscription_id: int,
        db=None,
        subscription_id=None,
    ) -> Dict[str, Any]:
        """
        Cancel a subscription on-chain.
        
        Args:
            chain: Target blockchain
            onchain_subscription_id: Smart contract subscription ID
        """
        contract = self._get_contract(chain)
        tx_func = contract.functions.cancelSubscription(onchain_subscription_id)
        return await self._send_transaction(
            chain, "cancelSubscription", tx_func, db, subscription_id
        )

    async def update_subscription_onchain(
        self,
        chain: str,
        onchain_subscription_id: int,
        new_amount: int,
        new_interval: int,
        db=None,
        subscription_id=None,
    ) -> Dict[str, Any]:
        """
        Update a subscription on-chain (amount can only decrease).
        """
        contract = self._get_contract(chain)
        tx_func = contract.functions.updateSubscription(
            onchain_subscription_id, new_amount, new_interval
        )
        return await self._send_transaction(
            chain, "updateSubscription", tx_func, db, subscription_id
        )

    # ============= READ-ONLY METHODS =============

    def get_onchain_subscription(self, chain: str, onchain_id: int) -> Dict:
        """Read subscription data from smart contract"""
        contract = self._get_contract(chain)
        data = contract.functions.getSubscription(onchain_id).call()
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

    def is_payment_due_onchain(self, chain: str, onchain_id: int) -> bool:
        """Check if payment is due on-chain"""
        contract = self._get_contract(chain)
        return contract.functions.isPaymentDue(onchain_id).call()

    def get_relayer_balance(self, chain: str) -> Dict[str, str]:
        """Get relayer's native token balance on a chain"""
        if not self._account:
            return {"balance": "0", "address": ""}

        w3 = self._get_w3(chain)
        balance_wei = w3.eth.get_balance(self._account.address)
        balance_eth = Decimal(str(balance_wei)) / Decimal("1e18")

        return {
            "chain": chain,
            "address": self._account.address,
            "balance_native": str(balance_eth),
            "balance_wei": str(balance_wei),
        }

    def get_all_balances(self) -> Dict[str, Dict]:
        """Get relayer balances across all configured chains"""
        balances = {}
        for chain in CHAIN_CONFIG:
            try:
                contract_addr = getattr(settings, CHAIN_CONFIG[chain]["contract_setting"], "")
                if contract_addr:
                    balances[chain] = self.get_relayer_balance(chain)
            except Exception as e:
                balances[chain] = {"error": str(e)}
        return balances


# Singleton instance
relayer = GaslessRelayer()
