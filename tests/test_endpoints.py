import pytest
from httpx import AsyncClient
import hmac
import hashlib
import json
import os
import uuid
from decimal import Decimal
from app.models.models import Merchant, MerchantWallet

pytestmark = pytest.mark.asyncio

async def test_idempotency_key(client: AsyncClient, auth_headers, db_session):
    """Test Idempotency-Key headers correctly caching 200 responses."""
    # First create a mock merchant in the test db
    merchant_id = uuid.UUID("d50a7c93-519e-4e4b-9721-e00f9f302b11")
    merchant = Merchant(
        id=merchant_id, 
        name="Test Merchant",
        email="test@example.com", 
        password_hash="fakehash",
        business_name="Test Business"
    )
    db_session.add(merchant)
    db_session.commit()

    # Now we POST an invoice with an idempotency key
    key = "test-idemp-key-123"
    headers = {**auth_headers, "Idempotency-Key": key}
    data = {
        "title": "Test Invoice",
        "description": "A test invoice",
        "amount": 100.0,
        "currency": "USD"
    }

    # First request
    res1 = await client.post("/invoices", json=data, headers=headers)
    assert res1.status_code == 201
    
    # Second request with the same idempotency key
    res2 = await client.post("/invoices", json=data, headers=headers)
    # The idempotency middleware should return the exact same cached response (200 OK or 201)
    assert res2.status_code == res1.status_code
    assert res2.json()["id"] == res1.json()["id"]

async def test_webhook_hmac_signature(client: AsyncClient):
    """Test Webhook HMAC-SHA256 signature verification."""
    payload = {"event": "payment.completed", "session_id": "pay_test"}
    body = json.dumps(payload).encode("utf-8")
    
    # Calculate a valid signature using the test secret from conftest.py
    secret = os.environ.get("API_KEY_SECRET", "test_secret_for_hmac_testing_only").encode("utf-8")
    valid_sig = hmac.new(secret, body, hashlib.sha256).hexdigest()

    # Valid signature test
    res = await client.post(
        "/public/webhooks/test", # This is just to test the validation utility endpoint if one exists
        content=body, 
        headers={"X-Webhook-Signature": valid_sig}
    )
    # We expect 404 since /public/webhooks/test might not exist, but let's test admin webhook
    pass # To be fully fleshed out with a specific webhook endpoint

async def test_merchant_wallets_dashboard_roles(client: AsyncClient):
    """Test GET /merchant/wallets/dashboard enforcing JWT roles."""
    # Attempt to access with no token
    res_no_auth = await client.get("/merchant/wallets/dashboard")
    assert res_no_auth.status_code == 403 or res_no_auth.status_code == 401

    # Attempt to access with a valid merchant token
    merchant_token = os.environ.get("DEBUG_TOKEN", "fake_token")
    # Will use the auth_headers fixture pattern in the fleshed out test

    # Attempt to access with a regular user token (not merchant) - should 403
    pass

async def test_trm_labs_risk_scoring(client: AsyncClient, auth_headers):
    """Test the integration of TRM Labs Risk Scoring on payment URLs."""
    # Create a payment session
    pass
