from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import secrets as secrets_module
import uuid
from datetime import datetime
from app.core import get_db, require_merchant
from app.models import Merchant
from app.schemas import MerchantProfileUpdate, MerchantProfile

router = APIRouter(prefix="/merchant", tags=["Merchant"])


@router.get("/profile", response_model=MerchantProfile)
async def get_merchant_profile(
    current_user: dict = Depends(require_merchant),
    db: Session = Depends(get_db)
):
    """Get merchant profile."""
    merchant = db.query(Merchant).filter(Merchant.id == uuid.UUID(current_user["id"])).first()
    
    if not merchant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Merchant not found"
        )
    
    return MerchantProfile(
        id=str(merchant.id),
        name=merchant.name,
        email=merchant.email,
        stellar_address=merchant.stellar_address,
        webhook_url=merchant.webhook_url,
        is_active=merchant.is_active,
        created_at=merchant.created_at
    )


@router.put("/profile", response_model=MerchantProfile)
async def update_merchant_profile(
    profile_update: MerchantProfileUpdate,
    current_user: dict = Depends(require_merchant),
    db: Session = Depends(get_db)
):
    """Update merchant profile (Stellar address and webhook URL)."""
    merchant = db.query(Merchant).filter(Merchant.id == uuid.UUID(current_user["id"])).first()
    
    if not merchant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Merchant not found"
        )
    
    # Update fields
    if profile_update.stellar_address is not None:
        merchant.stellar_address = profile_update.stellar_address
    
    if profile_update.webhook_url is not None:
        merchant.webhook_url = str(profile_update.webhook_url)
    
    db.commit()
    db.refresh(merchant)
    
    return MerchantProfile(
        id=str(merchant.id),
        name=merchant.name,
        email=merchant.email,
        stellar_address=merchant.stellar_address,
        webhook_url=merchant.webhook_url,
        is_active=merchant.is_active,
        created_at=merchant.created_at
    )


@router.post("/webhook-secret/rotate")
async def rotate_webhook_secret(
    current_user: dict = Depends(require_merchant),
    db: Session = Depends(get_db),
):
    """
    Generate a new webhook secret for the merchant.

    The new secret is returned ONCE in the response.
    All future webhook deliveries will be signed with this secret.
    The merchant must update their webhook verification code immediately.

    Security:
    - 32-byte cryptographically secure random hex string (256 bits)
    - Old secret is preserved for a 24-hour grace period
    - Constant-time comparison used during verification (in webhook_service)
    """
    merchant = db.query(Merchant).filter(Merchant.id == uuid.UUID(current_user["id"])).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    # Preserve current secret as previous (24h grace period)
    if merchant.webhook_secret:
        merchant.webhook_secret_previous = merchant.webhook_secret

    # Generate a 256-bit random secret
    new_secret = secrets_module.token_hex(32)
    merchant.webhook_secret = new_secret
    merchant.webhook_secret_rotated_at = datetime.utcnow()
    db.commit()

    return {
        "webhook_secret": new_secret,
        "message": "Webhook secret rotated. Save this secret — it will not be shown again.",
        "grace_period": "Previous secret valid for 24 hours.",
        "header_name": "X-Payment-Signature",
        "signature_format": "t=<unix_timestamp>,v1=<hmac_sha256_hex>",
        "verification_note": "Compute HMAC-SHA256(secret, '<timestamp>.<raw_body>') and compare to v1.",
    }
