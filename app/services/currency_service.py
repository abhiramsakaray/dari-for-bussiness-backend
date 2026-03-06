"""
Currency Service

Maps merchant countries to local currencies and provides
dual-currency conversion helpers (local currency + USDC).
Uses the existing PriceService for exchange rates.
"""

import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Dict, Tuple

from app.services.price_service import get_price_service

logger = logging.getLogger(__name__)


# ── Country → (Currency Code, Currency Symbol, Currency Name) ──
# Covers 100+ countries. Falls back to USD if not found.

COUNTRY_CURRENCY_MAP: Dict[str, Tuple[str, str, str]] = {
    # Asia
    "India": ("INR", "₹", "Indian Rupee"),
    "Pakistan": ("PKR", "₨", "Pakistani Rupee"),
    "Bangladesh": ("BDT", "৳", "Bangladeshi Taka"),
    "Sri Lanka": ("LKR", "Rs", "Sri Lankan Rupee"),
    "Nepal": ("NPR", "₨", "Nepalese Rupee"),
    "Japan": ("JPY", "¥", "Japanese Yen"),
    "China": ("CNY", "¥", "Chinese Yuan"),
    "South Korea": ("KRW", "₩", "South Korean Won"),
    "Singapore": ("SGD", "S$", "Singapore Dollar"),
    "Malaysia": ("MYR", "RM", "Malaysian Ringgit"),
    "Indonesia": ("IDR", "Rp", "Indonesian Rupiah"),
    "Thailand": ("THB", "฿", "Thai Baht"),
    "Vietnam": ("VND", "₫", "Vietnamese Dong"),
    "Philippines": ("PHP", "₱", "Philippine Peso"),
    "Taiwan": ("TWD", "NT$", "New Taiwan Dollar"),
    "Hong Kong": ("HKD", "HK$", "Hong Kong Dollar"),
    "UAE": ("AED", "د.إ", "UAE Dirham"),
    "United Arab Emirates": ("AED", "د.إ", "UAE Dirham"),
    "Saudi Arabia": ("SAR", "﷼", "Saudi Riyal"),
    "Qatar": ("QAR", "﷼", "Qatari Riyal"),
    "Kuwait": ("KWD", "د.ك", "Kuwaiti Dinar"),
    "Bahrain": ("BHD", "BD", "Bahraini Dinar"),
    "Oman": ("OMR", "﷼", "Omani Rial"),
    "Israel": ("ILS", "₪", "Israeli Shekel"),
    "Turkey": ("TRY", "₺", "Turkish Lira"),
    "Iraq": ("IQD", "ع.د", "Iraqi Dinar"),
    "Iran": ("IRR", "﷼", "Iranian Rial"),
    "Jordan": ("JOD", "JD", "Jordanian Dinar"),
    "Lebanon": ("LBP", "ل.ل", "Lebanese Pound"),
    "Myanmar": ("MMK", "K", "Myanmar Kyat"),
    "Cambodia": ("KHR", "៛", "Cambodian Riel"),

    # Europe
    "Germany": ("EUR", "€", "Euro"),
    "France": ("EUR", "€", "Euro"),
    "Italy": ("EUR", "€", "Euro"),
    "Spain": ("EUR", "€", "Euro"),
    "Netherlands": ("EUR", "€", "Euro"),
    "Belgium": ("EUR", "€", "Euro"),
    "Austria": ("EUR", "€", "Euro"),
    "Portugal": ("EUR", "€", "Euro"),
    "Ireland": ("EUR", "€", "Euro"),
    "Finland": ("EUR", "€", "Euro"),
    "Greece": ("EUR", "€", "Euro"),
    "Luxembourg": ("EUR", "€", "Euro"),
    "Estonia": ("EUR", "€", "Euro"),
    "Latvia": ("EUR", "€", "Euro"),
    "Lithuania": ("EUR", "€", "Euro"),
    "Slovakia": ("EUR", "€", "Euro"),
    "Slovenia": ("EUR", "€", "Euro"),
    "Malta": ("EUR", "€", "Euro"),
    "Cyprus": ("EUR", "€", "Euro"),
    "Croatia": ("EUR", "€", "Euro"),
    "United Kingdom": ("GBP", "£", "British Pound"),
    "UK": ("GBP", "£", "British Pound"),
    "Switzerland": ("CHF", "CHF", "Swiss Franc"),
    "Sweden": ("SEK", "kr", "Swedish Krona"),
    "Norway": ("NOK", "kr", "Norwegian Krone"),
    "Denmark": ("DKK", "kr", "Danish Krone"),
    "Poland": ("PLN", "zł", "Polish Zloty"),
    "Czech Republic": ("CZK", "Kč", "Czech Koruna"),
    "Czechia": ("CZK", "Kč", "Czech Koruna"),
    "Hungary": ("HUF", "Ft", "Hungarian Forint"),
    "Romania": ("RON", "lei", "Romanian Leu"),
    "Bulgaria": ("BGN", "лв", "Bulgarian Lev"),
    "Ukraine": ("UAH", "₴", "Ukrainian Hryvnia"),
    "Russia": ("RUB", "₽", "Russian Ruble"),
    "Serbia": ("RSD", "din", "Serbian Dinar"),
    "Iceland": ("ISK", "kr", "Icelandic Króna"),

    # Americas
    "United States": ("USD", "$", "US Dollar"),
    "USA": ("USD", "$", "US Dollar"),
    "Canada": ("CAD", "C$", "Canadian Dollar"),
    "Mexico": ("MXN", "$", "Mexican Peso"),
    "Brazil": ("BRL", "R$", "Brazilian Real"),
    "Argentina": ("ARS", "$", "Argentine Peso"),
    "Colombia": ("COP", "$", "Colombian Peso"),
    "Chile": ("CLP", "$", "Chilean Peso"),
    "Peru": ("PEN", "S/.", "Peruvian Sol"),
    "Venezuela": ("VES", "Bs.", "Venezuelan Bolívar"),
    "Ecuador": ("USD", "$", "US Dollar"),
    "Uruguay": ("UYU", "$U", "Uruguayan Peso"),
    "Paraguay": ("PYG", "₲", "Paraguayan Guarani"),
    "Bolivia": ("BOB", "Bs.", "Bolivian Boliviano"),
    "Costa Rica": ("CRC", "₡", "Costa Rican Colón"),
    "Panama": ("USD", "$", "US Dollar"),
    "Jamaica": ("JMD", "J$", "Jamaican Dollar"),
    "Trinidad and Tobago": ("TTD", "TT$", "Trinidad Dollar"),

    # Africa
    "Nigeria": ("NGN", "₦", "Nigerian Naira"),
    "South Africa": ("ZAR", "R", "South African Rand"),
    "Kenya": ("KES", "KSh", "Kenyan Shilling"),
    "Ghana": ("GHS", "₵", "Ghanaian Cedi"),
    "Egypt": ("EGP", "E£", "Egyptian Pound"),
    "Morocco": ("MAD", "MAD", "Moroccan Dirham"),
    "Tanzania": ("TZS", "TSh", "Tanzanian Shilling"),
    "Ethiopia": ("ETB", "Br", "Ethiopian Birr"),
    "Uganda": ("UGX", "USh", "Ugandan Shilling"),
    "Rwanda": ("RWF", "RF", "Rwandan Franc"),
    "Senegal": ("XOF", "CFA", "West African CFA Franc"),
    "Ivory Coast": ("XOF", "CFA", "West African CFA Franc"),
    "Cameroon": ("XAF", "FCFA", "Central African CFA Franc"),
    "Tunisia": ("TND", "DT", "Tunisian Dinar"),
    "Algeria": ("DZD", "د.ج", "Algerian Dinar"),
    "Zimbabwe": ("ZWL", "Z$", "Zimbabwean Dollar"),
    "Mozambique": ("MZN", "MT", "Mozambican Metical"),
    "Angola": ("AOA", "Kz", "Angolan Kwanza"),

    # Oceania
    "Australia": ("AUD", "A$", "Australian Dollar"),
    "New Zealand": ("NZD", "NZ$", "New Zealand Dollar"),
    "Fiji": ("FJD", "FJ$", "Fijian Dollar"),
    "Papua New Guinea": ("PGK", "K", "Papua New Guinean Kina"),
}

# Default fallback
DEFAULT_CURRENCY = ("USD", "$", "US Dollar")


def get_currency_for_country(country: Optional[str]) -> Tuple[str, str, str]:
    """
    Get (currency_code, symbol, name) for a country name.
    Falls back to USD if country is None or not found.
    """
    if not country:
        return DEFAULT_CURRENCY

    # Try exact match first
    result = COUNTRY_CURRENCY_MAP.get(country)
    if result:
        return result

    # Case-insensitive match
    country_lower = country.lower().strip()
    for key, value in COUNTRY_CURRENCY_MAP.items():
        if key.lower() == country_lower:
            return value

    # Partial match (e.g. "United States of America" → "United States")
    for key, value in COUNTRY_CURRENCY_MAP.items():
        if key.lower() in country_lower or country_lower in key.lower():
            return value

    return DEFAULT_CURRENCY


async def convert_usdc_to_local(
    amount_usdc: float,
    currency_code: str,
) -> Tuple[float, float]:
    """
    Convert a USDC amount to local currency.

    Returns (local_amount, exchange_rate).
    Rate = how many local currency units per 1 USDC.
    """
    if currency_code == "USD":
        return amount_usdc, 1.0

    try:
        price_service = get_price_service()
        # USDC ≈ 1 USD, so we just need USD → local rate
        rate = await price_service.get_fiat_rate("USD", currency_code)
        local_amount = float(
            (Decimal(str(amount_usdc)) * rate).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        )
        return local_amount, float(rate)
    except Exception as e:
        logger.error(f"Currency conversion error ({currency_code}): {e}")
        return amount_usdc, 1.0


async def build_local_amount(
    amount_usdc: float,
    currency_code: str,
    currency_symbol: str,
) -> dict:
    """
    Build a dict with both USDC and local currency representation.

    Returns:
        {
            "amount_usdc": 50.0,
            "amount_local": 4150.00,
            "local_currency": "INR",
            "local_symbol": "₹",
            "exchange_rate": 83.0,
            "display_local": "₹4,150.00"
        }
    """
    local_amount, rate = await convert_usdc_to_local(amount_usdc, currency_code)

    # Format display string
    if currency_code == "JPY" or currency_code == "KRW":
        display = f"{currency_symbol}{local_amount:,.0f}"
    else:
        display = f"{currency_symbol}{local_amount:,.2f}"

    return {
        "amount_usdc": round(amount_usdc, 8),
        "amount_local": local_amount,
        "local_currency": currency_code,
        "local_symbol": currency_symbol,
        "exchange_rate": rate,
        "display_local": display,
    }
