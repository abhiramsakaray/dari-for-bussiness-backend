from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core import get_db, require_admin
from app.models import PaymentSession, PaymentStatus
from app.services.webhook_service import send_webhook

router = APIRouter(prefix="/admin/webhooks", tags=["Admin - Webhooks"])


@router.post("/retry/{session_id}")
async def retry_webhook(
    session_id: str,
    current_user: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Manually retry webhook delivery for a paid session (admin only)."""
    session = db.query(PaymentSession).filter(
        PaymentSession.id == session_id
    ).first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment session not found"
        )
    
    if session.status != PaymentStatus.PAID:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only retry webhooks for paid sessions"
        )
    
    if not session.merchant.webhook_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Merchant has no webhook URL configured"
        )
    
    # Retry webhook
    await send_webhook(session, db, retry_count=0)
    
    return {
        "message": "Webhook retry initiated",
        "session_id": session_id,
        "webhook_url": session.merchant.webhook_url
    }


@router.get("/test/{merchant_id}")
async def test_webhook(
    merchant_id: str,
    current_user: dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Send a test webhook to merchant (admin only)."""
    from app.models import Merchant
    import httpx
    
    merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    
    if not merchant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Merchant not found"
        )
    
    if not merchant.webhook_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Merchant has no webhook URL configured"
        )
    
    # Send test webhook
    test_payload = {
        "event": "webhook.test",
        "session_id": "test_session",
        "amount": "0.00",
        "currency": "USDC",
        "tx_hash": "test_transaction",
        "message": "This is a test webhook from Dari for Business"
    }
    
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                merchant.webhook_url,
                json=test_payload,
                headers={"Content-Type": "application/json"}
            )
            
            return {
                "success": True,
                "webhook_url": merchant.webhook_url,
                "status_code": response.status_code,
                "response": response.text[:500]  # First 500 chars
            }
    except Exception as e:
        return {
            "success": False,
            "webhook_url": merchant.webhook_url,
            "error": str(e)
        }
