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
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any

from eth_account.messages import encode_typed_data
from web3 import Web3
from sqlalchemy.orm import Session

from app.models.models import SubscriptionMandate, MandateStatus

logger = logging.getLogger(__name__)

# EIP-712 Domain
DARI_DOMAIN = {
    "name": "Dari Subscriptions",
    "version": "1",
}

# EIP-712 Types
MANDATE_TYPES = {
    "SubscriptionMandate": [
        {"name": "subscriber", "type": "address"},
        {"name": "merchant", "type": "address"},
        {"name": "token", "type": "address"},
        {"name": "amount", "type": "uint256"},
        {"name": "interval", "type": "uint256"},
        {"name": "maxPayments", "type": "uint256"},
        {"name": "nonce", "type": "uint256"},
        {"name": "chainId", "type": "uint256"},
    ],
}


class MandateService:
    """
    Service for managing EIP-712 subscription mandates.
    
    A mandate is a signed authorization from a user that allows
    the Dari system to create and execute recurring payments.
    """

    def __init__(self, db: Session):
        self.db = db

    def get_next_nonce(self, subscriber_address: str, chain: str) -> int:
        """Get the next available nonce for a subscriber on a chain"""
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
        
        Returns:
            Dict with domain, types, primaryType, and message
        """
        nonce = self.get_next_nonce(subscriber, chain)

        domain = {
            **DARI_DOMAIN,
            "chainId": chain_id,
        }

        message = {
            "subscriber": Web3.to_checksum_address(subscriber),
            "merchant": Web3.to_checksum_address(merchant),
            "token": Web3.to_checksum_address(token),
            "amount": amount,
            "interval": interval,
            "maxPayments": max_payments,
            "nonce": nonce,
            "chainId": chain_id,
        }

        return {
            "domain": domain,
            "types": MANDATE_TYPES,
            "primaryType": "SubscriptionMandate",
            "message": message,
            "nonce": nonce,
        }

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
            signature: EIP-712 signature from user's wallet
            subscriber: Subscriber wallet address
            merchant_id: Dari merchant UUID
            merchant_address: Merchant's wallet address
            token_address: ERC20 token contract address
            token_symbol: Token symbol (USDC/USDT)
            amount: Human-readable amount
            amount_raw: Amount in token decimals
            interval_seconds: Billing interval in seconds
            max_payments: Maximum number of payments (null = unlimited)
            chain: Blockchain identifier
            chain_id: EVM chain ID
            nonce: Nonce used in the signed message
            
        Returns:
            SubscriptionMandate record
            
        Raises:
            ValueError: If signature is invalid or nonce mismatch
        """
        # Verify nonce to prevent replay attacks
        expected_nonce = self.get_next_nonce(subscriber, chain)
        if nonce != expected_nonce:
            raise ValueError(
                f"Invalid nonce: expected {expected_nonce}, got {nonce}. "
                "This may be a replay attack."
            )

        # Build the EIP-712 message for recovery
        domain_data = {
            **DARI_DOMAIN,
            "chainId": chain_id,
        }

        message_data = {
            "subscriber": Web3.to_checksum_address(subscriber),
            "merchant": Web3.to_checksum_address(merchant_address),
            "token": Web3.to_checksum_address(token_address),
            "amount": amount_raw,
            "interval": interval_seconds,
            "maxPayments": max_payments or 0,
            "nonce": nonce,
            "chainId": chain_id,
        }

        # Recover signer from signature
        try:
            full_message = {
                "types": {
                    "EIP712Domain": [
                        {"name": "name", "type": "string"},
                        {"name": "version", "type": "string"},
                        {"name": "chainId", "type": "uint256"},
                    ],
                    **MANDATE_TYPES,
                },
                "primaryType": "SubscriptionMandate",
                "domain": domain_data,
                "message": message_data,
            }

            signable = encode_typed_data(full_message=full_message)
            recovered = Web3().eth.account.recover_message(
                signable, signature=signature
            )
        except Exception as e:
            logger.error(f"Signature recovery failed: {e}")
            raise ValueError(f"Invalid signature: {e}")

        # Verify recovered address matches subscriber
        if recovered.lower() != subscriber.lower():
            raise ValueError(
                f"Signature mismatch: recovered {recovered}, expected {subscriber}"
            )

        # Calculate total approved amount
        approved_total = None
        if max_payments:
            approved_total = amount * max_payments

        # Create mandate record
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
            f"✅ Mandate created: subscriber={subscriber[:10]}... "
            f"merchant={merchant_id} chain={chain} amount={amount} {token_symbol}"
        )

        return mandate

    def revoke_mandate(self, mandate_id: str, subscriber_address: str) -> bool:
        """
        Revoke a mandate (user-initiated cancellation of authorization).
        
        Args:
            mandate_id: Mandate UUID
            subscriber_address: Must match the mandate's subscriber
            
        Returns:
            True if revoked successfully
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

        logger.info(f"✅ Mandate revoked: {mandate_id}")
        return True

    def get_mandate(self, mandate_id: str) -> Optional[SubscriptionMandate]:
        """Get mandate by ID"""
        return self.db.query(SubscriptionMandate).get(mandate_id)

    def get_subscriber_mandates(
        self, subscriber_address: str, chain: Optional[str] = None
    ):
        """Get all mandates for a subscriber"""
        query = self.db.query(SubscriptionMandate).filter(
            SubscriptionMandate.subscriber_address == subscriber_address.lower()
        )
        if chain:
            query = query.filter(SubscriptionMandate.chain == chain)
        return query.order_by(SubscriptionMandate.created_at.desc()).all()
