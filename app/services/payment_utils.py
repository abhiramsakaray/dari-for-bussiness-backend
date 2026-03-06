import secrets
import string
from decimal import Decimal


def generate_session_id() -> str:
    """Generate a unique payment session ID in the format 'pay_xxx'."""
    random_part = ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(16))
    return f"pay_{random_part}"


def convert_fiat_to_usdc(amount: Decimal, currency: str) -> str:
    """
    Convert fiat amount to USDC.
    
    This is a simplified conversion. In production, you would:
    - Use a real-time exchange rate API
    - Handle multiple currencies properly
    - Consider slippage and fees
    """
    # Mock exchange rates (1 USDC = 1 USD for simplification)
    exchange_rates = {
        "USD": Decimal("1.0"),
        "INR": Decimal("0.012"),  # 1 INR ≈ 0.012 USD
        "EUR": Decimal("1.1"),
        "GBP": Decimal("1.27"),
    }
    
    rate = exchange_rates.get(currency.upper(), Decimal("1.0"))
    usdc_amount = amount * rate
    
    # Return as string with 2 decimal places
    return f"{usdc_amount:.2f}"
