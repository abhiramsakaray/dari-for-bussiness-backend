from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
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
    merchant = db.query(Merchant).filter(Merchant.id == current_user["id"]).first()
    
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
    merchant = db.query(Merchant).filter(Merchant.id == current_user["id"]).first()
    
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
