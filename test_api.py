#!/usr/bin/env python3
"""
Quick test script for the payment gateway API.
"""
import requests
import json

BASE_URL = "http://localhost:8000"


def test_merchant_flow():
    """Test the complete merchant flow."""
    print("=" * 60)
    print("Testing Merchant Flow")
    print("=" * 60)
    
    # 1. Register merchant
    print("\n1. Registering merchant...")
    register_data = {
        "name": "Test Store",
        "email": "test@store.com",
        "password": "password123"
    }
    
    response = requests.post(f"{BASE_URL}/auth/register", json=register_data)
    print(f"Status: {response.status_code}")
    
    if response.status_code == 201:
        token = response.json()["access_token"]
        print(f"✅ Merchant registered successfully")
        print(f"Token: {token[:50]}...")
    else:
        print(f"❌ Registration failed: {response.text}")
        return
    
    # 2. Update profile with Stellar address
    print("\n2. Setting Stellar address...")
    headers = {"Authorization": f"Bearer {token}"}
    profile_data = {
        "stellar_address": "GABC123EXAMPLE456",
        "webhook_url": "https://webhook.site/test"
    }
    
    response = requests.put(f"{BASE_URL}/merchant/profile", json=profile_data, headers=headers)
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        print(f"✅ Profile updated")
        print(json.dumps(response.json(), indent=2))
    else:
        print(f"❌ Update failed: {response.text}")
        return
    
    # 3. Create payment session
    print("\n3. Creating payment session...")
    payment_data = {
        "amount": 1999,
        "currency": "INR",
        "success_url": "https://store.com/success",
        "cancel_url": "https://store.com/cancel"
    }
    
    response = requests.post(f"{BASE_URL}/v1/payment_sessions", json=payment_data, headers=headers)
    print(f"Status: {response.status_code}")
    if response.status_code == 201:
        session = response.json()
        print(f"✅ Payment session created")
        print(json.dumps(session, indent=2))
        
        session_id = session["session_id"]
        
        # 4. Check payment status
        print(f"\n4. Checking payment status...")
        response = requests.get(f"{BASE_URL}/v1/payment_sessions/{session_id}")
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            print(f"✅ Payment status retrieved")
            print(json.dumps(response.json(), indent=2))
        
        print(f"\n🌐 Checkout URL: {session['checkout_url']}")
        print(f"   Open this URL in your browser to see the hosted checkout page")
    else:
        print(f"❌ Payment creation failed: {response.text}")


def test_admin_login():
    """Test admin login and endpoints."""
    print("\n" + "=" * 60)
    print("Testing Admin Flow")
    print("=" * 60)
    
    # 1. Admin login
    print("\n1. Admin login...")
    login_data = {
        "email": "admin@paymentgateway.com",
        "password": "admin123456"
    }
    
    response = requests.post(f"{BASE_URL}/auth/login", json=login_data)
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        token = response.json()["access_token"]
        print(f"✅ Admin logged in")
        
        headers = {"Authorization": f"Bearer {token}"}
        
        # 2. View merchants
        print("\n2. Viewing all merchants...")
        response = requests.get(f"{BASE_URL}/admin/merchants", headers=headers)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            merchants = response.json()
            print(f"✅ Found {len(merchants)} merchant(s)")
            for m in merchants[:3]:  # Show first 3
                print(f"   - {m['name']} ({m['email']})")
        
        # 3. View payments
        print("\n3. Viewing all payments...")
        response = requests.get(f"{BASE_URL}/admin/payments", headers=headers)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            payments = response.json()
            print(f"✅ Found {len(payments)} payment(s)")
            for p in payments[:3]:  # Show first 3
                print(f"   - {p['id']}: {p['amount_usdc']} USDC ({p['status']})")
        
        # 4. Health check
        print("\n4. Checking gateway health...")
        response = requests.get(f"{BASE_URL}/admin/health", headers=headers)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            health = response.json()
            print(f"✅ Gateway health:")
            print(json.dumps(health, indent=2))
    else:
        print(f"❌ Admin login failed: {response.text}")


def main():
    """Run all tests."""
    print("\n🚀 Dari for Business - Multi-Chain Payment Gateway - Quick Test\n")
    
    # Check if server is running
    try:
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code == 200:
            print("✅ Server is running\n")
        else:
            print("⚠️  Server returned unexpected status\n")
    except requests.exceptions.ConnectionError:
        print("❌ Server is not running!")
        print("   Please start the server first: uvicorn app.main:app --reload\n")
        return
    
    # Run tests
    test_merchant_flow()
    test_admin_login()
    
    print("\n" + "=" * 60)
    print("✅ All tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
