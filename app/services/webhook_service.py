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
from app.models import PaymentSession
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
) -> bool:
    """
    Verify an incoming webhook signature.

    Merchants use this to verify webhooks are authentic.

    Parameters
    ----------
    payload_body : bytes
        Raw request body.
    signature_header : str
        Value of ``X-Payment-Signature`` header (``t=...,v1=...``).
    secret : str
        The merchant's webhook secret.
    tolerance_seconds : int
        Max age of the signature (replay protection).

    Returns
    -------
    bool
        True if signature is valid.
    """
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
            secret.encode(),
            signed_payload,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(computed, expected_sig)
    except Exception:
        return False
