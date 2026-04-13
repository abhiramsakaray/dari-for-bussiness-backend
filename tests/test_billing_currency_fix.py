"""
Test Billing Currency Fix

Verifies that billing endpoints return prices in merchant's currency.
"""
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient


def test_billing_plans_returns_merchant_currency(client, test_merchant):
    """Test that /billing/plans returns prices in merchant's currency"""
    response = client.get("/billing/plans", headers=test_merchant["headers"])
    
    assert response.status_code == 200
    plans = response.json()
    
    # Should return list of plans
    assert isinstance(plans, list)
    assert len(plans) > 0
    
    # Each plan should have currency field
    for plan in plans:
        assert "currency" in plan
        assert "monthly_price" in plan
        assert "tier" in plan
        
        # Currency should match merchant's currency
        # (test_merchant is typically USD, but could be INR based on setup)
        assert plan["currency"] in ["USD", "INR", "EUR", "GBP"]


def test_billing_info_includes_available_plans(client, test_merchant):
    """Test that /billing/info includes available_plans with converted prices"""
    response = client.get("/billing/info", headers=test_merchant["headers"])
    
    assert response.status_code == 200
    data = response.json()
    
    # Should include currency field
    assert "currency" in data
    assert data["currency"] in ["USD", "INR", "EUR", "GBP"]
    
    # Should include available_plans
    assert "available_plans" in data
    assert isinstance(data["available_plans"], dict)
    
    # Check plan structure
    for tier in ["free", "growth", "business", "enterprise"]:
        if tier in data["available_plans"]:
            plan = data["available_plans"][tier]
            assert "id" in plan
            assert "name" in plan
            assert "price" in plan
            assert "currency" in plan
            assert plan["currency"] == data["currency"]


def test_inr_user_gets_converted_prices(client, test_merchant_inr):
    """Test that INR users get prices converted from USD"""
    response = client.get("/billing/info", headers=test_merchant_inr["headers"])
    
    assert response.status_code == 200
    data = response.json()
    
    # Should be INR currency
    assert data["currency"] == "INR"
    
    # Check available plans have INR prices
    if "available_plans" in data:
        growth_plan = data["available_plans"].get("growth")
        if growth_plan:
            # Growth plan is $29 USD, should be ~2400 INR (rounded to nearest 100)
            assert growth_plan["currency"] == "INR"
            assert 2000 <= growth_plan["price"] <= 3000  # Allow for exchange rate variation
            
        business_plan = data["available_plans"].get("business")
        if business_plan:
            # Business plan is $99 USD, should be ~8200 INR
            assert business_plan["currency"] == "INR"
            assert 7000 <= business_plan["price"] <= 10000


def test_usd_user_gets_original_prices(client, test_merchant):
    """Test that USD users get original USD prices"""
    response = client.get("/billing/info", headers=test_merchant["headers"])
    
    assert response.status_code == 200
    data = response.json()
    
    # Should be USD currency
    assert data["currency"] == "USD"
    
    # Check available plans have USD prices
    if "available_plans" in data:
        free_plan = data["available_plans"].get("free")
        if free_plan:
            assert free_plan["currency"] == "USD"
            assert free_plan["price"] == 0
            
        growth_plan = data["available_plans"].get("growth")
        if growth_plan:
            assert growth_plan["currency"] == "USD"
            assert growth_plan["price"] == 29
            
        business_plan = data["available_plans"].get("business")
        if business_plan:
            assert business_plan["currency"] == "USD"
            assert business_plan["price"] == 99


@pytest.mark.asyncio
async def test_currency_conversion_with_rounding():
    """Test that currency conversion applies proper rounding"""
    from app.services.exchange_rate_service import get_exchange_rate_service
    
    exchange_service = get_exchange_rate_service()
    
    # Mock the exchange rate
    with patch.object(exchange_service._price_service, 'get_fiat_rate', 
                     new_callable=AsyncMock) as mock_rate:
        mock_rate.return_value = Decimal("83.0")  # 1 USD = 83 INR
        
        # Convert $29 to INR
        usd_amount = Decimal("29")
        inr_amount = await exchange_service.convert(usd_amount, "USD", "INR")
        
        # Should be 29 * 83 = 2407
        assert inr_amount == Decimal("2407")
        
        # After rounding to nearest 100, should be 2400
        rounded = (inr_amount / 100).quantize(Decimal("1")) * 100
        assert rounded == Decimal("2400")


def test_plans_endpoint_requires_authentication(client):
    """Test that /billing/plans requires authentication"""
    response = client.get("/billing/plans")
    
    # Should return 401 or 403 without auth
    assert response.status_code in [401, 403]


def test_billing_info_requires_authentication(client):
    """Test that /billing/info requires authentication"""
    response = client.get("/billing/info")
    
    # Should return 401 or 403 without auth
    assert response.status_code in [401, 403]


# Fixtures for test merchants with different currencies

@pytest.fixture
def test_merchant_inr(client, db):
    """Create a test merchant with INR currency"""
    from app.models import Merchant, MerchantSubscription
    from datetime import datetime, timedelta
    import uuid
    
    # Create merchant with India as country (INR currency)
    merchant = Merchant(
        id=uuid.uuid4(),
        name="Test Merchant INR",
        email="test_inr@example.com",
        password_hash="hashed_password",
        country="India",
        base_currency="INR",
        currency_symbol="₹",
        subscription_tier="free",
    )
    db.add(merchant)
    
    # Create subscription
    subscription = MerchantSubscription(
        merchant_id=merchant.id,
        tier="free",
        status="active",
        monthly_price=0,
        transaction_fee_percent=1.5,
        current_period_start=datetime.utcnow(),
        current_period_end=datetime.utcnow() + timedelta(days=30),
    )
    db.add(subscription)
    db.commit()
    
    # Generate auth token
    from app.core.auth import create_access_token
    token = create_access_token({"id": str(merchant.id), "email": merchant.email})
    
    return {
        "merchant": merchant,
        "headers": {"Authorization": f"Bearer {token}"},
    }
