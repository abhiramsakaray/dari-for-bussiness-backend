"""
Exchange Rate Service

Centralized exchange rate management with caching for consistent rates across
all API endpoints. Integrates with existing PriceService and adds Redis caching.
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, Dict, Any
import json

from app.services.price_service import get_price_service
from app.services.currency_formatting_service import CurrencyFormattingService
from app.schemas.schemas import MonetaryAmount, MerchantCurrency
from app.core.cache import get_redis_client

logger = logging.getLogger(__name__)


class ExchangeRateService:
    """
    Centralized exchange rate service with caching.
    
    Provides consistent exchange rates across all API endpoints within cache TTL.
    Uses Redis for distributed caching with 1-hour TTL, falls back to in-memory cache.
    """
    
    CACHE_TTL_SECONDS = 3600  # 1 hour
    CACHE_PREFIX = "exchange_rate:"
    
    def __init__(self):
        self._price_service = get_price_service()
        self._memory_cache: Dict[str, Dict[str, Any]] = {}
        self._redis_client = None
        
    def _get_redis(self):
        """Get Redis client (lazy initialization)"""
        if self._redis_client is None:
            try:
                self._redis_client = get_redis_client()
            except Exception as e:
                logger.warning(f"Redis not available, using memory cache: {e}")
        return self._redis_client
        
    def _get_cache_key(self, from_currency: str, to_currency: str) -> str:
        """Generate cache key for currency pair"""
        return f"{self.CACHE_PREFIX}{from_currency}_{to_currency}"
        
    async def get_rate(
        self,
        from_currency: str,
        to_currency: str
    ) -> Decimal:
        """
        Get exchange rate between two currencies with caching.
        
        Args:
            from_currency: Source currency code (e.g., "USD", "EUR")
            to_currency: Target currency code (e.g., "INR", "GBP")
            
        Returns:
            Exchange rate (1 from_currency = X to_currency)
        """
        if from_currency == to_currency:
            return Decimal("1")
            
        cache_key = self._get_cache_key(from_currency, to_currency)
        
        # Try Redis cache first
        try:
            redis = self._get_redis()
            if redis:
                cached_value = redis.get(cache_key)
                if cached_value:
                    logger.debug(f"Cache hit (Redis): {from_currency} -> {to_currency}")
                    return Decimal(cached_value.decode('utf-8'))
        except Exception as e:
            logger.warning(f"Redis cache read failed: {e}")
            
        # Try memory cache
        if cache_key in self._memory_cache:
            entry = self._memory_cache[cache_key]
            if datetime.utcnow() - entry["timestamp"] < timedelta(seconds=self.CACHE_TTL_SECONDS):
                logger.debug(f"Cache hit (memory): {from_currency} -> {to_currency}")
                return entry["rate"]
            else:
                # Expired, remove from memory cache
                del self._memory_cache[cache_key]
                
        # Cache miss - fetch from PriceService
        logger.debug(f"Cache miss: {from_currency} -> {to_currency}, fetching...")
        rate = await self._price_service.get_fiat_rate(from_currency, to_currency)
        
        # Store in caches
        self._cache_rate(cache_key, rate)
        
        return rate
        
    def _cache_rate(self, cache_key: str, rate: Decimal):
        """Store rate in both Redis and memory cache"""
        # Store in Redis
        try:
            redis = self._get_redis()
            if redis:
                redis.setex(
                    cache_key,
                    self.CACHE_TTL_SECONDS,
                    str(rate)
                )
                logger.debug(f"Cached rate in Redis: {cache_key} = {rate}")
        except Exception as e:
            logger.warning(f"Redis cache write failed: {e}")
            
        # Store in memory cache as fallback
        self._memory_cache[cache_key] = {
            "rate": rate,
            "timestamp": datetime.utcnow()
        }
        
    async def convert(
        self,
        amount: Decimal,
        from_currency: str,
        to_currency: str
    ) -> Decimal:
        """
        Convert amount between currencies.
        
        Args:
            amount: Amount in source currency
            from_currency: Source currency code
            to_currency: Target currency code
            
        Returns:
            Converted amount in target currency
        """
        if from_currency == to_currency:
            return amount
            
        rate = await self.get_rate(from_currency, to_currency)
        return amount * rate
        
    async def build_monetary_amount(
        self,
        amount: Decimal,
        currency: str,
        merchant_currency: str,
        merchant_locale: str = "en_US",
        crypto_amount: Optional[Decimal] = None,
        crypto_token: Optional[str] = None,
        crypto_chain: Optional[str] = None
    ) -> MonetaryAmount:
        """
        Build a complete MonetaryAmount object with all metadata.
        
        Args:
            amount: The numeric amount (in the specified currency)
            currency: Currency code for the amount
            merchant_currency: Merchant's preferred currency
            merchant_locale: Merchant's locale for formatting
            crypto_amount: Optional crypto token amount
            crypto_token: Optional token symbol (USDC, USDT, etc.)
            crypto_chain: Optional blockchain network
            
        Returns:
            MonetaryAmount object with complete metadata
        """
        # Initialize formatter
        formatter = CurrencyFormattingService(currency, merchant_locale)
        
        # Format primary amount
        symbol = formatter.get_currency_symbol(currency)
        formatted = formatter.format_currency(amount, currency)
        
        # Calculate USD equivalent if not already in USD
        amount_usd = None
        formatted_usd = None
        if currency != "USD":
            try:
                amount_usd = await self.convert(amount, currency, "USD")
                usd_formatter = CurrencyFormattingService("USD", "en_US")
                formatted_usd = usd_formatter.format_currency(amount_usd, "USD")
            except Exception as e:
                logger.warning(f"Failed to convert to USD: {e}")
                
        return MonetaryAmount(
            amount=amount,
            currency=currency,
            symbol=symbol,
            formatted=formatted,
            amount_usd=amount_usd,
            formatted_usd=formatted_usd,
            amount_crypto=crypto_amount,
            crypto_token=crypto_token,
            crypto_chain=crypto_chain
        )
        
    async def build_monetary_amount_from_usd(
        self,
        amount_usd: Decimal,
        merchant_currency: str,
        merchant_locale: str = "en_US",
        crypto_amount: Optional[Decimal] = None,
        crypto_token: Optional[str] = None,
        crypto_chain: Optional[str] = None
    ) -> MonetaryAmount:
        """
        Build MonetaryAmount starting from USD amount.
        
        Converts USD to merchant's preferred currency and builds complete object.
        
        Args:
            amount_usd: Amount in USD
            merchant_currency: Merchant's preferred currency
            merchant_locale: Merchant's locale for formatting
            crypto_amount: Optional crypto token amount
            crypto_token: Optional token symbol
            crypto_chain: Optional blockchain network
            
        Returns:
            MonetaryAmount object with merchant's currency as primary
        """
        # Convert USD to merchant currency
        if merchant_currency == "USD":
            amount = amount_usd
        else:
            amount = await self.convert(amount_usd, "USD", merchant_currency)
            
        # Initialize formatter
        formatter = CurrencyFormattingService(merchant_currency, merchant_locale)
        
        # Format amounts
        symbol = formatter.get_currency_symbol(merchant_currency)
        formatted = formatter.format_currency(amount, merchant_currency)
        
        # Format USD
        usd_formatter = CurrencyFormattingService("USD", "en_US")
        formatted_usd = usd_formatter.format_currency(amount_usd, "USD")
        
        return MonetaryAmount(
            amount=amount,
            currency=merchant_currency,
            symbol=symbol,
            formatted=formatted,
            amount_usd=amount_usd,
            formatted_usd=formatted_usd,
            amount_crypto=crypto_amount,
            crypto_token=crypto_token,
            crypto_chain=crypto_chain
        )
        
    def clear_cache(self):
        """Clear all cached exchange rates"""
        # Clear memory cache
        self._memory_cache.clear()
        
        # Clear Redis cache (all keys with our prefix)
        try:
            redis = self._get_redis()
            if redis:
                keys = redis.keys(f"{self.CACHE_PREFIX}*")
                if keys:
                    redis.delete(*keys)
                logger.info(f"Cleared {len(keys)} exchange rate cache entries from Redis")
        except Exception as e:
            logger.warning(f"Failed to clear Redis cache: {e}")
            
    async def get_merchant_currency_context(
        self,
        merchant_currency: str,
        merchant_locale: str = "en_US"
    ) -> MerchantCurrency:
        """
        Get merchant currency context for API responses.
        
        Args:
            merchant_currency: Merchant's preferred currency code
            merchant_locale: Merchant's locale
            
        Returns:
            MerchantCurrency object with metadata
        """
        formatter = CurrencyFormattingService(merchant_currency, merchant_locale)
        
        return MerchantCurrency(
            currency=merchant_currency,
            symbol=formatter.get_currency_symbol(merchant_currency),
            locale=merchant_locale,
            decimal_places=formatter.get_decimal_places(merchant_currency)
        )


# Singleton instance
_exchange_rate_service: Optional[ExchangeRateService] = None


def get_exchange_rate_service() -> ExchangeRateService:
    """Get singleton exchange rate service"""
    global _exchange_rate_service
    if _exchange_rate_service is None:
        _exchange_rate_service = ExchangeRateService()
    return _exchange_rate_service
