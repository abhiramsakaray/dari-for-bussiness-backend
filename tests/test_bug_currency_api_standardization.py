"""
Bug Condition Exploration Test: Inconsistent Currency Response Structures

**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10**

This test encodes the EXPECTED behavior (standardized MonetaryAmount structure).
It MUST FAIL on unfixed code to confirm the bug exists.

The test verifies that all 9 affected API endpoints return standardized MonetaryAmount
structures with required fields: amount, currency, symbol, formatted display string,
and consistent exchange rates across multiple calls within the same session.

CRITICAL: This test is EXPECTED TO FAIL on unfixed code.
Failure confirms the bug exists and surfaces counterexamples.
"""

import pytest
from hypothesis import given, strategies as st, settings, HealthCheck
from fastapi.testclient import TestClient
from decimal import Decimal
from typing import Dict, Any, List
import time

from app.main import app
from app.core.database import get_db
from app.models.models import Merchant, PaymentSession, Invoice, Subscription, SubscriptionPlan
from sqlalchemy.orm import Session


# ============= TEST FIXTURES =============

@pytest.fixture
def client():
    """Test client for API calls"""
    return TestClient(app)


@pytest.fixture
def test_merchant(client):
    """Create a test merchant with authentication"""
    # Register merchant
    register_data = {
        "name": "Test Merchant",
        "email": f"test_{int(time.time())}@example.com",
        "password": "testpass123",
        "merchant_category": "individual"
    }
    response = client.post("/v1/auth/register", json=register_data)
    assert response.status_code == 201
    
    # Login to get token
    login_data = {
        "email": register_data["email"],
        "password": register_data["password"]
    }
    response = client.post("/v1/auth/login", json=login_data)
    assert response.status_code == 200
    token_data = response.json()
    
    return {
        "email": register_data["email"],
        "token": token_data["access_token"],
        "merchant_id": token_data.get("merchant_id"),
        "headers": {"Authorization": f"Bearer {token_data['access_token']}"}
    }


# ============= HELPER FUNCTIONS =============

def has_standardized_monetary_amount(response_data: Dict[str, Any], field_name: str) -> bool:
    """
    Check if a response field contains a standardized MonetaryAmount structure.
    
    Required fields:
    - amount: Decimal value
    - currency: Currency code (USD, EUR, etc.)
    - symbol: Currency symbol ($, €, etc.)
    - formatted: Pre-formatted display string (e.g., "$1,234.56")
    """
    if field_name not in response_data:
        return False
    
    field = response_data[field_name]
    
    # Check if it's a MonetaryAmount object (dict with required fields)
    if not isinstance(field, dict):
        return False
    
    required_fields = ["amount", "currency", "symbol", "formatted"]
    return all(key in field for key in required_fields)


def has_currency_metadata(response_data: Dict[str, Any]) -> bool:
    """Check if response contains proper currency metadata"""
    # Check for old inconsistent field names (bug condition)
    has_old_fields = any(key in response_data for key in ["amount_fiat", "amount_usdc", "amount_local"])
    
    # Check for missing metadata
    if "currency" in response_data:
        has_symbol = "currency_symbol" in response_data or "symbol" in response_data
        has_formatted = "formatted" in response_data or "display" in response_data
        return has_symbol and has_formatted
    
    return False


def extract_exchange_rate(response_data: Dict[str, Any]) -> float:
    """Extract exchange rate from response for consistency checking"""
    # Try to find exchange rate in various possible locations
    if "exchange_rate" in response_data:
        return float(response_data["exchange_rate"])
    
    if "merchant_exchange_rate" in response_data:
        return float(response_data["merchant_exchange_rate"])
    
    if "payer_exchange_rate" in response_data:
        return float(response_data["payer_exchange_rate"])
    
    # Try to calculate from amounts if available
    if "amount_local" in response_data and "amount_usdc" in response_data:
        amount_local = float(response_data["amount_local"])
        amount_usdc = float(response_data["amount_usdc"])
        if amount_usdc > 0:
            return amount_local / amount_usdc
    
    return 1.0  # Default if not found


# ============= PROPERTY-BASED TESTS =============

@settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow]
)
@given(
    amount=st.decimals(min_value=Decimal("10.00"), max_value=Decimal("10000.00"), places=2),
    currency=st.sampled_from(["USD", "EUR", "GBP", "INR", "JPY"])
)
def test_property_1_analytics_overview_standardized_response(client, test_merchant, amount, currency):
    """
    Property 1: Analytics Overview API returns standardized MonetaryAmount structure
    
    **Validates: Requirements 1.1, 2.1**
    
    EXPECTED OUTCOME: This test FAILS on unfixed code (proves bug exists)
    
    The test verifies that /analytics/overview returns MonetaryAmount objects
    with amount, currency, symbol, and formatted display string.
    """
    # Call analytics overview endpoint
    response = client.get(
        "/analytics/overview?period=month",
        headers=test_merchant["headers"]
    )
    
    assert response.status_code == 200, f"Analytics overview failed: {response.text}"
    data = response.json()
    
    # Property: Response must contain standardized MonetaryAmount for monetary fields
    monetary_fields = ["total_volume", "invoice_volume", "subscription_mrr"]
    
    for field in monetary_fields:
        if field in data:
            # Check for standardized structure
            assert has_standardized_monetary_amount(data, field), \
                f"Field '{field}' lacks standardized MonetaryAmount structure. " \
                f"Expected: {{amount, currency, symbol, formatted}}, Got: {data.get(field)}"
    
    # Property: Must not use old inconsistent field names
    old_field_names = ["amount_fiat", "amount_usdc", "amount_local"]
    for old_field in old_field_names:
        assert old_field not in data, \
            f"Response contains deprecated field '{old_field}'. Should use MonetaryAmount structure."


@settings(
    max_examples=15,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow]
)
@given(
    amount=st.decimals(min_value=Decimal("5.00"), max_value=Decimal("1000.00"), places=2)
)
def test_property_2_payment_session_consistent_structure(client, test_merchant, amount):
    """
    Property 2: Payment Session APIs return consistent MonetaryAmount structures
    
    **Validates: Requirements 1.2, 2.2**
    
    EXPECTED OUTCOME: This test FAILS on unfixed code (proves bug exists)
    
    The test verifies that payment session creation and retrieval return
    consistent MonetaryAmount structures across multiple calls.
    """
    # Create payment session
    session_data = {
        "amount": float(amount),
        "currency": "USD",
        "success_url": "https://example.com/success",
        "cancel_url": "https://example.com/cancel"
    }
    
    create_response = client.post(
        "/v1/payment_sessions",
        json=session_data,
        headers=test_merchant["headers"]
    )
    
    assert create_response.status_code == 201, f"Payment session creation failed: {create_response.text}"
    create_data = create_response.json()
    
    # Property: Created session must have standardized amount structure
    assert "amount" in create_data, "Payment session response missing 'amount' field"
    
    # If amount is a dict, it should be a MonetaryAmount
    if isinstance(create_data["amount"], dict):
        assert has_standardized_monetary_amount(create_data, "amount"), \
            f"Payment session 'amount' lacks MonetaryAmount structure. Got: {create_data['amount']}"
    
    # Get session status
    session_id = create_data["session_id"]
    status_response = client.get(
        f"/v1/payment_sessions/{session_id}",
        headers=test_merchant["headers"]
    )
    
    assert status_response.status_code == 200, f"Get session status failed: {status_response.text}"
    status_data = status_response.json()
    
    # Property: Status response must have consistent structure with creation response
    assert "amount" in status_data or "amount_usdc" in status_data, \
        "Payment session status missing amount field"
    
    # Property: Must not mix field names (amount_usdc, amount_fiat, amount_local)
    mixed_fields = sum(1 for f in ["amount_usdc", "amount_fiat", "amount_local"] if f in status_data)
    assert mixed_fields <= 1, \
        f"Payment session uses mixed field names: {[f for f in ['amount_usdc', 'amount_fiat', 'amount_local'] if f in status_data]}"


@settings(
    max_examples=10,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow]
)
@given(
    subtotal=st.decimals(min_value=Decimal("50.00"), max_value=Decimal("5000.00"), places=2),
    tax=st.decimals(min_value=Decimal("0.00"), max_value=Decimal("500.00"), places=2)
)
def test_property_3_invoice_preformatted_display(client, test_merchant, subtotal, tax):
    """
    Property 3: Invoice APIs include pre-formatted display strings
    
    **Validates: Requirements 1.3, 2.3**
    
    EXPECTED OUTCOME: This test FAILS on unfixed code (proves bug exists)
    
    The test verifies that invoice responses include MonetaryAmount objects
    with pre-formatted display strings for all monetary fields.
    """
    # Create invoice
    invoice_data = {
        "customer_email": "customer@example.com",
        "customer_name": "Test Customer",
        "line_items": [
            {
                "description": "Test Item",
                "quantity": 1,
                "unit_price": float(subtotal)
            }
        ],
        "tax": float(tax),
        "discount": 0.0,
        "due_date": "2024-12-31T23:59:59Z"
    }
    
    response = client.post(
        "/invoices",
        json=invoice_data,
        headers=test_merchant["headers"]
    )
    
    assert response.status_code == 200, f"Invoice creation failed: {response.text}"
    data = response.json()
    
    # Property: All monetary fields must have formatted display strings
    monetary_fields = ["subtotal", "tax", "discount", "total"]
    
    for field in monetary_fields:
        if field in data:
            field_value = data[field]
            
            # If it's a MonetaryAmount object, check for formatted field
            if isinstance(field_value, dict):
                assert "formatted" in field_value, \
                    f"Invoice field '{field}' missing 'formatted' display string. Got: {field_value}"
            else:
                # If it's a raw number, it should be wrapped in MonetaryAmount
                assert False, \
                    f"Invoice field '{field}' is raw number {field_value}, should be MonetaryAmount with formatted string"


@settings(
    max_examples=10,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow]
)
@given(
    plan_amount=st.decimals(min_value=Decimal("10.00"), max_value=Decimal("500.00"), places=2)
)
def test_property_4_subscription_standardized_pricing(client, test_merchant, plan_amount):
    """
    Property 4: Subscription APIs return standardized MonetaryAmount for pricing
    
    **Validates: Requirements 1.4, 2.4**
    
    EXPECTED OUTCOME: This test FAILS on unfixed code (proves bug exists)
    
    The test verifies that subscription plan responses use MonetaryAmount
    structures for all pricing fields.
    """
    # Create subscription plan
    plan_data = {
        "name": f"Test Plan {int(time.time())}",
        "description": "Test subscription plan",
        "amount": float(plan_amount),
        "interval": "monthly",
        "trial_days": 0
    }
    
    response = client.post(
        "/subscriptions/plans",
        json=plan_data,
        headers=test_merchant["headers"]
    )
    
    assert response.status_code == 200, f"Subscription plan creation failed: {response.text}"
    data = response.json()
    
    # Property: Pricing fields must use MonetaryAmount structure
    pricing_fields = ["amount", "setup_fee", "trial_price"]
    
    for field in pricing_fields:
        if field in data and data[field] is not None:
            field_value = data[field]
            
            # If it's a MonetaryAmount object, verify structure
            if isinstance(field_value, dict):
                assert has_standardized_monetary_amount(data, field), \
                    f"Subscription field '{field}' lacks MonetaryAmount structure. Got: {field_value}"
            else:
                # Raw numbers should be wrapped in MonetaryAmount
                assert False, \
                    f"Subscription field '{field}' is raw number {field_value}, should be MonetaryAmount"


@settings(
    max_examples=10,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow]
)
def test_property_5_wallet_balance_merchant_currency(client, test_merchant):
    """
    Property 5: Wallet APIs return MonetaryAmount with merchant currency preference
    
    **Validates: Requirements 1.5, 2.5, 2.10**
    
    EXPECTED OUTCOME: This test FAILS on unfixed code (proves bug exists)
    
    The test verifies that wallet balance responses include MonetaryAmount
    objects in merchant's preferred currency with proper metadata.
    """
    # Get wallet balance
    response = client.get(
        "/merchant/wallets/balance",
        headers=test_merchant["headers"]
    )
    
    assert response.status_code == 200, f"Wallet balance failed: {response.text}"
    data = response.json()
    
    # Property: Balance fields must use MonetaryAmount structure
    balance_fields = ["total_balance_usdc", "net_available_usdc", "pending_withdrawals_usdc"]
    
    for field in balance_fields:
        if field in data:
            # Check if there's a corresponding _local field with MonetaryAmount
            local_field = field.replace("_usdc", "_local")
            
            if local_field in data:
                local_value = data[local_field]
                assert isinstance(local_value, dict), \
                    f"Wallet field '{local_field}' should be MonetaryAmount object, got: {type(local_value)}"
                
                # Verify MonetaryAmount structure
                required_fields = ["amount_local", "local_currency", "local_symbol", "display_local"]
                for req_field in required_fields:
                    assert req_field in local_value, \
                        f"Wallet MonetaryAmount missing '{req_field}'. Got: {local_value}"


@settings(
    max_examples=10,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow]
)
def test_property_6_withdrawal_fiat_equivalents(client, test_merchant):
    """
    Property 6: Withdrawal APIs include both token and fiat amounts in MonetaryAmount
    
    **Validates: Requirements 1.6, 2.6**
    
    EXPECTED OUTCOME: This test FAILS on unfixed code (proves bug exists)
    
    The test verifies that withdrawal responses include MonetaryAmount objects
    with both token amounts and fiat equivalents.
    """
    # Get withdrawal balance
    response = client.get(
        "/withdrawals/balance",
        headers=test_merchant["headers"]
    )
    
    assert response.status_code == 200, f"Withdrawal balance failed: {response.text}"
    data = response.json()
    
    # Property: Balance items must have MonetaryAmount with local currency
    if "balances" in data and len(data["balances"]) > 0:
        for balance_item in data["balances"]:
            # Check for MonetaryAmount structure in local fields
            local_fields = ["available_local", "net_available_local"]
            
            for field in local_fields:
                if field in balance_item:
                    local_value = balance_item[field]
                    assert isinstance(local_value, dict), \
                        f"Withdrawal field '{field}' should be MonetaryAmount, got: {type(local_value)}"
                    
                    # Verify it has currency metadata
                    assert "local_currency" in local_value or "currency" in local_value, \
                        f"Withdrawal MonetaryAmount missing currency field. Got: {local_value}"


@settings(
    max_examples=5,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow]
)
def test_property_7_consistent_exchange_rates_across_endpoints(client, test_merchant):
    """
    Property 7: Exchange rates are consistent across multiple endpoint calls
    
    **Validates: Requirements 1.8, 2.8**
    
    EXPECTED OUTCOME: This test FAILS on unfixed code (proves bug exists)
    
    The test verifies that when multiple API endpoints are called within the same
    session, they use consistent exchange rates from a centralized service.
    """
    # Call multiple endpoints and collect exchange rates
    exchange_rates = []
    
    # 1. Analytics overview
    response1 = client.get("/analytics/overview?period=month", headers=test_merchant["headers"])
    if response1.status_code == 200:
        rate1 = extract_exchange_rate(response1.json())
        exchange_rates.append(("analytics_overview", rate1))
    
    # 2. Wallet balance
    response2 = client.get("/merchant/wallets/balance", headers=test_merchant["headers"])
    if response2.status_code == 200:
        rate2 = extract_exchange_rate(response2.json())
        exchange_rates.append(("wallet_balance", rate2))
    
    # 3. Withdrawal balance
    response3 = client.get("/withdrawals/balance", headers=test_merchant["headers"])
    if response3.status_code == 200:
        rate3 = extract_exchange_rate(response3.json())
        exchange_rates.append(("withdrawal_balance", rate3))
    
    # Property: All exchange rates should be identical (or very close due to caching)
    if len(exchange_rates) >= 2:
        base_rate = exchange_rates[0][1]
        
        for endpoint, rate in exchange_rates[1:]:
            # Allow small floating point differences, but rates should be from same cache
            rate_diff = abs(rate - base_rate)
            assert rate_diff < 0.01, \
                f"Inconsistent exchange rates across endpoints: " \
                f"{exchange_rates[0][0]}={base_rate}, {endpoint}={rate}. " \
                f"Difference: {rate_diff}. Rates should be consistent within same session."


@settings(
    max_examples=10,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow]
)
def test_property_8_no_frontend_currency_formatting(client, test_merchant):
    """
    Property 8: All currency formatting is done server-side, not delegated to frontend
    
    **Validates: Requirements 1.7, 2.7**
    
    EXPECTED OUTCOME: This test FAILS on unfixed code (proves bug exists)
    
    The test verifies that API responses include pre-formatted display strings,
    eliminating the need for frontend to use Intl.NumberFormat.
    """
    # Call analytics overview
    response = client.get("/analytics/overview?period=month", headers=test_merchant["headers"])
    assert response.status_code == 200
    data = response.json()
    
    # Property: Monetary fields must include formatted display strings
    # Check if response has any monetary values
    has_monetary_data = any(key in data for key in ["total_volume", "invoice_volume", "subscription_mrr"])
    
    if has_monetary_data:
        # At least one monetary field should have a formatted string
        has_formatted = False
        
        for key, value in data.items():
            if isinstance(value, dict) and "formatted" in value:
                has_formatted = True
                # Verify formatted string looks like currency (contains symbol and number)
                formatted_str = value["formatted"]
                assert isinstance(formatted_str, str), \
                    f"Formatted field should be string, got: {type(formatted_str)}"
                assert len(formatted_str) > 0, "Formatted string is empty"
                break
        
        assert has_formatted, \
            "Response contains monetary data but no pre-formatted display strings. " \
            "Server should format currency, not delegate to frontend Intl.NumberFormat."


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
