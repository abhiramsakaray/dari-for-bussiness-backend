"""
Subscription Payment Scheduler

Cron-based scheduler that runs every 60 seconds (configurable) to detect
and execute due Web3 subscription payments.

Key design decisions:
  - Batch-processes subscriptions with LIMIT for scalability at 100k+ scale
  - Uses composite DB index (next_payment_at, status) for O(log n) lookups
  - Groups by chain for efficient relayer batching
  - Retry window: 12h intervals for 3 days (6 attempts) before marking FAILED
  - State transitions: ACTIVE → PAST_DUE → PAUSED
  - Emits webhook events at each state transition
  - Multi-chain dispatch: EVM → GaslessRelayer, Tron → TronRelayer,
    Solana → SolanaRelayer, Stellar → SorobanRelayer
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.core.database import SessionLocal
from app.models.models import (
    Web3Subscription, Web3SubscriptionPayment, Web3SubscriptionStatus,
    PaymentStatus, Merchant,
)
from app.services.gasless_relayer import relayer as evm_relayer
from app.services.tron_relayer import tron_relayer
from app.services.solana_relayer import solana_relayer
from app.services.soroban_relayer import soroban_relayer
from app.services.event_queue import EventService
from app.core.config import settings

logger = logging.getLogger(__name__)

# Chains handled by the EVM GaslessRelayer
EVM_CHAINS = {"ethereum", "polygon", "base", "bsc", "arbitrum"}


class SubscriptionScheduler:
    """
    Cron-based scheduler for Web3 subscription payment execution.
    
    Runs as an asyncio background task, scanning for due payments
    and triggering the correct chain-specific relayer to execute
    them on-chain.

    Chain dispatch:
      - EVM chains (ethereum, polygon, base, bsc, arbitrum) → GaslessRelayer
      - tron → TronRelayer
      - solana → SolanaRelayer
      - stellar → SorobanRelayer
    """

    def __init__(self):
        self.is_running = False
        self._task = None
        self.interval_seconds = 60  # run every 60 seconds
        self.batch_size = 100  # process up to 100 subscriptions per cycle
        self.stats = {
            "total_cycles": 0,
            "total_payments_executed": 0,
            "total_payments_failed": 0,
            "last_run": None,
            "last_error": None,
        }

    async def start(self):
        """Start the scheduler loop"""
        if self.is_running:
            logger.warning("Scheduler already running")
            return

        self.is_running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            f"✅ Subscription scheduler started "
            f"(interval={self.interval_seconds}s, batch={self.batch_size})"
        )

    async def stop(self):
        """Stop the scheduler loop"""
        self.is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("🛑 Subscription scheduler stopped")

    async def _run_loop(self):
        """Main scheduler loop"""
        while self.is_running:
            try:
                await self._process_cycle()
            except Exception as e:
                logger.error(f"Scheduler cycle error: {e}", exc_info=True)
                self.stats["last_error"] = str(e)

            await asyncio.sleep(self.interval_seconds)

    async def _process_cycle(self):
        """Process one scheduler cycle"""
        self.stats["total_cycles"] += 1
        self.stats["last_run"] = datetime.utcnow().isoformat()

        db = SessionLocal()
        try:
            # Query due subscriptions using the optimized composite index
            due_subs = (
                db.query(Web3Subscription)
                .filter(
                    Web3Subscription.next_payment_at <= datetime.utcnow(),
                    Web3Subscription.status.in_([
                        Web3SubscriptionStatus.ACTIVE,
                        Web3SubscriptionStatus.PAST_DUE,
                        Web3SubscriptionStatus.PENDING_PAYMENT,
                    ]),
                )
                .order_by(Web3Subscription.next_payment_at.asc())
                .limit(self.batch_size)
                .all()
            )

            if not due_subs:
                return

            logger.info(
                f"📋 Scheduler cycle #{self.stats['total_cycles']}: "
                f"found {len(due_subs)} due subscription(s)"
            )

            # Group by chain for efficient batching
            by_chain: Dict[str, List[Web3Subscription]] = {}
            for sub in due_subs:
                by_chain.setdefault(sub.chain, []).append(sub)

            # Process each chain batch
            for chain, subs in by_chain.items():
                for sub in subs:
                    await self._execute_subscription_payment(db, sub)

        except Exception as e:
            logger.error(f"Cycle processing error: {e}", exc_info=True)
            db.rollback()
        finally:
            db.close()

    async def _dispatch_execute_payment(
        self, db: Session, sub: Web3Subscription
    ) -> Dict:
        """
        Route execute_payment to the correct chain-specific relayer.

        All relayers return the same dict shape:
            {"tx_hash": str, "status": "confirmed"|"reverted", "gas_used": int, "block_number": int|None}
        """
        chain = sub.chain

        if chain in EVM_CHAINS:
            # EVM chains use the original GaslessRelayer
            return await evm_relayer.execute_payment(
                chain=chain,
                onchain_subscription_id=sub.onchain_subscription_id,
                db=db,
                subscription_id=sub.id,
            )

        elif chain == "tron":
            return await tron_relayer.execute_payment(
                onchain_subscription_id=sub.onchain_subscription_id,
                db=db,
                subscription_id=sub.id,
            )

        elif chain == "solana":
            # Solana requires additional account info from the subscription metadata
            # The subscriber_address, token_address, and merchant_address are stored
            # in the Web3Subscription model. ATAs must be derived or stored.
            metadata = sub.subscription_metadata if hasattr(sub, 'subscription_metadata') else None
            subscriber_ata = (metadata or {}).get("subscriber_token_account", "")
            merchant_ata = (metadata or {}).get("merchant_token_account", "")

            if not subscriber_ata or not merchant_ata:
                raise RuntimeError(
                    f"Solana subscription {sub.id} missing ATA metadata "
                    f"(subscriber_token_account / merchant_token_account)"
                )

            return await solana_relayer.execute_payment(
                onchain_subscription_id=sub.onchain_subscription_id,
                subscriber=sub.subscriber_address,
                mint=sub.token_address,
                subscriber_token_account=subscriber_ata,
                merchant_token_account=merchant_ata,
                db=db,
                subscription_id=sub.id,
            )

        elif chain == "stellar":
            return await soroban_relayer.execute_payment(
                onchain_subscription_id=sub.onchain_subscription_id,
                db=db,
                subscription_id=sub.id,
            )

        else:
            raise ValueError(f"Unsupported chain for subscription execution: {chain}")

    async def _execute_subscription_payment(
        self, db: Session, sub: Web3Subscription
    ):
        """
        Execute a single subscription payment via the appropriate relayer.
        
        Handles success, failure, retry logic, and state transitions.
        Uses the exact same logic across all chains.
        """
        if not sub.onchain_subscription_id:
            logger.warning(f"Subscription {sub.id} has no on-chain ID, skipping")
            return

        # Use next_payment_at for all scheduling, so no separate next_retry_at check is needed.

        # Create payment record
        payment = Web3SubscriptionPayment(
            subscription_id=sub.id,
            amount=sub.amount,
            token_symbol=sub.token_symbol,
            chain=sub.chain,
            payment_number=sub.total_payments + 1,
            period_start=sub.next_payment_at,
            period_end=sub.next_payment_at + timedelta(seconds=sub.interval_seconds),
            status=PaymentStatus.PENDING,
        )
        db.add(payment)
        db.flush()

        try:
            # Dispatch to the correct chain-specific relayer
            result = await self._dispatch_execute_payment(db, sub)

            if result["status"] == "confirmed":
                # ✅ Payment succeeded
                payment.status = PaymentStatus.PAID
                payment.tx_hash = result["tx_hash"]
                payment.block_number = result.get("block_number")
                payment.gas_used = result.get("gas_used")
                payment.confirmed_at = datetime.utcnow()

                # Update subscription
                sub.total_payments += 1
                sub.total_amount_collected += sub.amount
                # Mirror on-chain logic: contract sets nextPayment = block.timestamp + interval
                # Using utcnow() + interval instead of old next_payment_at + interval
                # prevents re-triggering when the subscription was overdue.
                sub.next_payment_at = datetime.utcnow() + timedelta(
                    seconds=sub.interval_seconds
                )
                sub.status = Web3SubscriptionStatus.ACTIVE
                sub.failed_payment_count = 0
                sub.first_failed_at = None  # Reset failure tracking on success
                sub.updated_at = datetime.utcnow()

                self.stats["total_payments_executed"] += 1
                logger.info(
                    f"✅ Payment #{payment.payment_number} executed for sub {sub.id} "
                    f"on {sub.chain} | tx={result['tx_hash'][:16]}..."
                )

                # Emit event for webhooks
                try:
                    event_service = EventService(db)
                    event_service.create_event(
                        event_type="subscription.payment_executed",
                        entity_type="web3_subscription",
                        entity_id=str(sub.id),
                        merchant_id=sub.merchant_id,
                        payload={
                            "subscription_id": str(sub.id),
                            "payment_number": payment.payment_number,
                            "amount": str(sub.amount),
                            "token": sub.token_symbol,
                            "chain": sub.chain,
                            "tx_hash": result["tx_hash"],
                        },
                    )
                except Exception as e:
                    logger.warning(f"Event emission failed: {e}")

            else:
                # ❌ Transaction reverted
                self._handle_payment_failure(db, sub, payment, "Transaction reverted")

        except Exception as e:
            # ❌ Relayer error
            self._handle_payment_failure(db, sub, payment, str(e))
            self.stats["total_payments_failed"] += 1

        db.commit()

    def _handle_payment_failure(
        self,
        db: Session,
        sub: Web3Subscription,
        payment: Web3SubscriptionPayment,
        error: str,
    ):
        """Handle a failed payment with grace period + retry logic"""
        payment.status = PaymentStatus.FAILED
        payment.error_message = error[:500]  # Store error details for debugging
        sub.failed_payment_count += 1

        # Track first failure timestamp
        if sub.first_failed_at is None:
            sub.first_failed_at = datetime.utcnow()

        retry_interval_hours = max(
            1, int(getattr(settings, "SCHEDULER_RETRY_INTERVAL_HOURS", 12))
        )

        # Determine effective grace period: sub-level setting, then global fallback
        grace_period_days = (
            sub.grace_period_days
            if sub.grace_period_days is not None
            else int(getattr(settings, "SCHEDULER_GRACE_PERIOD_DAYS", 3))
        )
        grace_period_hours = grace_period_days * 24

        # How long has this subscription been past due?
        first_failure_at = sub.first_failed_at or datetime.utcnow()
        hours_past_due = (datetime.utcnow() - first_failure_at).total_seconds() / 3600

        if hours_past_due >= grace_period_hours:
            # Grace period exceeded → PAUSED (merchant can resume later)
            sub.status = Web3SubscriptionStatus.PAUSED
            sub.paused_at = datetime.utcnow()
            logger.warning(
                f"⏸️  Subscription {sub.id} PAUSED — grace period of "
                f"{grace_period_days}d exceeded (past due {hours_past_due:.1f}h)"
            )

            try:
                from app.services.event_queue import EventService
                event_service = EventService(db)
                event_service.create_event(
                    event_type="subscription.paused",
                    entity_type="web3_subscription",
                    entity_id=str(sub.id),
                    merchant_id=sub.merchant_id,
                    payload={
                        "subscription_id": str(sub.id),
                        "reason": "grace_period_exceeded",
                        "grace_period_days": grace_period_days,
                        "hours_past_due": round(hours_past_due, 1),
                        "error": error[:200],
                    },
                )
            except Exception:
                pass

        else:
            # Still within grace period — retry after retry_interval_hours
            sub.status = Web3SubscriptionStatus.PAST_DUE
            sub.next_payment_at = datetime.utcnow() + timedelta(hours=retry_interval_hours)
            logger.warning(
                f"⚠️  Payment failed for sub {sub.id} "
                f"(attempt {sub.failed_payment_count}, grace {grace_period_days}d, "
                f"past due {hours_past_due:.1f}h), retry in {retry_interval_hours}h"
            )

        sub.updated_at = datetime.utcnow()

    def get_status(self) -> Dict:
        """Get scheduler status and stats"""
        return {
            "is_running": self.is_running,
            "interval_seconds": self.interval_seconds,
            "batch_size": self.batch_size,
            **self.stats,
        }


# Singleton instance
scheduler = SubscriptionScheduler()
