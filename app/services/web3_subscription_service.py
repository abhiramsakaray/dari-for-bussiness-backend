"""
Web3 Subscription Service

Core business logic for Web3 subscription lifecycle management.
Orchestrates mandate verification, on-chain creation, cancellation,
and database state management.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from decimal import Decimal

from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from web3 import Web3

from app.models.models import (
    Web3Subscription, Web3SubscriptionStatus,
    SubscriptionMandate, MandateStatus,
    Web3SubscriptionPayment, RelayerTransaction,
    SubscriptionPlan, Merchant, MerchantWallet,
    PaymentStatus,
)
from app.services.gasless_relayer import relayer
from app.services.mandate_service import MandateService
from app.services.event_queue import EventService
from app.core.config import settings

logger = logging.getLogger(__name__)

# Interval name to seconds mapping
INTERVAL_SECONDS = {
    "daily": 86400,
    "weekly": 604800,
    "monthly": 2592000,       # 30 days
    "quarterly": 7776000,     # 90 days
    "yearly": 31536000,       # 365 days
}

TOKEN_ADDRESS_SETTINGS = {
    "ethereum": {
        "USDC": "ETHEREUM_USDC_ADDRESS",
        "USDT": "ETHEREUM_USDT_ADDRESS",
    },
    "polygon": {
        "USDC": "POLYGON_USDC_ADDRESS",
        "USDT": "POLYGON_USDT_ADDRESS",
    },
    "base": {
        "USDC": "BASE_USDC_ADDRESS",
    },
    "arbitrum": {
        "USDC": "ARBITRUM_USDC_ADDRESS",
        "USDT": "ARBITRUM_USDT_ADDRESS",
    },
}

# Chain to contract address mapping
def _get_contract_address(chain: str) -> str:
    """Get subscription contract address for a chain"""
    setting_name = f"SUBSCRIPTION_CONTRACT_{chain.upper()}"
    address = getattr(settings, setting_name, "")
    if not address:
        raise ValueError(f"No contract address configured for chain: {chain}")
    return address


def _resolve_token_address(chain: str, token_symbol: str, token_address: str) -> str:
    """Resolve token address from explicit input or settings defaults."""
    if token_address:
        return token_address

    setting_name = TOKEN_ADDRESS_SETTINGS.get(chain, {}).get(token_symbol.upper())
    if not setting_name:
        raise ValueError(
            f"Unsupported token {token_symbol} for chain {chain}. "
            "Provide token_address explicitly."
        )

    resolved = getattr(settings, setting_name, "")
    if not resolved:
        raise ValueError(
            f"No token address configured for {chain}/{token_symbol}. "
            f"Missing env: {setting_name}"
        )
    return resolved


class Web3SubscriptionService:
    """
    Service for managing the complete Web3 subscription lifecycle.
    
    Coordinates between:
      - MandateService (user authorization)
      - GaslessRelayer (on-chain execution)
      - Database (state management)
      - EventService (webhook notifications)
    """

    def __init__(self, db: Session):
        self.db = db
        self.mandate_service = MandateService(db)

    # ============= SUBSCRIPTION CREATION =============

    async def create_subscription(
        self,
        # Mandate data
        signature: str,
        subscriber_address: str,
        # Merchant & plan
        merchant_id: str,
        plan_id: Optional[str] = None,
        # Payment details
        token_address: str = "",
        token_symbol: str = "USDC",
        amount: float = 0,
        interval: str = "monthly",
        chain: str = "polygon",
        chain_id: int = 137,
        max_payments: Optional[int] = None,
        # Customer info
        customer_email: Optional[str] = None,
        customer_name: Optional[str] = None,
        nonce: int = 0,
    ) -> Web3Subscription:
        """
        Create a new Web3 subscription.
        
        Full flow:
          1. Verify EIP-712 mandate signature
          2. Resolve plan details (if plan_id provided)
          3. Create on-chain subscription via relayer
          4. Store subscription in database
          5. Emit event for webhooks
        """
        # Resolve plan and merchant
        plan = None
        if plan_id:
            plan = self.db.query(SubscriptionPlan).get(plan_id)
            if not plan:
                raise ValueError("Plan not found")
            merchant_id = str(plan.merchant_id)
            amount = float(plan.amount)
            interval = plan.interval.value if hasattr(plan.interval, 'value') else plan.interval
            if max_payments is None and plan.max_billing_cycles:
                max_payments = int(plan.max_billing_cycles)

        if not merchant_id:
            raise ValueError("merchant_id is required when plan_id is not provided")

        merchant = self.db.query(Merchant).get(merchant_id)
        if not merchant:
            raise ValueError("Merchant not found")

        # Get merchant wallet for the chain
        merchant_wallet = (
            self.db.query(MerchantWallet)
            .filter(
                MerchantWallet.merchant_id == merchant_id,
                MerchantWallet.chain == chain,
                MerchantWallet.is_active == True,
            )
            .first()
        )
        if not merchant_wallet:
            raise ValueError(f"Merchant has no active wallet on {chain}")

        merchant_address = merchant_wallet.wallet_address

        # Validate amount and resolve token address
        if amount <= 0:
            raise ValueError("Amount must be greater than zero")

        token_address = _resolve_token_address(chain, token_symbol, token_address)

        # Validate address formats early for clearer API errors
        if not Web3.is_address(subscriber_address):
            raise ValueError("Invalid subscriber wallet address")
        if not Web3.is_address(token_address):
            raise ValueError("Invalid token contract address")
        if not Web3.is_address(merchant_address):
            raise ValueError("Invalid merchant wallet address")

        # Convert interval to seconds
        interval_seconds = INTERVAL_SECONDS.get(interval)
        if not interval_seconds:
            raise ValueError(f"Invalid interval: {interval}")

        # Calculate token amount in decimals (USDC/USDT = 6 decimals)
        decimals = 6
        if hasattr(self, '_amount_raw_override') and self._amount_raw_override:
            # Use the exact integer from the request (avoids float rounding)
            amount_raw = self._amount_raw_override
        else:
            amount_raw = int(amount * (10 ** decimals))

        # Get contract address
        contract_address = _get_contract_address(chain)

        logger.info(
            f"Verifying mandate: subscriber={subscriber_address} "
            f"merchant={merchant_address} token={token_address} "
            f"amount_raw={amount_raw} interval={interval_seconds} "
            f"max_payments={max_payments} nonce={nonce} chain_id={chain_id}"
        )

        # Step 1: Verify mandate signature
        mandate = self.mandate_service.verify_and_create_mandate(
            signature=signature,
            subscriber=subscriber_address,
            merchant_id=merchant_id,
            merchant_address=merchant_address,
            token_address=token_address,
            token_symbol=token_symbol,
            amount=amount,
            amount_raw=amount_raw,
            interval_seconds=interval_seconds,
            max_payments=max_payments,
            chain=chain,
            chain_id=chain_id,
            nonce=nonce,
        )

        # Step 2: Calculate start time (first payment immediately with 60s buffer for Tx timing)
        start_time = int(datetime.utcnow().timestamp()) + 60

        # Step 3: Create on-chain subscription via relayer
        try:
            result = await relayer.create_subscription_onchain(
                chain=chain,
                subscriber=subscriber_address,
                merchant=merchant_address,
                token=token_address,
                amount=amount_raw,
                interval=interval_seconds,
                start_time=start_time,
                db=self.db,
            )
        except Exception as e:
            # Revert mandate if on-chain creation fails
            mandate.status = MandateStatus.REVOKED
            mandate.revoked_at = datetime.utcnow()
            self.db.commit()
            raise ValueError(f"On-chain subscription creation failed: {e}")

        # Step 4: Extract on-chain subscription ID from events/receipt
        # For now, read the subscription count from the contract
        onchain_id = None
        try:
            w3 = relayer._get_w3(chain)
            contract = relayer._get_contract(chain)
            onchain_id = contract.functions.subscriptionCount().call()
        except Exception:
            pass

        # Use the actual startTime the relayer sent to the contract (fetched from chain).
        actual_start_time = result.get("start_time", start_time)

        # Step 5: Store in database — PENDING_PAYMENT until first charge confirms
        subscription = Web3Subscription(
            onchain_subscription_id=onchain_id,
            chain=chain,
            contract_address=contract_address,
            subscriber_address=subscriber_address.lower(),
            merchant_address=merchant_address.lower(),
            token_address=token_address.lower(),
            token_symbol=token_symbol,
            amount=Decimal(str(amount)),
            interval_seconds=interval_seconds,
            next_payment_at=datetime.utcfromtimestamp(actual_start_time),
            status=Web3SubscriptionStatus.PENDING_PAYMENT,
            plan_id=None,
            merchant_id=merchant_id,
            mandate_id=mandate.id,
            created_tx_hash=result.get("tx_hash"),
            customer_email=customer_email,
            customer_name=customer_name,
            max_retries=0,
            retry_interval_hours=24,
            grace_period_days=3,
        )

        self.db.add(subscription)
        self.db.flush()

        # Step 6: Emit created event
        try:
            event_service = EventService(self.db)
            event_service.create_event(
                event_type="subscription.created",
                entity_type="web3_subscription",
                entity_id=str(subscription.id),
                merchant_id=merchant_id,
                payload={
                    "subscription_id": str(subscription.id),
                    "subscriber": subscriber_address,
                    "amount": str(amount),
                    "token": token_symbol,
                    "chain": chain,
                    "interval": interval,
                    "tx_hash": result.get("tx_hash"),
                },
            )
        except Exception as e:
            logger.warning(f"Event emission failed: {e}")

        self.db.commit()

        logger.info(
            f"✅ Web3 subscription created (PENDING_PAYMENT): {subscription.id} "
            f"| subscriber={subscriber_address[:10]}... "
            f"| amount={amount} {token_symbol} | chain={chain}"
        )

        # Step 7: Execute first payment IMMEDIATELY (don't wait for scheduler)
        if onchain_id:
            await self._execute_first_payment(subscription)

        return subscription

    async def _execute_first_payment(self, subscription: "Web3Subscription"):
        """
        Execute the first subscription payment immediately after creation.
        Sets status to ACTIVE on success, PAST_DUE on failure.
        """
        import asyncio
        
        # Calculate time remaining until the subscription's start time on-chain
        # The relayer baked in a 120s buffer for 'safe_start_time' to avoid createSubscription reverts.
        # We must wait until block.timestamp >= nextPayment to avoid PaymentNotDue() revert.
        now_ts = int(datetime.utcnow().timestamp())
        start_ts = int(subscription.next_payment_at.timestamp())
        wait_seconds = max(5, start_ts - now_ts + 5) # Check if we need to wait for the 120s buffer, minimum 5s for indexing

        logger.info(
            f"⚡ Waiting {wait_seconds}s before first payment for sub {subscription.id} "
            f"to pass the safe_start_time buffer (onchain_id={subscription.onchain_subscription_id})"
        )
        await asyncio.sleep(wait_seconds)
        try:
            pay_result = await relayer.execute_payment(
                chain=subscription.chain,
                onchain_subscription_id=subscription.onchain_subscription_id,
                db=self.db,
                subscription_id=subscription.id,
            )

            if pay_result.get("status") == "confirmed":
                subscription.status = Web3SubscriptionStatus.ACTIVE
                subscription.total_payments = 1
                subscription.total_amount_collected = subscription.amount
                subscription.next_payment_at = datetime.utcnow() + timedelta(
                    seconds=subscription.interval_seconds
                )
                subscription.updated_at = datetime.utcnow()
                self.db.commit()
                logger.info(
                    f"✅ First payment confirmed for sub {subscription.id} | "
                    f"tx={pay_result.get('tx_hash', '')[:16]}... | status→ACTIVE"
                )
            else:
                subscription.status = Web3SubscriptionStatus.PAST_DUE
                subscription.failed_payment_count = 1
                subscription.updated_at = datetime.utcnow()
                self.db.commit()
                logger.warning(
                    f"⚠️  First payment reverted for sub {subscription.id} → PAST_DUE"
                )

        except Exception as e:
            logger.error(f"❌ First payment failed for sub {subscription.id}: {e}")
            try:
                subscription.status = Web3SubscriptionStatus.PAST_DUE
                subscription.failed_payment_count = 1
                subscription.updated_at = datetime.utcnow()
                self.db.commit()
            except Exception:
                pass



    # ============= CANCELLATION =============

    async def cancel_subscription(
        self,
        subscription_id: str,
        cancelled_by: str = "merchant",  # "merchant", "subscriber", "system"
        merchant_id: Optional[str] = None,
        subscriber_address: Optional[str] = None,
    ) -> Web3Subscription:
        """Cancel a Web3 subscription both on-chain and in DB"""
        sub = self.db.query(Web3Subscription).get(subscription_id)
        if not sub:
            raise ValueError("Subscription not found")

        if sub.status in (Web3SubscriptionStatus.CANCELLED, Web3SubscriptionStatus.EXPIRED):
            raise ValueError("Subscription already cancelled")

        # Authorization check
        if cancelled_by == "merchant" and str(sub.merchant_id) != str(merchant_id):
            raise ValueError("Not authorized")
        if cancelled_by == "subscriber":
            if not subscriber_address or sub.subscriber_address.lower() != subscriber_address.lower():
                raise ValueError("Not authorized")

        # Cancel on-chain
        if sub.onchain_subscription_id:
            try:
                result = await relayer.cancel_subscription_onchain(
                    chain=sub.chain,
                    onchain_subscription_id=sub.onchain_subscription_id,
                    db=self.db,
                    subscription_id=sub.id,
                )
                sub.cancelled_tx_hash = result.get("tx_hash")
            except Exception as e:
                logger.error(f"On-chain cancellation failed: {e}")
                # Still cancel in DB even if on-chain fails

        # Update DB
        sub.status = Web3SubscriptionStatus.CANCELLED
        sub.cancelled_at = datetime.utcnow()
        sub.updated_at = datetime.utcnow()

        # Revoke mandate
        if sub.mandate_id:
            mandate = self.db.query(SubscriptionMandate).get(sub.mandate_id)
            if mandate and mandate.status == MandateStatus.ACTIVE:
                mandate.status = MandateStatus.REVOKED
                mandate.revoked_at = datetime.utcnow()

        # Emit event
        try:
            event_service = EventService(self.db)
            event_service.create_event(
                event_type="subscription.cancelled",
                entity_type="web3_subscription",
                entity_id=str(sub.id),
                merchant_id=sub.merchant_id,
                payload={
                    "subscription_id": str(sub.id),
                    "cancelled_by": cancelled_by,
                    "subscriber": sub.subscriber_address,
                },
            )
        except Exception:
            pass

        self.db.commit()
        logger.info(f"✅ Subscription {subscription_id} cancelled by {cancelled_by}")
        return sub

    # ============= QUERIES =============

    def get_subscription(self, subscription_id: str) -> Optional[Web3Subscription]:
        """Get a subscription by ID"""
        return self.db.query(Web3Subscription).get(subscription_id)

    def list_merchant_subscriptions(
        self,
        merchant_id: str,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict:
        """List all Web3 subscriptions for a merchant with pagination"""
        query = self.db.query(Web3Subscription).filter(
            Web3Subscription.merchant_id == merchant_id
        )

        if status:
            query = query.filter(Web3Subscription.status == status)

        total = query.count()
        subs = (
            query.order_by(Web3Subscription.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        return {
            "subscriptions": subs,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def list_subscriber_subscriptions(
        self, subscriber_address: str
    ) -> List[Web3Subscription]:
        """List all subscriptions for a subscriber wallet"""
        return (
            self.db.query(Web3Subscription)
            .filter(
                Web3Subscription.subscriber_address == subscriber_address.lower()
            )
            .order_by(Web3Subscription.created_at.desc())
            .all()
        )

    def list_subscription_payments(
        self,
        subscription_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict:
        """List payments for a subscription"""
        query = self.db.query(Web3SubscriptionPayment).filter(
            Web3SubscriptionPayment.subscription_id == subscription_id
        )

        total = query.count()
        payments = (
            query.order_by(Web3SubscriptionPayment.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        return {
            "payments": payments,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    # ============= ANALYTICS =============

    def get_merchant_analytics(self, merchant_id: str) -> Dict:
        """Get Web3 subscription analytics for a merchant"""
        # Active subscriptions
        active_count = (
            self.db.query(func.count(Web3Subscription.id))
            .filter(
                Web3Subscription.merchant_id == merchant_id,
                Web3Subscription.status == Web3SubscriptionStatus.ACTIVE,
            )
            .scalar()
        )

        # Total revenue
        total_revenue = (
            self.db.query(func.sum(Web3Subscription.total_amount_collected))
            .filter(Web3Subscription.merchant_id == merchant_id)
            .scalar()
        ) or 0

        # MRR (Monthly Recurring Revenue)
        monthly_subs = (
            self.db.query(Web3Subscription)
            .filter(
                Web3Subscription.merchant_id == merchant_id,
                Web3Subscription.status == Web3SubscriptionStatus.ACTIVE,
            )
            .all()
        )
        mrr = sum(
            float(s.amount) * (2592000 / s.interval_seconds)
            for s in monthly_subs
        )

        # Churn (cancelled in last 30 days)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        churned = (
            self.db.query(func.count(Web3Subscription.id))
            .filter(
                Web3Subscription.merchant_id == merchant_id,
                Web3Subscription.status == Web3SubscriptionStatus.CANCELLED,
                Web3Subscription.cancelled_at >= thirty_days_ago,
            )
            .scalar()
        )

        # Past due
        past_due = (
            self.db.query(func.count(Web3Subscription.id))
            .filter(
                Web3Subscription.merchant_id == merchant_id,
                Web3Subscription.status == Web3SubscriptionStatus.PAST_DUE,
            )
            .scalar()
        )

        return {
            "active_subscriptions": active_count,
            "past_due_subscriptions": past_due,
            "churned_last_30d": churned,
            "total_revenue": str(total_revenue),
            "mrr": round(mrr, 2),
        }

    # ============= HEALTH CHECK =============

    def check_subscription_health(self, subscription_id: str) -> Dict:
        """
        Verify on-chain state matches DB state for a subscription.
        Useful for detecting drift or inconsistencies.
        """
        sub = self.db.query(Web3Subscription).get(subscription_id)
        if not sub or not sub.onchain_subscription_id:
            return {"error": "Subscription not found or no on-chain ID"}

        try:
            onchain = relayer.get_onchain_subscription(
                sub.chain, sub.onchain_subscription_id
            )
            
            db_active = sub.status in (
                Web3SubscriptionStatus.ACTIVE,
                Web3SubscriptionStatus.PAST_DUE,
            )

            return {
                "subscription_id": str(sub.id),
                "db_active": db_active,
                "onchain_active": onchain["active"],
                "state_match": db_active == onchain["active"],
                "db_amount": str(sub.amount),
                "onchain_amount": str(onchain["amount"]),
                "onchain_payment_count": onchain["paymentCount"],
                "db_payment_count": sub.total_payments,
            }
        except Exception as e:
            return {"error": str(e)}
