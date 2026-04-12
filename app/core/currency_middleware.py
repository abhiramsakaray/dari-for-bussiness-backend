"""
Merchant Currency Middleware

Injects merchant's currency preferences into request context for consistent
currency handling across all API endpoints.
"""

import logging
from typing import Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import Merchant

logger = logging.getLogger(__name__)


class MerchantCurrencyContext:
    """
    Currency context attached to request state.
    Contains merchant's currency preferences for formatting.
    """
    
    def __init__(
        self,
        currency: str = "USD",
        locale: str = "en_US",
        symbol: str = "$",
        decimal_places: int = 2
    ):
        self.currency = currency
        self.locale = locale
        self.symbol = symbol
        self.decimal_places = decimal_places
        
    @classmethod
    def from_merchant(cls, merchant: Merchant) -> "MerchantCurrencyContext":
        """Create context from merchant model"""
        return cls(
            currency=merchant.currency_preference or merchant.base_currency or "USD",
            locale=merchant.currency_locale or "en_US",
            symbol=merchant.currency_symbol or "$",
            decimal_places=merchant.currency_decimal_places or 2
        )
        
    @classmethod
    def default(cls) -> "MerchantCurrencyContext":
        """Create default USD context"""
        return cls(
            currency="USD",
            locale="en_US",
            symbol="$",
            decimal_places=2
        )


class MerchantCurrencyMiddleware(BaseHTTPMiddleware):
    """
    Middleware that injects merchant currency preferences into request context.
    
    Extracts merchant_id from:
    1. request.state.merchant (set by auth middleware)
    2. API key from Authorization header
    3. JWT token from Authorization header
    
    Attaches MerchantCurrencyContext to request.state.currency_context
    """
    
    async def dispatch(self, request: Request, call_next):
        # Initialize with default context
        currency_context = MerchantCurrencyContext.default()
        
        try:
            # Try to get merchant from request state (set by auth middleware)
            merchant = getattr(request.state, "merchant", None)
            
            if merchant:
                # Merchant already loaded by auth middleware
                currency_context = MerchantCurrencyContext.from_merchant(merchant)
                logger.debug(
                    f"Currency context from auth: {currency_context.currency} "
                    f"({currency_context.locale})"
                )
            else:
                # Try to extract merchant_id from auth headers
                merchant_id = self._extract_merchant_id(request)
                
                if merchant_id:
                    # Load merchant from database
                    db = next(get_db())
                    try:
                        merchant = db.query(Merchant).filter(
                            Merchant.id == merchant_id
                        ).first()
                        
                        if merchant:
                            currency_context = MerchantCurrencyContext.from_merchant(merchant)
                            logger.debug(
                                f"Currency context loaded: {currency_context.currency} "
                                f"({currency_context.locale})"
                            )
                    finally:
                        db.close()
                        
        except Exception as e:
            logger.warning(f"Failed to load merchant currency context: {e}")
            # Continue with default context
            
        # Attach currency context to request state
        request.state.currency_context = currency_context
        
        # Process request
        response: Response = await call_next(request)
        
        return response
        
    def _extract_merchant_id(self, request: Request) -> Optional[str]:
        """
        Extract merchant_id from request.
        
        Tries:
        1. API key from Authorization header
        2. JWT token from Authorization header (would need JWT decoding)
        3. merchant_id from path parameters
        
        Returns:
            Merchant ID string or None
        """
        # Try API key
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            api_key = auth_header[7:]
            
            # Look up merchant by API key
            db = next(get_db())
            try:
                merchant = db.query(Merchant).filter(
                    Merchant.api_key == api_key
                ).first()
                if merchant:
                    return str(merchant.id)
            finally:
                db.close()
                
        # Could add JWT token decoding here if needed
        # For now, rely on auth middleware to set request.state.merchant
        
        return None


def get_currency_context(request: Request) -> MerchantCurrencyContext:
    """
    Get currency context from request state.
    
    Args:
        request: FastAPI request object
        
    Returns:
        MerchantCurrencyContext (defaults to USD if not set)
    """
    return getattr(
        request.state,
        "currency_context",
        MerchantCurrencyContext.default()
    )
