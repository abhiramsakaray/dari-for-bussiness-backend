"""
Subscription Payment Scheduler

Cron-based scheduler that runs every 60 seconds (configurable) to detect
and execute due Web3 subscription payments.

Key design decisions:
  - Batch-processes subscriptions with LIMIT for scalability at 100k+ scale
  - Uses composite DB index (next_payment_at, status) for O(log n) lookups
  - Groups by chain for efficient relayer batching
  - Retry window: 12h intervals for 3 days (6 attempts) before marking FAILED
  - State transitions: ACTIVE → PAST_DUE → FAILED
  - Emits webhook events at each state transition
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
from app.services.gasless_relayer import relayer
from app.services.event_queue import EventService

logger = logging.getLogger(__name__)


class SubscriptionScheduler:
    """
    Cron-based scheduler for Web3 subscription payment execution.
    
    Runs as an asyncio background task, scanning for due payments
    and triggering the gasless relayer to execute them on-chain.
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
                    or_(
                        Web3Subscription.status == Web3SubscriptionStatus.ACTIVE,
                        Web3Subscription.status == Web3SubscriptionStatus.PAST_DUE,
                    ),
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

    async def _execute_subscription_payment(
        self, db: Session, sub: Web3Subscription
    ):
        """
        Execute a single subscription payment via the relayer.
        
        Handles success, failure, retry logic, and state transitions.
        """
        if not sub.onchain_subscription_id:
            logger.warning(f"Subscription {sub.id} has no on-chain ID, skipping")
            return

        # Check if this is a retry and if we should retry yet
        if sub.status == Web3SubscriptionStatus.PAST_DUE:
            if sub.next_retry_at and datetime.utcnow() < sub.next_retry_at:
                return  # Not time to retry yet

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
            # Execute payment via relayer
            result = await relayer.execute_payment(
                chain=sub.chain,
                onchain_subscription_id=sub.onchain_subscription_id,
                db=db,
                subscription_id=sub.id,
            )

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
                sub.next_payment_at = sub.next_payment_at + timedelta(
                    seconds=sub.interval_seconds
                )
                sub.status = Web3SubscriptionStatus.ACTIVE
                sub.failed_payment_count = 0
                sub.last_retry_at = None
                sub.next_retry_at = None
                sub.updated_at = datetime.utcnow()

                self.stats["total_payments_executed"] += 1
                logger.info(
                    f"✅ Payment #{payment.payment_number} executed for sub {sub.id} "
                    f"| tx={result['tx_hash'][:16]}..."
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
        """Handle a failed payment with retry logic"""
        payment.status = PaymentStatus.FAILED
        payment.failed_at = datetime.utcnow()

        sub.failed_payment_count += 1
        sub.last_retry_at = datetime.utcnow()

        if sub.failed_payment_count >= sub.max_retries:
            # Max retries exceeded → mark as FAILED
            sub.status = Web3SubscriptionStatus.FAILED
            sub.next_retry_at = None
            logger.error(
                f"❌ Subscription {sub.id} FAILED after {sub.failed_payment_count} retries"
            )

            # Emit failure event
            try:
                event_service = EventService(db)
                event_service.create_event(
                    event_type="subscription.failed",
                    entity_type="web3_subscription",
                    entity_id=str(sub.id),
                    merchant_id=sub.merchant_id,
                    payload={
                        "subscription_id": str(sub.id),
                        "failed_count": sub.failed_payment_count,
                        "error": error[:200],
                    },
                )
            except Exception:
                pass

        else:
            # Schedule retry
            sub.status = Web3SubscriptionStatus.PAST_DUE
            sub.next_retry_at = datetime.utcnow() + timedelta(
                hours=sub.retry_interval_hours
            )
            logger.warning(
                f"⚠️  Payment failed for sub {sub.id} "
                f"(attempt {sub.failed_payment_count}/{sub.max_retries}), "
                f"retry at {sub.next_retry_at}"
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
