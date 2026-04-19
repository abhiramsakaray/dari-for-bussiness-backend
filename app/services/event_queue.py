"""
Event Queue Service
Async event processing for webhooks and notifications
"""
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import json
import asyncio
import logging
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models.models import Event, WebhookDelivery, Merchant
from app.core.database import get_db

logger = logging.getLogger(__name__)


# Event types
class EventTypes:
    # Payments
    PAYMENT_CREATED = "payment.created"
    PAYMENT_PENDING = "payment.pending"
    PAYMENT_CONFIRMED = "payment.confirmed"
    PAYMENT_FAILED = "payment.failed"
    PAYMENT_EXPIRED = "payment.expired"
    
    # Invoices
    INVOICE_CREATED = "invoice.created"
    INVOICE_SENT = "invoice.sent"
    INVOICE_VIEWED = "invoice.viewed"
    INVOICE_PAID = "invoice.paid"
    INVOICE_OVERDUE = "invoice.overdue"
    INVOICE_CANCELLED = "invoice.cancelled"
    
    # Subscriptions
    SUBSCRIPTION_CREATED = "subscription.created"
    SUBSCRIPTION_PLAN_VIEWED = "subscription.plan_viewed"
    SUBSCRIPTION_PLAN_SELECTED = "subscription.plan_selected"
    SUBSCRIPTION_APPROVED = "subscription.approved"
    SUBSCRIPTION_AUTHORIZATION_COMPLETED = "subscription.authorization_completed"
    SUBSCRIPTION_AUTHORIZATION_REJECTED = "subscription.authorization_rejected"
    SUBSCRIPTION_ACTIVATED = "subscription.activated"
    SUBSCRIPTION_RENEWED = "subscription.renewed"
    SUBSCRIPTION_PAUSED = "subscription.paused"
    SUBSCRIPTION_RESUMED = "subscription.resumed"
    SUBSCRIPTION_CANCELLED = "subscription.cancelled"
    SUBSCRIPTION_PAYMENT_FAILED = "subscription.payment_failed"
    
    # Refunds
    REFUND_CREATED = "refund.created"
    REFUND_PROCESSING = "refund.processing"
    REFUND_COMPLETED = "refund.completed"
    REFUND_FAILED = "refund.failed"
    
    # Webhooks
    WEBHOOK_DELIVERED = "webhook.delivered"
    WEBHOOK_FAILED = "webhook.failed"


class EventService:
    """Service for managing the event queue"""
    
    MAX_RETRIES = 5
    RETRY_DELAYS = [60, 300, 900, 3600, 7200]  # Seconds: 1m, 5m, 15m, 1h, 2h
    
    def __init__(self, db: Session):
        self.db = db
    
    def create_event(
        self,
        event_type: str,
        entity_type: str,
        entity_id: str,
        payload: Dict[str, Any],
        merchant_id: Optional[str] = None,
        scheduled_for: Optional[datetime] = None
    ) -> Event:
        """
        Create a new event in the queue.
        
        Args:
            event_type: Type of event (e.g., payment.confirmed)
            entity_type: Type of entity (e.g., payment, invoice)
            entity_id: ID of the entity
            payload: Event payload data
            merchant_id: Associated merchant ID (string, will be converted to UUID)
            scheduled_for: Future time to process (for delayed events)
        
        Returns:
            Created Event object
        """
        import uuid
        # Convert merchant_id string to UUID if provided
        merchant_uuid = uuid.UUID(merchant_id) if merchant_id and isinstance(merchant_id, str) else merchant_id
        
        event = Event(
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload,
            merchant_id=merchant_uuid,
            status="pending",
            scheduled_for=scheduled_for
        )
        
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        
        logger.info(f"Created event {event.id}: {event_type} for {entity_type}:{entity_id}")
        
        return event
    
    def get_pending_events(self, limit: int = 100) -> List[Event]:
        """Get pending events ready for processing"""
        now = datetime.utcnow()
        
        events = self.db.query(Event).filter(
            and_(
                Event.status == "pending",
                Event.attempts < self.MAX_RETRIES,
                # Not scheduled for future
                (Event.scheduled_for.is_(None)) | (Event.scheduled_for <= now)
            )
        ).order_by(Event.created_at).limit(limit).all()
        
        return events
    
    def mark_processing(self, event_id: str) -> bool:
        """Mark an event as being processed"""
        event = self.db.query(Event).filter(Event.id == event_id).first()
        
        if not event or event.status != "pending":
            return False
        
        event.status = "processing"
        event.attempts += 1
        event.last_attempt = datetime.utcnow()
        self.db.commit()
        
        return True
    
    def mark_completed(self, event_id: str) -> bool:
        """Mark an event as successfully processed"""
        event = self.db.query(Event).filter(Event.id == event_id).first()
        
        if not event:
            return False
        
        event.status = "completed"
        event.processed_at = datetime.utcnow()
        self.db.commit()
        
        logger.info(f"Event {event_id} completed successfully")
        
        return True
    
    def mark_failed(self, event_id: str, error_message: str) -> bool:
        """Mark an event as failed"""
        event = self.db.query(Event).filter(Event.id == event_id).first()
        
        if not event:
            return False
        
        event.error_message = error_message
        
        if event.attempts >= self.MAX_RETRIES:
            event.status = "failed"
            logger.error(f"Event {event_id} failed permanently after {event.attempts} attempts")
        else:
            event.status = "pending"
            # Schedule retry
            delay = self.RETRY_DELAYS[min(event.attempts - 1, len(self.RETRY_DELAYS) - 1)]
            event.scheduled_for = datetime.utcnow() + timedelta(seconds=delay)
            logger.warning(f"Event {event_id} failed, will retry in {delay}s")
        
        self.db.commit()
        
        return True
    
    def get_event(self, event_id: str) -> Optional[Event]:
        """Get an event by ID"""
        return self.db.query(Event).filter(Event.id == event_id).first()
    
    def list_events(
        self,
        merchant_id: Optional[str] = None,
        event_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Event]:
        """List events with optional filters"""
        query = self.db.query(Event)
        
        if merchant_id:
            query = query.filter(Event.merchant_id == merchant_id)
        if event_type:
            query = query.filter(Event.event_type == event_type)
        if status:
            query = query.filter(Event.status == status)
        
        return query.order_by(Event.created_at.desc()).offset(offset).limit(limit).all()


class WebhookDeliveryService:
    """Service for managing webhook deliveries"""
    
    MAX_RETRIES = 5
    RETRY_DELAYS = [60, 300, 900, 3600, 7200]  # Exponential backoff
    
    def __init__(self, db: Session):
        self.db = db
    
    def create_delivery(
        self,
        merchant_id: str,
        event_id: str,
        url: str,
        event_type: str,
        payload: Dict[str, Any]
    ) -> WebhookDelivery:
        """Create a new webhook delivery"""
        delivery = WebhookDelivery(
            merchant_id=merchant_id,
            event_id=event_id,
            url=url,
            event_type=event_type,
            payload=payload,
            status="pending",
            attempt_count=0
        )
        
        self.db.add(delivery)
        self.db.commit()
        self.db.refresh(delivery)
        
        return delivery
    
    def get_pending_deliveries(self, limit: int = 100) -> List[WebhookDelivery]:
        """Get pending webhook deliveries"""
        now = datetime.utcnow()
        
        deliveries = self.db.query(WebhookDelivery).filter(
            and_(
                WebhookDelivery.status == "pending",
                WebhookDelivery.attempt_count < self.MAX_RETRIES,
                (WebhookDelivery.next_retry.is_(None)) | (WebhookDelivery.next_retry <= now)
            )
        ).order_by(WebhookDelivery.created_at).limit(limit).all()
        
        return deliveries
    
    def mark_delivered(
        self,
        delivery_id: str,
        http_status: int,
        response_body: Optional[str] = None
    ) -> bool:
        """Mark a webhook as successfully delivered"""
        delivery = self.db.query(WebhookDelivery).filter(
            WebhookDelivery.id == delivery_id
        ).first()
        
        if not delivery:
            return False
        
        delivery.status = "success"
        delivery.http_status = http_status
        delivery.response_body = response_body
        delivery.delivered_at = datetime.utcnow()
        delivery.attempt_count += 1
        
        self.db.commit()
        
        logger.info(f"Webhook {delivery_id} delivered successfully")
        
        return True
    
    def mark_failed(
        self,
        delivery_id: str,
        http_status: Optional[int] = None,
        response_body: Optional[str] = None
    ) -> bool:
        """Mark a webhook delivery as failed"""
        delivery = self.db.query(WebhookDelivery).filter(
            WebhookDelivery.id == delivery_id
        ).first()
        
        if not delivery:
            return False
        
        delivery.http_status = http_status
        delivery.response_body = response_body
        delivery.attempt_count += 1
        
        if delivery.attempt_count >= self.MAX_RETRIES:
            delivery.status = "failed"
            logger.error(f"Webhook {delivery_id} failed permanently")
        else:
            # Schedule retry
            delay = self.RETRY_DELAYS[min(delivery.attempt_count - 1, len(self.RETRY_DELAYS) - 1)]
            delivery.next_retry = datetime.utcnow() + timedelta(seconds=delay)
            logger.warning(f"Webhook {delivery_id} failed, will retry in {delay}s")
        
        self.db.commit()
        
        return True
    
    def list_deliveries(
        self,
        merchant_id: str,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[WebhookDelivery]:
        """List webhook deliveries for a merchant"""
        query = self.db.query(WebhookDelivery).filter(
            WebhookDelivery.merchant_id == merchant_id
        )
        
        if status:
            query = query.filter(WebhookDelivery.status == status)
        
        return query.order_by(WebhookDelivery.created_at.desc()).offset(offset).limit(limit).all()


# Helper functions for creating events

def emit_payment_event(
    db: Session,
    event_type: str,
    payment_session,
    extra_data: Optional[Dict] = None
):
    """Emit a payment-related event"""
    payload = {
        "session_id": payment_session.id,
        "amount_fiat": str(payment_session.amount_fiat),
        "currency": payment_session.fiat_currency,
        "status": payment_session.status.value if hasattr(payment_session.status, 'value') else payment_session.status,
        "token": payment_session.token,
        "chain": payment_session.chain,
        "tx_hash": payment_session.tx_hash,
        "merchant_id": str(payment_session.merchant_id),
        "order_id": payment_session.order_id,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    if extra_data:
        payload.update(extra_data)
    
    service = EventService(db)
    return service.create_event(
        event_type=event_type,
        entity_type="payment",
        entity_id=payment_session.id,
        payload=payload,
        merchant_id=str(payment_session.merchant_id)
    )


def emit_invoice_event(
    db: Session,
    event_type: str,
    invoice,
    extra_data: Optional[Dict] = None
):
    """Emit an invoice-related event"""
    payload = {
        "invoice_id": invoice.id,
        "invoice_number": invoice.invoice_number,
        "customer_email": invoice.customer_email,
        "total": str(invoice.total),
        "currency": invoice.fiat_currency,
        "status": invoice.status.value if hasattr(invoice.status, 'value') else invoice.status,
        "due_date": invoice.due_date.isoformat(),
        "merchant_id": str(invoice.merchant_id),
        "timestamp": datetime.utcnow().isoformat()
    }
    
    if extra_data:
        payload.update(extra_data)
    
    service = EventService(db)
    return service.create_event(
        event_type=event_type,
        entity_type="invoice",
        entity_id=invoice.id,
        payload=payload,
        merchant_id=str(invoice.merchant_id)
    )


def emit_subscription_event(
    db: Session,
    event_type: str,
    subscription,
    extra_data: Optional[Dict] = None
):
    """Emit a subscription-related event"""
    payload = {
        "subscription_id": subscription.id,
        "plan_id": subscription.plan_id,
        "customer_email": subscription.customer_email,
        "status": subscription.status.value if hasattr(subscription.status, 'value') else subscription.status,
        "current_period_end": subscription.current_period_end.isoformat(),
        "merchant_id": str(subscription.merchant_id),
        "timestamp": datetime.utcnow().isoformat()
    }
    
    if extra_data:
        payload.update(extra_data)
    
    service = EventService(db)
    return service.create_event(
        event_type=event_type,
        entity_type="subscription",
        entity_id=subscription.id,
        payload=payload,
        merchant_id=str(subscription.merchant_id)
    )


def emit_refund_event(
    db: Session,
    event_type: str,
    refund,
    extra_data: Optional[Dict] = None
):
    """Emit a refund-related event"""
    payload = {
        "refund_id": refund.id,
        "payment_session_id": refund.payment_session_id,
        "amount": str(refund.amount),
        "token": refund.token,
        "chain": refund.chain,
        "status": refund.status.value if hasattr(refund.status, 'value') else refund.status,
        "merchant_id": str(refund.merchant_id),
        "timestamp": datetime.utcnow().isoformat()
    }
    
    if extra_data:
        payload.update(extra_data)
    
    service = EventService(db)
    return service.create_event(
        event_type=event_type,
        entity_type="refund",
        entity_id=refund.id,
        payload=payload,
        merchant_id=str(refund.merchant_id)
    )
