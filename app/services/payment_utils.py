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


# Mapping from token symbol to Merchant balance column name
BALANCE_COLUMNS = {
    "USDC": "balance_usdc",
    "USDT": "balance_usdt",
    "PYUSD": "balance_pyusd",
}


def credit_merchant_balance(db, merchant_id, token: str, amount) -> None:
    """
    Credit a merchant's balance after a confirmed payment.

    Args:
        db: SQLAlchemy session
        merchant_id: Merchant UUID
        token: Token symbol (USDC, USDT, PYUSD)
        amount: Amount to credit (string, float, or Decimal)
    """
    from app.models.models import Merchant

    col_name = BALANCE_COLUMNS.get(token.upper())
    if not col_name:
        logger.warning(f"Unknown token '{token}' – cannot credit merchant {merchant_id}")
        return

    merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    if not merchant:
        logger.warning(f"Merchant {merchant_id} not found – cannot credit balance")
        return

    current = getattr(merchant, col_name, None) or Decimal("0")
    credit = Decimal(str(amount))
    setattr(merchant, col_name, current + credit)
    db.commit()
    logger.info(
        f"💰 Credited {credit} {token} to merchant {merchant_id} "
        f"(new {col_name}={current + credit})"
    )
