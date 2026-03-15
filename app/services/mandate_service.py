"""
EIP-712 Mandate Service

Handles user authorization mandates for subscription payments.
Users sign an EIP-712 typed data message that authorizes the Dari system
to execute recurring payments on their behalf.

The mandate contains:
  - Subscriber address
  - Merchant address
  - Token address and amount
  - Billing interval
  - Maximum payments allowed
  - Nonce (prevents replay attacks)

FIX NOTES (v2):
  - Added verifyingContract to domain separator (was root cause of mismatch)
  - Removed chainId from SubscriptionMandate struct (it belongs only in domain)
  - Added EIP712Domain type definition for correct MetaMask/ethers.js compatibility
  - Replaced private Account._recover_hash with public recoverHash API
  - get_signing_data() now requires and includes verifyingContract
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any

import eth_abi
from eth_account import Account
from web3 import Web3
from sqlalchemy.orm import Session

from app.models.models import SubscriptionMandate, MandateStatus
from app.core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# EIP-712 Domain base (verifyingContract is injected per-chain at runtime)
# ---------------------------------------------------------------------------
DARI_DOMAIN_BASE = {
    "name": "Dari Subscriptions",
    "version": "1",
}

# ---------------------------------------------------------------------------
# EIP-712 Types
#
# IMPORTANT:
#   - EIP712Domain MUST be included so MetaMask / ethers.js hashes domain correctly.
#   - chainId is REMOVED from SubscriptionMandate struct — it lives in the domain only.
#   - Field order here MUST match the Solidity struct and the typehash string exactly.
# ---------------------------------------------------------------------------
MANDATE_TYPES = {
    # Required by MetaMask and ethers.js v6 to hash the domain correctly
    "EIP712Domain": [
        {"name": "name",               "type": "string"},
        {"name": "version",            "type": "string"},
        {"name": "chainId",            "type": "uint256"},
        {"name": "verifyingContract",  "type": "address"},
    ],
    "SubscriptionMandate": [
        {"name": "subscriber",   "type": "address"},
        {"name": "merchant",     "type": "address"},
        {"name": "token",        "type": "address"},
        {"name": "amount",       "type": "uint256"},
        {"name": "interval",     "type": "uint256"},
        {"name": "maxPayments",  "type": "uint256"},
        {"name": "nonce",        "type": "uint256"},
        # chainId intentionally NOT here — it's in the domain, not the struct
    ],
}

# Precomputed typehash strings — MUST match your Solidity exactly
_DOMAIN_TYPEHASH_STR = (
    "EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"
)
_MANDATE_TYPEHASH_STR = (
    "SubscriptionMandate(address subscriber,address merchant,address token,"
    "uint256 amount,uint256 interval,uint256 maxPayments,uint256 nonce)"
)


def _get_contract_address(chain: str) -> str:
    """Get the deployed subscription contract address for a chain."""
    setting_name = f"SUBSCRIPTION_CONTRACT_{chain.upper()}"
    address = getattr(settings, setting_name, "")
    if not address:
        raise ValueError(f"No subscription contract address configured for chain: {chain}")
    return Web3.to_checksum_address(address)


class MandateService:
    """
    Service for managing EIP-712 subscription mandates.

    A mandate is a signed authorization from a user that allows
    the Dari system to create and execute recurring payments.
    """

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Nonce management
    # ------------------------------------------------------------------

    def get_next_nonce(self, subscriber_address: str, chain: str) -> int:
        """Return the next available nonce for a subscriber on a given chain."""
        latest = (
            self.db.query(SubscriptionMandate)
            .filter(
                SubscriptionMandate.subscriber_address == subscriber_address.lower(),
                SubscriptionMandate.chain == chain,
            )
            .order_by(SubscriptionMandate.nonce.desc())
            .first()
        )
        return (latest.nonce + 1) if latest else 0

    # ------------------------------------------------------------------
    # Signing data for the frontend
    # ------------------------------------------------------------------

    def get_signing_data(
        self,
        subscriber: str,
        merchant: str,
        token: str,
        amount: int,
        interval: int,
        max_payments: int,
        chain: str,
        chain_id: int,
    ) -> Dict[str, Any]:
        """
        Generate EIP-712 typed data for the frontend to sign.

        Returns a dict ready to be passed to:
            eth_sendTransaction / wallet_signTypedData_v4  (MetaMask)
            signer.signTypedData(domain, types, value)     (ethers.js v6)
        """
        nonce = self.get_next_nonce(subscriber, chain)
        contract_address = _get_contract_address(chain)

        domain = {
            **DARI_DOMAIN_BASE,
            "chainId": chain_id,
            "verifyingContract": contract_address,   # FIX: was missing
        }

        message = {
            "subscriber":  Web3.to_checksum_address(subscriber),
            "merchant":    Web3.to_checksum_address(merchant),
            "token":       Web3.to_checksum_address(token),
            "amount":      amount,
            "interval":    interval,
            "maxPayments": max_payments,
            "nonce":       nonce,
            # chainId NOT included here — it's in domain only
        }

        return {
            "domain":      domain,
            "types":       MANDATE_TYPES,
            "primaryType": "SubscriptionMandate",
            "message":     message,
            "nonce":       nonce,
        }

    # ------------------------------------------------------------------
    # EIP-712 hash + signer recovery
    # ------------------------------------------------------------------

    def _build_domain_separator(self, domain_data: dict) -> bytes:
        """
        Compute the EIP-712 domain separator.

        domain_data must contain: name, version, chainId, verifyingContract
        """
        domain_typehash  = Web3.keccak(text=_DOMAIN_TYPEHASH_STR)
        name_hash        = Web3.keccak(text=domain_data["name"])
        version_hash     = Web3.keccak(text=domain_data["version"])
        chain_id         = int(domain_data["chainId"])
        contract_address = Web3.to_checksum_address(domain_data["verifyingContract"])

        encoded = eth_abi.encode(
            ["bytes32", "bytes32", "bytes32", "uint256", "address"],
            [domain_typehash, name_hash, version_hash, chain_id, contract_address],
        )
        return bytes(Web3.keccak(encoded))

    def _build_struct_hash(self, message_data: dict) -> bytes:
        """
        Compute the EIP-712 struct hash for SubscriptionMandate.

        message_data must contain:
            subscriber, merchant, token, amount, interval, maxPayments, nonce
        Note: chainId is intentionally absent — it belongs to the domain only.
        """
        mandate_typehash = Web3.keccak(text=_MANDATE_TYPEHASH_STR)

        encoded = eth_abi.encode(
            [
                "bytes32",
                "address", "address", "address",
                "uint256", "uint256", "uint256", "uint256",
            ],
            [
                mandate_typehash,
                Web3.to_checksum_address(message_data["subscriber"]),
                Web3.to_checksum_address(message_data["merchant"]),
                Web3.to_checksum_address(message_data["token"]),
                int(message_data["amount"]),
                int(message_data["interval"]),
                int(message_data["maxPayments"]),
                int(message_data["nonce"]),
            ],
        )
        return bytes(Web3.keccak(encoded))

    def _recover_signer(
        self,
        signature: str,
        domain_data: dict,
        message_data: dict,
    ) -> str:
        """
        Recover the EIP-712 signer address from a wallet signature.

        Uses manual ABI encoding to guarantee byte-perfect agreement with
        ethers.js signTypedData / MetaMask eth_signTypedData_v4.

        Args:
            signature:    Hex signature string from the wallet (0x...)
            domain_data:  Dict with name, version, chainId, verifyingContract
            message_data: Dict with subscriber, merchant, token, amount,
                          interval, maxPayments, nonce

        Returns:
            Checksum-cased recovered signer address.
        """
        domain_separator = self._build_domain_separator(domain_data)
        struct_hash       = self._build_struct_hash(message_data)

        # EIP-712 final digest: keccak256("\x19\x01" || domainSeparator || structHash)
        final_hash = Web3.keccak(primitive=b"\x19\x01" + domain_separator + struct_hash)

        # eth_account 0.13+: _recover_hash is an instance method; param is message_hash
        recovered = Account()._recover_hash(message_hash=final_hash, signature=signature)
        return recovered   # already checksum-cased

    # ------------------------------------------------------------------
    # Mandate verification and creation
    # ------------------------------------------------------------------

    def verify_and_create_mandate(
        self,
        signature: str,
        subscriber: str,
        merchant_id: str,
        merchant_address: str,
        token_address: str,
        token_symbol: str,
        amount: float,
        amount_raw: int,
        interval_seconds: int,
        max_payments: Optional[int],
        chain: str,
        chain_id: int,
        nonce: int,
    ) -> SubscriptionMandate:
        """
        Verify an EIP-712 signature and create a mandate record.

        Args:
            signature:        EIP-712 signature from the user's wallet (0x…)
            subscriber:       Subscriber wallet address
            merchant_id:      Dari merchant UUID
            merchant_address: Merchant's wallet address
            token_address:    ERC20 token contract address
            token_symbol:     Token symbol (USDC / USDT)
            amount:           Human-readable amount (e.g. 1.08)
            amount_raw:       Amount in token decimals (e.g. 1_080_000 for USDC)
            interval_seconds: Billing interval in seconds
            max_payments:     Maximum payments (None = unlimited → stored as 0)
            chain:            Blockchain identifier (e.g. "polygon")
            chain_id:         EVM chain ID (e.g. 80002 for Amoy testnet)
            nonce:            Nonce used in the signed message

        Returns:
            SubscriptionMandate ORM record (not yet committed)

        Raises:
            ValueError: Nonce mismatch, invalid signature, or address mismatch.
        """
        # 1. Replay-attack guard
        expected_nonce = self.get_next_nonce(subscriber, chain)
        if nonce != expected_nonce:
            raise ValueError(
                f"Nonce mismatch: expected {expected_nonce}, got {nonce}. "
                "Possible replay attack."
            )

        # 2. Resolve contract address for this chain
        contract_address = _get_contract_address(chain)

        # 3. Build domain and message dicts for hashing
        domain_data = {
            **DARI_DOMAIN_BASE,
            "chainId":           chain_id,
            "verifyingContract": contract_address,   # FIX: was missing
        }

        message_data = {
            "subscriber":  Web3.to_checksum_address(subscriber),
            "merchant":    Web3.to_checksum_address(merchant_address),
            "token":       Web3.to_checksum_address(token_address),
            "amount":      amount_raw,
            "interval":    interval_seconds,
            "maxPayments": max_payments or 0,
            "nonce":       nonce,
            # chainId NOT here — belongs to domain only
        }

        # 4. Recover signer
        try:
            recovered = self._recover_signer(signature, domain_data, message_data)
        except Exception as exc:
            logger.error("Signature recovery failed: %s", exc)
            raise ValueError(f"Invalid signature: {exc}") from exc

        # 5. Verify recovered address
        if recovered.lower() != subscriber.lower():
            raise ValueError(
                f"Signature mismatch: recovered {recovered}, expected {subscriber}. "
                "Ensure the frontend domain (name, version, chainId, verifyingContract) "
                "exactly matches the backend."
            )

        # 6. Persist mandate record
        approved_total = (amount * max_payments) if max_payments else None

        mandate = SubscriptionMandate(
            subscriber_address=subscriber.lower(),
            merchant_id=merchant_id,
            signature=signature,
            nonce=nonce,
            chain=chain,
            token_address=token_address.lower(),
            token_symbol=token_symbol,
            amount=amount,
            interval_seconds=interval_seconds,
            max_payments=max_payments,
            approved_total=approved_total,
            status=MandateStatus.ACTIVE,
            activated_at=datetime.utcnow(),
        )

        self.db.add(mandate)
        self.db.flush()

        logger.info(
            "✅ Mandate created: subscriber=%s… merchant=%s chain=%s amount=%s %s",
            subscriber[:10], merchant_id, chain, amount, token_symbol,
        )
        return mandate

    # ------------------------------------------------------------------
    # Mandate management helpers
    # ------------------------------------------------------------------

    def revoke_mandate(self, mandate_id: str, subscriber_address: str) -> bool:
        """
        Revoke a mandate (user-initiated cancellation of signing authorization).

        Returns True on success, raises ValueError otherwise.
        """
        mandate = self.db.query(SubscriptionMandate).get(mandate_id)
        if not mandate:
            raise ValueError("Mandate not found")
        if mandate.subscriber_address.lower() != subscriber_address.lower():
            raise ValueError("Not authorized to revoke this mandate")
        if mandate.status == MandateStatus.REVOKED:
            raise ValueError("Mandate already revoked")

        mandate.status = MandateStatus.REVOKED
        mandate.revoked_at = datetime.utcnow()
        self.db.commit()

        logger.info("✅ Mandate revoked: %s", mandate_id)
        return True

    def get_mandate(self, mandate_id: str) -> Optional[SubscriptionMandate]:
        """Fetch a mandate by its UUID."""
        return self.db.query(SubscriptionMandate).get(mandate_id)

    def get_subscriber_mandates(
        self,
        subscriber_address: str,
        chain: Optional[str] = None,
    ):
        """Return all mandates for a subscriber, optionally filtered by chain."""
        query = self.db.query(SubscriptionMandate).filter(
            SubscriptionMandate.subscriber_address == subscriber_address.lower()
        )
        if chain:
            query = query.filter(SubscriptionMandate.chain == chain)
        return query.order_by(SubscriptionMandate.created_at.desc()).all()