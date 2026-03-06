import httpx
import logging
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models import PaymentSession
from app.schemas import WebhookPayload

logger = logging.getLogger(__name__)


async def send_webhook(session: PaymentSession, db: Session, retry_count: int = 0):
    """
    Send webhook notification to merchant.
    
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
        confirmations=session.confirmations
    )
    
    webhook_url = session.merchant.webhook_url
    
    try:
        async with httpx.AsyncClient(timeout=settings.WEBHOOK_TIMEOUT_SECONDS) as client:
            response = await client.post(
                webhook_url,
                json=payload.model_dump(),
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "DariForBusiness/1.0",
                    "X-Webhook-Event": "payment.success",
                    "X-Session-ID": session.id,
                    "X-Chain": session.chain or "stellar",
                    "X-Token": session.token or "USDC",
                }
            )
            
            if response.status_code >= 200 and response.status_code < 300:
                logger.info(f"✅ Webhook sent successfully to {webhook_url} for session {session.id}")
            else:
                logger.warning(
                    f"Webhook returned non-2xx status {response.status_code} for session {session.id}"
                )
                
                # Retry if within limit
                if retry_count < settings.WEBHOOK_RETRY_LIMIT - 1:
                    logger.info(f"Retrying webhook (attempt {retry_count + 2}/{settings.WEBHOOK_RETRY_LIMIT})...")
                    await send_webhook(session, db, retry_count + 1)
                else:
                    logger.error(f"❌ Webhook failed after {settings.WEBHOOK_RETRY_LIMIT} attempts for session {session.id}")
                    
    except httpx.TimeoutException:
        logger.error(f"Webhook timeout for {webhook_url} (session {session.id})")
        
        # Retry if within limit
        if retry_count < settings.WEBHOOK_RETRY_LIMIT - 1:
            logger.info(f"Retrying webhook (attempt {retry_count + 2}/{settings.WEBHOOK_RETRY_LIMIT})...")
            await send_webhook(session, db, retry_count + 1)
        else:
            logger.error(f"❌ Webhook failed after {settings.WEBHOOK_RETRY_LIMIT} attempts for session {session.id}")
            
    except Exception as e:
        logger.error(f"Webhook error for {webhook_url}: {e}")
        
        # Retry if within limit
        if retry_count < settings.WEBHOOK_RETRY_LIMIT - 1:
            logger.info(f"Retrying webhook (attempt {retry_count + 2}/{settings.WEBHOOK_RETRY_LIMIT})...")
            await send_webhook(session, db, retry_count + 1)
        else:
            logger.error(f"❌ Webhook failed after {settings.WEBHOOK_RETRY_LIMIT} attempts for session {session.id}")
