"""
Currency Formatting Service

Provides server-side currency formatting using babel.numbers for locale-aware
formatting with proper symbols, thousand separators, and decimal places.
"""

from decimal import Decimal
from typing import Optional
import babel.numbers
from babel.core import Locale


class CurrencyFormattingService:
    """
    Service for formatting currency amounts with locale support.
    Uses babel.numbers for proper internationalization.
    """
    
    # Special cases for currencies with non-standard decimal places
    DECIMAL_PLACES_MAP = {
        "JPY": 0,  # Japanese Yen has no decimal places
        "KRW": 0,  # Korean Won has no decimal places
        "VND": 0,  # Vietnamese Dong has no decimal places
        "CLP": 0,  # Chilean Peso has no decimal places
        "BTC": 8,  # Bitcoin uses 8 decimal places
        "ETH": 8,  # Ethereum uses 8 decimal places
        "USDC": 6,  # USDC uses 6 decimal places
        "USDT": 6,  # USDT uses 6 decimal places
        "PYUSD": 6,  # PYUSD uses 6 decimal places
    }
    
    def __init__(self, merchant_currency: str = "USD", merchant_locale: str = "en_US"):
        """
        Initialize the currency formatter.
        
        Args:
            merchant_currency: ISO 4217 currency code (e.g., "USD", "EUR", "INR")
            merchant_locale: Locale string (e.g., "en_US", "en_IN", "de_DE")
        """
        self.currency = merchant_currency
        self.locale = merchant_locale
        
    def format_currency(
        self,
        amount: Decimal,
        currency: Optional[str] = None,
        locale: Optional[str] = None
    ) -> str:
        """
        Format a currency amount with proper locale formatting.
        
        Args:
            amount: The numeric amount to format
            currency: Currency code (defaults to merchant's currency)
            locale: Locale string (defaults to merchant's locale)
            
        Returns:
            Formatted currency string (e.g., "$1,234.56", "₹1,02,345.67")
        """
        currency = currency or self.currency
        locale = locale or self.locale
        
        try:
            # Get decimal places for this currency
            decimal_places = self.get_decimal_places(currency)
            
            # Format using babel
            formatted = babel.numbers.format_currency(
                amount,
                currency,
                locale=locale,
                decimal_quantization=False  # Use currency's natural decimal places
            )
            
            return formatted
        except Exception as e:
            # Fallback to simple formatting if babel fails
            symbol = self.get_currency_symbol(currency, locale)
            return f"{symbol}{amount:,.{self.get_decimal_places(currency)}f}"
    
    def get_currency_symbol(
        self,
        currency: Optional[str] = None,
        locale: Optional[str] = None
    ) -> str:
        """
        Get the currency symbol for a given currency and locale.
        
        Args:
            currency: Currency code (defaults to merchant's currency)
            locale: Locale string (defaults to merchant's locale)
            
        Returns:
            Currency symbol (e.g., "$", "€", "₹")
        """
        currency = currency or self.currency
        locale = locale or self.locale
        
        try:
            return babel.numbers.get_currency_symbol(currency, locale=locale)
        except Exception:
            # Fallback symbols
            fallback_symbols = {
                "USD": "$",
                "EUR": "€",
                "GBP": "£",
                "INR": "₹",
                "JPY": "¥",
                "CNY": "¥",
                "KRW": "₩",
                "BTC": "₿",
                "ETH": "Ξ",
                "USDC": "USDC",
                "USDT": "USDT",
                "PYUSD": "PYUSD",
            }
            return fallback_symbols.get(currency, currency)
    
    def get_decimal_places(self, currency: str) -> int:
        """
        Get the number of decimal places for a currency.
        
        Args:
            currency: Currency code
            
        Returns:
            Number of decimal places (typically 2, except for special cases)
        """
        # Check special cases first
        if currency in self.DECIMAL_PLACES_MAP:
            return self.DECIMAL_PLACES_MAP[currency]
        
        # Default to 2 decimal places for most fiat currencies
        return 2
    
    def format_amount_simple(
        self,
        amount: Decimal,
        currency: Optional[str] = None
    ) -> str:
        """
        Format amount without currency symbol (just the number).
        
        Args:
            amount: The numeric amount to format
            currency: Currency code (for decimal places)
            
        Returns:
            Formatted number string (e.g., "1,234.56")
        """
        currency = currency or self.currency
        decimal_places = self.get_decimal_places(currency)
        
        try:
            locale_obj = Locale.parse(self.locale)
            return babel.numbers.format_decimal(
                amount,
                locale=locale_obj,
                decimal_quantization=False
            )
        except Exception:
            # Fallback to simple formatting
            return f"{amount:,.{decimal_places}f}"


# Global instance (can be overridden per request via middleware)
_default_formatter = CurrencyFormattingService()


def get_formatter(currency: str = "USD", locale: str = "en_US") -> CurrencyFormattingService:
    """
    Get a currency formatter instance.
    
    Args:
        currency: ISO 4217 currency code
        locale: Locale string
        
    Returns:
        CurrencyFormattingService instance
    """
    return CurrencyFormattingService(currency, locale)
