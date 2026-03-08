import secrets
import string
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)


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


def update_merchant_volume(db, merchant_id, amount_fiat: Decimal) -> None:
    """
    Increment the merchant's subscription volume by amount_fiat (the full
    original order amount, before any coupon discount).
    """
    from app.models.models import MerchantSubscription
    sub = (
        db.query(MerchantSubscription)
        .filter(MerchantSubscription.merchant_id == merchant_id)
        .first()
    )
    if sub:
        sub.current_volume = (sub.current_volume or Decimal("0")) + amount_fiat
        db.commit()
        logger.info(f"Updated volume for merchant {merchant_id}: +{amount_fiat} → {sub.current_volume}")
    else:
        logger.warning(f"No subscription found for merchant {merchant_id}, skipping volume update")
