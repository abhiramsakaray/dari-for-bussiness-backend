"""
Subscription Billing Service

Handles the recurring payment lifecycle:
- Trial expiration and conversion to paid
- Payment collection for due subscriptions
- Failed payment retries and grace periods
- Subscription status management (past_due, cancelled)
- Trial ending reminders

This service should be called periodically (e.g., via cron job or background task)
to process all due subscriptions.
"""
import logging
import secrets
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Any

from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models.models import (
    Subscription, SubscriptionPlan, SubscriptionPayment,
    PaymentSession, Merchant, MerchantWallet,
    SubscriptionStatus, PaymentStatus
)
from app.services.event_queue import EventService, EventTypes

logger = logging.getLogger(__name__)


def calculate_next_billing_date(current_date: datetime, interval: str, interval_count: int = 1) -> datetime:
    """Calculate the next billing date based on interval."""
    if interval == "daily":
        return current_date + timedelta(days=interval_count)
    elif interval == "weekly":
        return current_date + timedelta(weeks=interval_count)
    elif interval == "monthly":
        return current_date + timedelta(days=30 * interval_count)
    elif interval == "quarterly":
        return current_date + timedelta(days=90 * interval_count)
    elif interval == "yearly":
        return current_date + timedelta(days=365 * interval_count)
    return current_date + timedelta(days=30)


class SubscriptionBillingService:
    """Service for processing recurring subscription billing."""

    # Send trial ending reminder this many days before trial ends
    TRIAL_ENDING_REMINDER_DAYS = 3

    def __init__(self, db: Session):
        self.db = db
        self.event_service = EventService(db)

    def process_all(self) -> Dict[str, Any]:
        """
        Run all billing tasks. Call this periodically (e.g., every hour).
        
        Returns a summary of actions taken.
        """
        results = {
            "trials_converted": 0,
            "trial_reminders_sent": 0,
            "payments_created": 0,
            "subscriptions_past_due": 0,
            "subscriptions_cancelled": 0,
            "errors": []
        }

        try:
            self._process_trial_reminders(results)
        except Exception as e:
            logger.error(f"Error processing trial reminders: {e}", exc_info=True)
            results["errors"].append(f"trial_reminders: {str(e)}")

        try:
            self._process_trial_expirations(results)
        except Exception as e:
            logger.error(f"Error processing trial expirations: {e}", exc_info=True)
            results["errors"].append(f"trial_expirations: {str(e)}")

        try:
            self._process_due_payments(results)
        except Exception as e:
            logger.error(f"Error processing due payments: {e}", exc_info=True)
            results["errors"].append(f"due_payments: {str(e)}")

        try:
            self._process_failed_payments(results)
        except Exception as e:
            logger.error(f"Error processing failed payments: {e}", exc_info=True)
            results["errors"].append(f"failed_payments: {str(e)}")

        try:
            self._process_pending_cancellations(results)
        except Exception as e:
            logger.error(f"Error processing cancellations: {e}", exc_info=True)
            results["errors"].append(f"cancellations: {str(e)}")

        return results

    def _process_trial_reminders(self, results: Dict):
        """Send reminders for trials ending soon."""
        reminder_cutoff = datetime.utcnow() + timedelta(days=self.TRIAL_ENDING_REMINDER_DAYS)

        trials_ending = self.db.query(Subscription).filter(
            and_(
                Subscription.status == SubscriptionStatus.TRIALING,
                Subscription.trial_end <= reminder_cutoff,
                Subscription.trial_end > datetime.utcnow(),
                Subscription.trial_reminder_sent == False
            )
        ).all()

        for sub in trials_ending:
            try:
                sub.trial_reminder_sent = True
                self.event_service.create_event(
                    event_type=EventTypes.SUBSCRIPTION_PAYMENT_FAILED,  # Reuse; ideally add TRIAL_ENDING
                    entity_type="subscription",
                    entity_id=sub.id,
                    payload={
                        "subscription_id": sub.id,
                        "customer_email": sub.customer_email,
                        "trial_end": sub.trial_end.isoformat(),
                        "plan_name": sub.plan.name if sub.plan else "Unknown",
                        "amount": float(sub.plan.amount) if sub.plan else 0,
                        "event": "subscription.trial_ending"
                    },
                    merchant_id=str(sub.merchant_id)
                )
                results["trial_reminders_sent"] += 1
                logger.info(f"Trial ending reminder sent for subscription {sub.id}")
            except Exception as e:
                logger.error(f"Error sending trial reminder for {sub.id}: {e}")

        self.db.commit()

    def _process_trial_expirations(self, results: Dict):
        """Convert expired trials to active subscriptions."""
        expired_trials = self.db.query(Subscription).filter(
            and_(
                Subscription.status == SubscriptionStatus.TRIALING,
                Subscription.trial_end <= datetime.utcnow()
            )
        ).all()

        now = datetime.utcnow()

        for sub in expired_trials:
            try:
                plan = sub.plan
                if not plan:
                    logger.warning(f"Subscription {sub.id} has no plan, skipping")
                    continue

                interval_value = plan.interval.value if hasattr(plan.interval, 'value') else plan.interval

                # Convert trial to active
                sub.status = SubscriptionStatus.ACTIVE
                sub.trial_converted_at = now
                sub.current_period_start = now
                sub.current_period_end = calculate_next_billing_date(now, interval_value, plan.interval_count)
                sub.next_payment_at = now
                sub.updated_at = now

                # Create first payment record after trial
                payment = SubscriptionPayment(
                    subscription_id=sub.id,
                    period_start=sub.current_period_start,
                    period_end=sub.current_period_end,
                    amount=plan.amount,
                    fiat_currency=plan.fiat_currency,
                    status=PaymentStatus.CREATED
                )
                self.db.add(payment)

                self.event_service.create_event(
                    event_type=EventTypes.SUBSCRIPTION_ACTIVATED,
                    entity_type="subscription",
                    entity_id=sub.id,
                    payload={
                        "subscription_id": sub.id,
                        "customer_email": sub.customer_email,
                        "plan_name": plan.name,
                        "amount": float(plan.amount),
                        "event": "subscription.trial_converted"
                    },
                    merchant_id=str(sub.merchant_id)
                )

                results["trials_converted"] += 1
                logger.info(f"Trial converted to active for subscription {sub.id}")
            except Exception as e:
                logger.error(f"Error converting trial for {sub.id}: {e}")

        self.db.commit()

    def _process_due_payments(self, results: Dict):
        """Create payment sessions for subscriptions with due payments."""
        due_subscriptions = self.db.query(Subscription).filter(
            and_(
                Subscription.status == SubscriptionStatus.ACTIVE,
                Subscription.next_payment_at <= datetime.utcnow(),
                # Exclude subscriptions pending cancellation that have passed cancel_at
                ~and_(
                    Subscription.cancel_at.isnot(None),
                    Subscription.cancel_at <= datetime.utcnow()
                )
            )
        ).all()

        for sub in due_subscriptions:
            try:
                plan = sub.plan
                if not plan:
                    continue

                # Check max billing cycles
                if plan.max_billing_cycles and (sub.total_payments_collected or 0) >= plan.max_billing_cycles:
                    sub.status = SubscriptionStatus.CANCELLED
                    sub.cancelled_at = datetime.utcnow()
                    sub.cancel_reason = "Max billing cycles reached"
                    logger.info(f"Subscription {sub.id} completed max billing cycles")
                    continue

                # Check if there's already a pending payment for this period
                existing = self.db.query(SubscriptionPayment).filter(
                    and_(
                        SubscriptionPayment.subscription_id == sub.id,
                        SubscriptionPayment.period_start == sub.current_period_start,
                        SubscriptionPayment.status.in_([PaymentStatus.CREATED, PaymentStatus.PENDING])
                    )
                ).first()

                if existing:
                    continue

                # Create payment session
                session_id = f"pay_{secrets.token_urlsafe(12)}"
                
                # Find merchant wallet for the subscription's chain
                merchant_wallet_address = None
                if sub.customer_chain:
                    wallet = self.db.query(MerchantWallet).filter(
                        and_(
                            MerchantWallet.merchant_id == sub.merchant_id,
                            MerchantWallet.chain == sub.customer_chain,
                            MerchantWallet.is_active == True
                        )
                    ).first()
                    if wallet:
                        merchant_wallet_address = wallet.wallet_address

                payment_session = PaymentSession(
                    id=session_id,
                    merchant_id=sub.merchant_id,
                    amount_fiat=plan.amount,
                    fiat_currency=plan.fiat_currency,
                    amount_token=str(plan.amount),
                    amount_usdc=str(plan.amount),
                    token=sub.customer_token or (plan.accepted_tokens[0] if plan.accepted_tokens else "USDC"),
                    chain=sub.customer_chain or (plan.accepted_chains[0] if plan.accepted_chains else "stellar"),
                    accepted_tokens=plan.accepted_tokens,
                    accepted_chains=plan.accepted_chains,
                    merchant_wallet=merchant_wallet_address,
                    status=PaymentStatus.CREATED,
                    success_url="",
                    cancel_url="",
                    order_id=f"sub_{sub.id}_{sub.current_period_start.strftime('%Y%m%d')}",
                    session_metadata={
                        "subscription_id": sub.id,
                        "period_start": sub.current_period_start.isoformat(),
                        "period_end": sub.current_period_end.isoformat(),
                        "type": "subscription_payment"
                    },
                    expires_at=datetime.utcnow() + timedelta(hours=48),
                    collect_payer_data=False,
                    payer_email=sub.customer_email,
                    payer_name=sub.customer_name,
                )
                self.db.add(payment_session)

                sub_payment = SubscriptionPayment(
                    subscription_id=sub.id,
                    payment_session_id=session_id,
                    period_start=sub.current_period_start,
                    period_end=sub.current_period_end,
                    amount=plan.amount,
                    fiat_currency=plan.fiat_currency,
                    status=PaymentStatus.CREATED
                )
                self.db.add(sub_payment)

                results["payments_created"] += 1
                logger.info(f"Payment session {session_id} created for subscription {sub.id}")
            except Exception as e:
                logger.error(f"Error creating payment for subscription {sub.id}: {e}")

        self.db.commit()

    def _process_failed_payments(self, results: Dict):
        """Handle subscriptions with failed or expired payments."""
        # Find subscriptions with overdue payments (past grace period)
        active_subs = self.db.query(Subscription).filter(
            and_(
                Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.PAST_DUE]),
                Subscription.next_payment_at < datetime.utcnow()
            )
        ).all()

        for sub in active_subs:
            try:
                # Check if the latest payment for this period was paid
                latest_payment = self.db.query(SubscriptionPayment).filter(
                    and_(
                        SubscriptionPayment.subscription_id == sub.id,
                        SubscriptionPayment.period_start == sub.current_period_start
                    )
                ).order_by(SubscriptionPayment.created_at.desc()).first()

                if latest_payment and latest_payment.status == PaymentStatus.PAID:
                    continue  # Payment succeeded

                grace_days = sub.grace_period_days or 3
                max_retries = sub.max_payment_retries or 3
                days_overdue = (datetime.utcnow() - sub.next_payment_at).days

                if days_overdue > grace_days and sub.failed_payment_count >= max_retries:
                    # Cancel subscription after exhausting retries
                    sub.status = SubscriptionStatus.CANCELLED
                    sub.cancelled_at = datetime.utcnow()
                    sub.cancel_reason = f"Payment failed after {max_retries} attempts"
                    results["subscriptions_cancelled"] += 1

                    self.event_service.create_event(
                        event_type=EventTypes.SUBSCRIPTION_CANCELLED,
                        entity_type="subscription",
                        entity_id=sub.id,
                        payload={
                            "subscription_id": sub.id,
                            "customer_email": sub.customer_email,
                            "reason": "payment_failed",
                            "failed_attempts": sub.failed_payment_count,
                            "event": "subscription.cancelled"
                        },
                        merchant_id=str(sub.merchant_id)
                    )
                    logger.info(f"Subscription {sub.id} cancelled due to payment failure")
                elif days_overdue > 0:
                    # Mark as past due
                    if sub.status != SubscriptionStatus.PAST_DUE:
                        sub.status = SubscriptionStatus.PAST_DUE
                        results["subscriptions_past_due"] += 1

                    sub.failed_payment_count = (sub.failed_payment_count or 0) + 1

                    self.event_service.create_event(
                        event_type=EventTypes.SUBSCRIPTION_PAYMENT_FAILED,
                        entity_type="subscription",
                        entity_id=sub.id,
                        payload={
                            "subscription_id": sub.id,
                            "customer_email": sub.customer_email,
                            "attempt": sub.failed_payment_count,
                            "max_retries": max_retries,
                            "event": "subscription.payment_failed"
                        },
                        merchant_id=str(sub.merchant_id)
                    )
            except Exception as e:
                logger.error(f"Error processing failed payment for {sub.id}: {e}")

        self.db.commit()

    def _process_pending_cancellations(self, results: Dict):
        """Cancel subscriptions that have reached their cancel_at date."""
        pending = self.db.query(Subscription).filter(
            and_(
                Subscription.cancel_at.isnot(None),
                Subscription.cancel_at <= datetime.utcnow(),
                Subscription.status != SubscriptionStatus.CANCELLED
            )
        ).all()

        for sub in pending:
            sub.status = SubscriptionStatus.CANCELLED
            sub.updated_at = datetime.utcnow()
            results["subscriptions_cancelled"] += 1
            logger.info(f"Subscription {sub.id} cancelled at scheduled date")

        self.db.commit()

    def handle_payment_confirmed(self, payment_session_id: str):
        """
        Called when a payment session is confirmed (paid).
        
        Links the payment to the subscription and advances the billing cycle.
        This should be called by the blockchain listener when a subscription
        payment is detected.
        """
        payment_session = self.db.query(PaymentSession).filter(
            PaymentSession.id == payment_session_id
        ).first()

        if not payment_session or not payment_session.session_metadata:
            return

        metadata = payment_session.session_metadata
        if metadata.get("type") != "subscription_payment":
            return

        subscription_id = metadata.get("subscription_id")
        if not subscription_id:
            return

        sub = self.db.query(Subscription).filter(
            Subscription.id == subscription_id
        ).first()

        if not sub:
            logger.warning(f"Subscription {subscription_id} not found for payment {payment_session_id}")
            return

        plan = sub.plan
        if not plan:
            return

        # Update subscription payment record
        sub_payment = self.db.query(SubscriptionPayment).filter(
            SubscriptionPayment.payment_session_id == payment_session_id
        ).first()

        if sub_payment:
            sub_payment.status = PaymentStatus.PAID
            sub_payment.paid_at = datetime.utcnow()

        # Advance to next billing period
        now = datetime.utcnow()
        interval_value = plan.interval.value if hasattr(plan.interval, 'value') else plan.interval

        sub.last_payment_at = now
        sub.total_payments_collected = (sub.total_payments_collected or 0) + 1
        sub.total_revenue = Decimal(str(sub.total_revenue or 0)) + plan.amount
        sub.failed_payment_count = 0
        sub.status = SubscriptionStatus.ACTIVE
        sub.current_period_start = now
        sub.current_period_end = calculate_next_billing_date(now, interval_value, plan.interval_count)
        sub.next_payment_at = sub.current_period_end
        sub.updated_at = now

        self.event_service.create_event(
            event_type=EventTypes.SUBSCRIPTION_RENEWED,
            entity_type="subscription",
            entity_id=sub.id,
            payload={
                "subscription_id": sub.id,
                "customer_email": sub.customer_email,
                "plan_name": plan.name,
                "amount": float(plan.amount),
                "period_start": sub.current_period_start.isoformat(),
                "period_end": sub.current_period_end.isoformat(),
                "total_payments": sub.total_payments_collected,
                "event": "subscription.renewed"
            },
            merchant_id=str(sub.merchant_id)
        )

        self.db.commit()
        logger.info(
            f"Subscription {sub.id} renewed. Period: "
            f"{sub.current_period_start.isoformat()} - {sub.current_period_end.isoformat()}"
        )
