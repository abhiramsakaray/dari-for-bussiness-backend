"""
Price Conversion Service

Handles fiat to crypto price conversion using external APIs.
Supports multiple stablecoins and fiat currencies.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Dict, Any
import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# Supported fiat currencies
SUPPORTED_FIAT = ["USD", "EUR", "GBP", "INR", "AUD", "CAD", "JPY", "CNY"]

# Stablecoin coingecko IDs
STABLECOIN_IDS = {
    "USDC": "usd-coin",
    "USDT": "tether",
    "PYUSD": "paypal-usd"
}


class PriceCache:
    """Simple in-memory price cache"""
    
    def __init__(self, ttl_seconds: int = 60):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._ttl = timedelta(seconds=ttl_seconds)
        
    def get(self, key: str) -> Optional[Decimal]:
        """Get cached price"""
        if key not in self._cache:
            return None
        entry = self._cache[key]
        if datetime.utcnow() - entry["timestamp"] > self._ttl:
            del self._cache[key]
            return None
        return entry["price"]
        
    def set(self, key: str, price: Decimal):
        """Set cached price"""
        self._cache[key] = {
            "price": price,
            "timestamp": datetime.utcnow()
        }
        
    def clear(self):
        """Clear all cached prices"""
        self._cache.clear()


class PriceService:
    """
    Price conversion service for fiat to crypto.
    
    Uses CoinGecko API for price data.
    Stablecoins are assumed to be 1:1 with USD.
    """
    
    def __init__(self):
        self._cache = PriceCache(ttl_seconds=60)
        self._http_client: Optional[httpx.AsyncClient] = None
        self._coingecko_base = "https://api.coingecko.com/api/v3"
        
    @property
    def client(self) -> httpx.AsyncClient:
        """Get async HTTP client"""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client
        
    async def close(self):
        """Close HTTP client"""
        if self._http_client:
            await self._http_client.aclose()
            
    async def get_fiat_rate(self, from_currency: str, to_currency: str = "USD") -> Decimal:
        """
        Get exchange rate between fiat currencies.
        
        Args:
            from_currency: Source currency (e.g., "EUR")
            to_currency: Target currency (e.g., "USD")
            
        Returns:
            Exchange rate (1 from_currency = X to_currency)
        """
        if from_currency == to_currency:
            return Decimal("1")
            
        cache_key = f"fiat:{from_currency}:{to_currency}"
        cached = self._cache.get(cache_key)
        if cached:
            return cached
            
        try:
            # Use free currency API
            response = await self.client.get(
                f"https://api.exchangerate-api.com/v4/latest/{from_currency}"
            )
            
            if response.status_code == 200:
                data = response.json()
                rate = Decimal(str(data.get("rates", {}).get(to_currency, 1)))
                self._cache.set(cache_key, rate)
                return rate
                
        except Exception as e:
            logger.error(f"Error fetching fiat rate: {e}")
            
        # Fallback: return 1 for USD-pegged
        return Decimal("1")
        
    async def get_stablecoin_price(self, symbol: str, currency: str = "USD") -> Decimal:
        """
        Get stablecoin price in fiat.
        
        For stablecoins, we assume ~1:1 with USD but fetch actual rate
        for accuracy during depegging events.
        
        Args:
            symbol: Token symbol (USDC, USDT, PYUSD)
            currency: Fiat currency
            
        Returns:
            Price in specified fiat currency
        """
        cache_key = f"stable:{symbol}:{currency}"
        cached = self._cache.get(cache_key)
        if cached:
            return cached
            
        try:
            coingecko_id = STABLECOIN_IDS.get(symbol.upper())
            if not coingecko_id:
                # Unknown stablecoin, assume 1:1 with USD
                if currency == "USD":
                    return Decimal("1")
                return await self.get_fiat_rate("USD", currency)
                
            # Fetch from CoinGecko
            response = await self.client.get(
                f"{self._coingecko_base}/simple/price",
                params={
                    "ids": coingecko_id,
                    "vs_currencies": currency.lower()
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                price = data.get(coingecko_id, {}).get(currency.lower())
                if price:
                    result = Decimal(str(price))
                    self._cache.set(cache_key, result)
                    return result
                    
        except Exception as e:
            logger.error(f"Error fetching stablecoin price: {e}")
            
        # Fallback: 1:1 with USD
        if currency == "USD":
            return Decimal("1")
        return await self.get_fiat_rate("USD", currency)
        
    async def convert_fiat_to_token(
        self,
        amount: Decimal,
        fiat_currency: str,
        token_symbol: str,
        precision: int = 2
    ) -> Decimal:
        """
        Convert fiat amount to token amount.
        
        Args:
            amount: Fiat amount
            fiat_currency: Fiat currency code
            token_symbol: Target token symbol
            precision: Decimal precision for result
            
        Returns:
            Token amount
        """
        try:
            # Get stablecoin price in USD
            token_price_usd = await self.get_stablecoin_price(token_symbol, "USD")
            
            # Get fiat currency rate to USD
            if fiat_currency.upper() != "USD":
                fiat_rate = await self.get_fiat_rate(fiat_currency, "USD")
                amount_usd = amount * fiat_rate
            else:
                amount_usd = amount
                
            # Calculate token amount
            token_amount = amount_usd / token_price_usd
            
            # Round to precision
            return token_amount.quantize(
                Decimal(10) ** -precision,
                rounding=ROUND_HALF_UP
            )
            
        except Exception as e:
            logger.error(f"Error converting fiat to token: {e}")
            # Fallback: 1:1 conversion
            return amount
            
    async def convert_token_to_fiat(
        self,
        amount: Decimal,
        token_symbol: str,
        fiat_currency: str,
        precision: int = 2
    ) -> Decimal:
        """
        Convert token amount to fiat amount.
        
        Args:
            amount: Token amount
            token_symbol: Token symbol
            fiat_currency: Target fiat currency
            precision: Decimal precision for result
            
        Returns:
            Fiat amount
        """
        try:
            # Get token price in target fiat
            token_price = await self.get_stablecoin_price(token_symbol, fiat_currency)
            
            # Calculate fiat amount
            fiat_amount = amount * token_price
            
            # Round to precision
            return fiat_amount.quantize(
                Decimal(10) ** -precision,
                rounding=ROUND_HALF_UP
            )
            
        except Exception as e:
            logger.error(f"Error converting token to fiat: {e}")
            return amount
            
    async def get_payment_amount(
        self,
        fiat_amount: Decimal,
        fiat_currency: str,
        token_symbol: str
    ) -> Dict[str, Any]:
        """
        Calculate payment amount for checkout.
        
        Args:
            fiat_amount: Amount in fiat
            fiat_currency: Fiat currency code
            token_symbol: Target stablecoin
            
        Returns:
            Payment details including token amount and exchange rate
        """
        try:
            token_amount = await self.convert_fiat_to_token(
                fiat_amount,
                fiat_currency,
                token_symbol
            )
            
            # Get effective exchange rate
            if token_amount > 0:
                rate = fiat_amount / token_amount
            else:
                rate = Decimal("1")
                
            return {
                "fiat_amount": str(fiat_amount),
                "fiat_currency": fiat_currency,
                "token_amount": str(token_amount),
                "token_symbol": token_symbol,
                "exchange_rate": str(rate),
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error calculating payment amount: {e}")
            return {
                "fiat_amount": str(fiat_amount),
                "fiat_currency": fiat_currency,
                "token_amount": str(fiat_amount),  # 1:1 fallback
                "token_symbol": token_symbol,
                "exchange_rate": "1",
                "timestamp": datetime.utcnow().isoformat()
            }


# Singleton instance
_price_service: Optional[PriceService] = None


def get_price_service() -> PriceService:
    """Get singleton price service"""
    global _price_service
    if _price_service is None:
        _price_service = PriceService()
    return _price_service


async def convert_fiat_to_token(
    amount: float,
    fiat_currency: str = "USD",
    token_symbol: str = "USDC"
) -> str:
    """
    Convenience function for fiat to token conversion.
    
    Args:
        amount: Fiat amount
        fiat_currency: Fiat currency code
        token_symbol: Target token
        
    Returns:
        Token amount as string
    """
    service = get_price_service()
    result = await service.convert_fiat_to_token(
        Decimal(str(amount)),
        fiat_currency,
        token_symbol
    )
    return str(result)
