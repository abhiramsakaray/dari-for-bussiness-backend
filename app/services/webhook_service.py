import hashlib
import hmac
import httpx
import json
import logging
import time
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models import PaymentSession, Refund
from app.schemas import WebhookPayload

logger = logging.getLogger(__name__)


def _compute_webhook_signature(payload_bytes: bytes, secret: str) -> str:
    """
    Compute HMAC-SHA256 signature for webhook payload.

    Format: ``t=<unix_ts>,v1=<hex_digest>``
    The merchant verifies by recomputing HMAC(secret, "<timestamp>.<body>").
    """
    timestamp = str(int(time.time()))
    signed_payload = f"{timestamp}.".encode() + payload_bytes
    signature = hmac.new(
        secret.encode(),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()
    return f"t={timestamp},v1={signature}"


async def send_webhook(session: PaymentSession, db: Session, retry_count: int = 0):
    """
    Send webhook notification to merchant with HMAC-SHA256 signing.
    
    Args:
        session: Payment session that was completed
        db: Database session
        retry_count: Current retry attempt (0-indexed)
    """
    if not session.merchant.webhook_url:
        logger.warning(f"No webhook URL for merchant {session.merchant.id}")
        return
    
    # Prepare webhook payload with multi-chain support
    payload = WebhookPayload(
        event="payment.success",
        session_id=session.id,
        amount=session.amount_token or session.amount_usdc,
        currency=session.token or "USDC",
        tx_hash=session.tx_hash or "",
        chain=session.chain,
        token=session.token,
        block_number=session.block_number,
        confirmations=session.confirmations,
        timestamp=datetime.utcnow().isoformat() + "Z",
        # Dual currency
        payer_currency=session.payer_currency,
        payer_amount_local=float(session.payer_amount_local) if session.payer_amount_local else None,
        merchant_currency=session.merchant_currency,
        merchant_amount_local=float(session.merchant_amount_local) if session.merchant_amount_local else None,
        is_cross_border=session.is_cross_border or False,
    )
    
    webhook_url = session.merchant.webhook_url
    payload_bytes = json.dumps(payload.model_dump(), default=str).encode()

    # Build headers
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "DariForBusiness/2.2",
        "X-Webhook-Event": "payment.success",
        "X-Session-ID": session.id,
        "X-Chain": session.chain or "stellar",
        "X-Token": session.token or "USDC",
    }

    # Add HMAC signature if merchant has a webhook secret
    signing_secret = session.merchant.webhook_secret or settings.WEBHOOK_SIGNING_SECRET
    if signing_secret:
        headers["X-Payment-Signature"] = _compute_webhook_signature(
            payload_bytes, signing_secret
        )
    
    try:
        async with httpx.AsyncClient(timeout=settings.WEBHOOK_TIMEOUT_SECONDS) as client:
            response = await client.post(
                webhook_url,
                content=payload_bytes,
                headers=headers,
            )
            
            if response.status_code >= 200 and response.status_code < 300:
                logger.info(f"Webhook sent successfully to {webhook_url} for session {session.id}")
                
                # Auto-create invoice on successful payment
                try:
                    from app.services.invoice_service import create_invoice_from_payment
                    create_invoice_from_payment(session, db)
                except Exception as inv_err:
                    logger.error(f"Auto-invoice creation failed for {session.id}: {inv_err}")
            else:
                logger.warning(
                    f"Webhook returned non-2xx status {response.status_code} for session {session.id}"
                )
                
                if retry_count < settings.WEBHOOK_RETRY_LIMIT - 1:
                    logger.info(f"Retrying webhook (attempt {retry_count + 2}/{settings.WEBHOOK_RETRY_LIMIT})...")
                    await send_webhook(session, db, retry_count + 1)
                else:
                    logger.error(f"Webhook failed after {settings.WEBHOOK_RETRY_LIMIT} attempts for session {session.id}")
                    
    except httpx.TimeoutException:
        logger.error(f"Webhook timeout for {webhook_url} (session {session.id})")
        if retry_count < settings.WEBHOOK_RETRY_LIMIT - 1:
            await send_webhook(session, db, retry_count + 1)
        else:
            logger.error(f"Webhook failed after {settings.WEBHOOK_RETRY_LIMIT} attempts for session {session.id}")
            
    except Exception as e:
        logger.error(f"Webhook error for {webhook_url}: {e}")
        if retry_count < settings.WEBHOOK_RETRY_LIMIT - 1:
            await send_webhook(session, db, retry_count + 1)
        else:
            logger.error(f"Webhook failed after {settings.WEBHOOK_RETRY_LIMIT} attempts for session {session.id}")


def verify_webhook_signature(
    payload_body: bytes,
    signature_header: str,
    secret: str,
    tolerance_seconds: int = 300,
    previous_secret: Optional[str] = None,
) -> bool:
    """
    Verify an incoming webhook signature.

    Merchants use this to verify webhooks are authentic.

    During the 24-hour grace period after secret rotation, this function
    tries the current secret first, then falls back to the previous secret.

    Parameters
    ----------
    payload_body : bytes
        Raw request body.
    signature_header : str
        Value of ``X-Payment-Signature`` header (``t=...,v1=...``).
    secret : str
        The merchant's current webhook secret.
    tolerance_seconds : int
        Max age of the signature (replay protection).
    previous_secret : str, optional
        The previous webhook secret (for rotation grace period).

    Returns
    -------
    bool
        True if signature is valid with either current or previous secret.
    """
    def _verify_with_secret(sec: str) -> bool:
        try:
            parts = dict(p.split("=", 1) for p in signature_header.split(","))
            timestamp = parts.get("t", "")
            expected_sig = parts.get("v1", "")

            if not timestamp or not expected_sig:
                return False

            # Replay protection
            ts = int(timestamp)
            if abs(time.time() - ts) > tolerance_seconds:
                return False

            signed_payload = f"{timestamp}.".encode() + payload_body
            computed = hmac.new(
                sec.encode(),
                signed_payload,
                hashlib.sha256,
            ).hexdigest()

            return hmac.compare_digest(computed, expected_sig)
        except Exception:
            return False

    # Try current secret first
    if _verify_with_secret(secret):
        return True
    
    # Fall back to previous secret (rotation grace period)
    if previous_secret and _verify_with_secret(previous_secret):
        logger.info("Webhook verified with previous secret (rotation grace period)")
        return True
    
    return False


async def send_refund_webhook(refund: Refund, db: Session, retry_count: int = 0):
    """
    Send webhook notification to merchant when refund status changes.
    
    Args:
        refund: Refund object with all details
        db: Database session
        retry_count: Current retry attempt (0-indexed)
    """
    if not refund.merchant.webhook_url:
        logger.warning(f"No webhook URL for merchant {refund.merchant.id}, skipping refund webhook")
        return
    
    # Prepare webhook payload for refund
    event_type = f"refund.{refund.status.value.lower()}" if refund.status else "refund.pending"
    
    payload_dict = {
        "event": event_type,
        "refund_id": refund.id,
        "payment_session_id": str(refund.payment_session_id),
        "merchant_id": str(refund.merchant_id),
        "amount": str(refund.amount),
        "token": refund.token,
        "chain": refund.chain,
        "status": refund.status.value if refund.status else "PENDING",
        "tx_hash": refund.tx_hash or None,  # None if still pending
        "recipient_address": refund.refund_address,
        "refund_reason": refund.reason or None,
        "failure_reason": refund.failure_reason or None,
        "created_at": refund.created_at.isoformat() if refund.created_at else None,
        "processed_at": refund.processed_at.isoformat() if refund.processed_at else None,
        "completed_at": refund.completed_at.isoformat() if refund.completed_at else None,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
    
    webhook_url = refund.merchant.webhook_url
    payload_bytes = json.dumps(payload_dict, default=str).encode()

    # Build headers
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "ChainPe/2.2",
        "X-Webhook-Event": event_type,
        "X-Refund-ID": str(refund.id),
        "X-Chain": refund.chain or "stellar",
        "X-Token": refund.token or "USDC",
    }

    # Add HMAC signature if merchant has a webhook secret
    signing_secret = refund.merchant.webhook_secret or settings.WEBHOOK_SIGNING_SECRET
    if signing_secret:
        headers["X-Webhook-Signature"] = _compute_webhook_signature(
            payload_bytes, signing_secret
        )
    
    try:
        async with httpx.AsyncClient(timeout=settings.WEBHOOK_TIMEOUT_SECONDS) as client:
            response = await client.post(
                webhook_url,
                content=payload_bytes,
                headers=headers,
            )
            
            if response.status_code >= 200 and response.status_code < 300:
                logger.info(f"✅ Refund webhook sent successfully to {webhook_url} for refund {refund.id} (status: {refund.status.value})")
            else:
                logger.warning(
                    f"Refund webhook returned non-2xx status {response.status_code} for refund {refund.id}"
                )
                
                if retry_count < settings.WEBHOOK_RETRY_LIMIT - 1:
                    logger.info(f"Retrying refund webhook (attempt {retry_count + 2}/{settings.WEBHOOK_RETRY_LIMIT})...")
                    await send_refund_webhook(refund, db, retry_count + 1)
                else:
                    logger.error(f"Refund webhook failed after {settings.WEBHOOK_RETRY_LIMIT} attempts for refund {refund.id}")
                    
    except httpx.TimeoutException:
        logger.error(f"Refund webhook timeout for {webhook_url} (refund {refund.id})")
        if retry_count < settings.WEBHOOK_RETRY_LIMIT - 1:
            await send_refund_webhook(refund, db, retry_count + 1)
        else:
            logger.error(f"Refund webhook failed after {settings.WEBHOOK_RETRY_LIMIT} attempts for refund {refund.id}")
            
    except Exception as e:
        logger.error(f"Refund webhook error for {webhook_url} (refund {refund.id}): {e}", exc_info=True)
        if retry_count < settings.WEBHOOK_RETRY_LIMIT - 1:
            await send_refund_webhook(refund, db, retry_count + 1)
        else:
            logger.error(f"Refund webhook failed after {settings.WEBHOOK_RETRY_LIMIT} attempts for refund {refund.id}")
