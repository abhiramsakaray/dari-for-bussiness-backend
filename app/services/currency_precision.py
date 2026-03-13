"""
Currency Precision Service

Handles correct decimal precision for every currency type:
  - Fiat: USD (2), EUR (2), JPY (0), KWD (3), etc.
  - Crypto: USDC (6), USDT (6), BTC (8), ETH (18), etc.

Provides formatting and rounding utilities.
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

# ── Fiat precision map (ISO 4217) ──
FIAT_PRECISION: dict[str, int] = {
    "USD": 2, "EUR": 2, "GBP": 2, "INR": 2, "AUD": 2, "CAD": 2,
    "CHF": 2, "CNY": 2, "HKD": 2, "SGD": 2, "MXN": 2, "BRL": 2,
    "ZAR": 2, "SEK": 2, "NOK": 2, "DKK": 2, "NZD": 2, "THB": 2,
    "PHP": 2, "MYR": 2, "IDR": 0, "KRW": 0,
    "JPY": 0, "VND": 0, "CLP": 0,
    "KWD": 3, "BHD": 3, "OMR": 3,
}

# ── Crypto / stablecoin precision ──
CRYPTO_PRECISION: dict[str, int] = {
    "USDC": 6, "USDT": 6, "PYUSD": 6,
    "BTC": 8, "ETH": 18, "SOL": 9,
    "XLM": 7, "TRX": 6, "MATIC": 18,
}

# Default precisions
_DEFAULT_FIAT_PRECISION = 2
_DEFAULT_CRYPTO_PRECISION = 6


def get_precision(currency: str) -> int:
    """Get the correct decimal precision for a currency code."""
    upper = currency.upper()
    if upper in CRYPTO_PRECISION:
        return CRYPTO_PRECISION[upper]
    if upper in FIAT_PRECISION:
        return FIAT_PRECISION[upper]
    # Heuristic: 3-letter uppercase → fiat
    return _DEFAULT_FIAT_PRECISION


def round_amount(amount: Decimal, currency: str) -> Decimal:
    """Round an amount to the correct precision for the currency."""
    precision = get_precision(currency)
    if precision == 0:
        return amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    quantizer = Decimal(10) ** -precision
    return amount.quantize(quantizer, rounding=ROUND_HALF_UP)


def format_amount(amount: Decimal, currency: str) -> str:
    """Format amount as a string with correct decimal places."""
    rounded = round_amount(amount, currency)
    precision = get_precision(currency)
    if precision == 0:
        return str(int(rounded))
    return f"{rounded:.{precision}f}"


def is_fiat(currency: str) -> bool:
    """Check if a currency code is fiat (vs crypto)."""
    return currency.upper() in FIAT_PRECISION or (
        currency.upper() not in CRYPTO_PRECISION and len(currency) == 3
    )


def validate_amount(
    amount: Decimal,
    currency: str,
    min_amount: Optional[Decimal] = None,
    max_amount: Optional[Decimal] = None,
) -> tuple[bool, str]:
    """
    Validate that an amount meets precision and range constraints.

    Returns (is_valid, error_message).
    """
    if amount <= 0:
        return False, "Amount must be positive"

    precision = get_precision(currency)
    # Check that the amount doesn't have more decimal places than allowed
    if precision == 0:
        if amount != amount.to_integral_value():
            return False, f"{currency} does not support decimal places"
    else:
        quantizer = Decimal(10) ** -precision
        if amount.quantize(quantizer, rounding=ROUND_HALF_UP) != amount:
            return False, f"{currency} supports at most {precision} decimal places"

    if min_amount is not None and amount < min_amount:
        return False, f"Amount below minimum ({min_amount})"
    if max_amount is not None and amount > max_amount:
        return False, f"Amount above maximum ({max_amount})"

    return True, ""
