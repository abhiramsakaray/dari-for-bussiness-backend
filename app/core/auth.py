"""Authentication and authorization utilities."""
from fastapi import Header, HTTPException, status, Depends
from sqlalchemy.orm import Session
from app.models import Merchant
from app.core.database import get_db
from typing import Optional


async def get_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
) -> str:
    """
    Extract and validate API key from request header.
    
    Usage:
    ```python
    @router.post("/endpoint")
    async def my_endpoint(api_key: str = Depends(get_api_key)):
        # api_key is validated and ready to use
    ```
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required. Include 'X-API-Key' header with your API key."
        )
    
    return x_api_key


async def validate_merchant_api_key(api_key: str, db: Session) -> Merchant:
    """
    Validate API key and return merchant object.
    
    Args:
        api_key: The API key to validate
        db: Database session
        
    Returns:
        Merchant object if valid
        
    Raises:
        HTTPException if invalid
    """
    merchant = db.query(Merchant).filter(Merchant.api_key == api_key).first()
    
    if not merchant:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )
    
    if not merchant.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Merchant account is disabled"
        )
    
    return merchant


async def get_current_merchant(
    api_key: str = Depends(get_api_key),
    db: Session = Depends(get_db)
) -> Merchant:
    """
    Dependency to get the currently authenticated merchant.
    
    Extracts API key from headers and validates it.
    
    Usage:
    ```python
    @router.post("/endpoint")
    async def my_endpoint(merchant: Merchant = Depends(get_current_merchant)):
        # merchant is authenticated and ready to use
    ```
    """
    return await validate_merchant_api_key(api_key, db)
