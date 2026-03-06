# API Testing Guide

## Quick Start

### 1. Start the Server

```bash
# Terminal 1 - API Server
uvicorn app.main:app --reload

# Terminal 2 - Stellar Listener
python -m app.services.stellar_listener
```

### 2. Run Quick Test

```bash
python test_api.py
```

## Manual API Testing

### Using cURL

#### 1. Merchant Registration

```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Store",
    "email": "merchant@example.com",
    "password": "securepassword123"
  }'
```

Response:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

#### 2. Merchant Login

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "merchant@example.com",
    "password": "securepassword123"
  }'
```

#### 3. Update Profile (Set Stellar Address)

```bash
curl -X PUT http://localhost:8000/merchant/profile \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -d '{
    "stellar_address": "GABC123...",
    "webhook_url": "https://your-webhook-url.com/webhook"
  }'
```

#### 4. Create Payment Session

```bash
curl -X POST http://localhost:8000/v1/payment_sessions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -d '{
    "amount": 1999,
    "currency": "INR",
    "success_url": "https://yourstore.com/success",
    "cancel_url": "https://yourstore.com/cancel"
  }'
```

Response:
```json
{
  "session_id": "pay_abc123xyz",
  "checkout_url": "http://localhost:8000/checkout/pay_abc123xyz"
}
```

#### 5. Get Payment Status

```bash
curl http://localhost:8000/v1/payment_sessions/pay_abc123xyz
```

#### 6. Admin Login

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@paymentgateway.com",
    "password": "admin123456"
  }'
```

#### 7. View All Merchants (Admin)

```bash
curl http://localhost:8000/admin/merchants \
  -H "Authorization: Bearer ADMIN_TOKEN_HERE"
```

#### 8. View All Payments (Admin)

```bash
curl http://localhost:8000/admin/payments \
  -H "Authorization: Bearer ADMIN_TOKEN_HERE"
```

#### 9. Gateway Health (Admin)

```bash
curl http://localhost:8000/admin/health \
  -H "Authorization: Bearer ADMIN_TOKEN_HERE"
```

#### 10. Disable Merchant (Admin)

```bash
curl -X PATCH http://localhost:8000/admin/merchants/MERCHANT_ID/disable \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ADMIN_TOKEN_HERE" \
  -d '{
    "is_active": false
  }'
```

## Using Postman

### Import Collection

Create a new Postman collection with these requests:

#### Environment Variables

Create a Postman environment with:
- `base_url`: `http://localhost:8000`
- `merchant_token`: (will be set after login)
- `admin_token`: (will be set after login)

#### Collection Structure

```
Dari for Business - Multi-Chain Payment Gateway
│
├── Auth
│   ├── Merchant Register
│   └── Merchant Login
│
├── Merchant
│   ├── Get Profile
│   └── Update Profile
│
├── Payments
│   ├── Create Payment Session
│   └── Get Payment Status
│
├── Checkout
│   ├── Get Checkout Page
│   └── Get Checkout Details (JSON)
│
└── Admin
    ├── Admin Login
    ├── List Merchants
    ├── List Payments
    ├── Gateway Health
    └── Disable Merchant
```

## Testing Payment Flow End-to-End

### Step 1: Setup Stellar Testnet Wallet

1. **Create Freighter Wallet** or use Stellar Laboratory
2. **Get testnet XLM** from friendbot:
   ```bash
   curl "https://friendbot.stellar.org?addr=YOUR_STELLAR_ADDRESS"
   ```

3. **Add USDC trustline**:
   - Asset Code: `USDC`
   - Issuer: `GBBD47IF6LWK7P7MDEVSCWR7DPUWV3NY3DTQEVFL4NAT4AQH3ZLLFLA5`

4. **Get test USDC** (you may need to use a DEX or testnet faucet)

### Step 2: Create Merchant & Payment Session

```bash
# 1. Register
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Store",
    "email": "test@store.com",
    "password": "password123"
  }'

# Save the token from response

# 2. Set Stellar address (use YOUR address from Step 1)
curl -X PUT http://localhost:8000/merchant/profile \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "stellar_address": "YOUR_STELLAR_ADDRESS",
    "webhook_url": "https://webhook.site/your-unique-url"
  }'

# 3. Create payment session
curl -X POST http://localhost:8000/v1/payment_sessions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "amount": 100,
    "currency": "INR",
    "success_url": "https://example.com/success",
    "cancel_url": "https://example.com/cancel"
  }'

# Note the session_id and checkout_url
```

### Step 3: Open Checkout Page

Open the `checkout_url` in your browser. You'll see:
- Payment amount in USDC
- QR code
- Merchant Stellar address
- Payment memo (session_id)

### Step 4: Make Payment

Using Freighter Wallet or Stellar Laboratory:

1. **Send USDC to merchant address**
2. **Amount**: Use the exact amount shown on checkout page
3. **Memo Type**: TEXT
4. **Memo**: Use the session_id shown on checkout page

Example using Stellar Laboratory:
- Transaction Type: Payment
- Destination: (merchant address)
- Asset: USDC (with issuer)
- Amount: (from checkout page)
- Add Memo: TEXT, (session_id)

### Step 5: Verify Payment Detection

Watch the Stellar listener logs - you should see:
```
✅ Valid payment detected for session pay_xxx, tx: ABC123...
```

The checkout page should automatically:
1. Detect the payment
2. Show "Payment Confirmed"
3. Redirect to success_url

### Step 6: Verify Webhook

Check your webhook URL (e.g., webhook.site) - you should receive:

```json
{
  "event": "payment.success",
  "session_id": "pay_abc123",
  "amount": "1.20",
  "currency": "USDC",
  "tx_hash": "abc123..."
}
```

## Testing Webhook Integration

### Using webhook.site

1. Go to https://webhook.site
2. Copy your unique URL
3. Set it as your merchant webhook_url
4. Make a test payment
5. View the webhook payload on webhook.site

### Using Local Webhook Server

```python
# webhook_receiver.py
from flask import Flask, request
import json

app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    print("Received webhook:")
    print(json.dumps(data, indent=2))
    return {"status": "ok"}, 200

if __name__ == '__main__':
    app.run(port=5000)
```

```bash
# Install flask
pip install flask

# Run webhook receiver
python webhook_receiver.py

# Use http://localhost:5000/webhook as webhook_url
```

## Load Testing

### Using Apache Bench

```bash
# Install apache2-utils (Linux) or httpd (Mac)

# Test registration endpoint
ab -n 100 -c 10 -p register.json -T application/json \
   http://localhost:8000/auth/register

# register.json
{
  "name": "Test",
  "email": "test@example.com",
  "password": "password123"
}
```

### Using Python locust

```python
# locustfile.py
from locust import HttpUser, task, between

class PaymentGatewayUser(HttpUser):
    wait_time = between(1, 3)
    
    def on_start(self):
        # Login
        response = self.client.post("/auth/register", json={
            "name": "Test User",
            "email": f"user{self.user_id}@test.com",
            "password": "password123"
        })
        self.token = response.json()["access_token"]
    
    @task
    def get_profile(self):
        self.client.get("/merchant/profile", headers={
            "Authorization": f"Bearer {self.token}"
        })
    
    @task(3)
    def create_payment(self):
        self.client.post("/v1/payment_sessions", 
            headers={"Authorization": f"Bearer {self.token}"},
            json={
                "amount": 100,
                "currency": "USD",
                "success_url": "https://example.com/success",
                "cancel_url": "https://example.com/cancel"
            }
        )
```

```bash
# Install locust
pip install locust

# Run load test
locust -f locustfile.py
```

## Common Test Scenarios

### 1. Invalid Token
```bash
curl http://localhost:8000/merchant/profile \
  -H "Authorization: Bearer invalid_token"

# Expected: 401 Unauthorized
```

### 2. Duplicate Email Registration
```bash
# Register twice with same email
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"name": "Test", "email": "same@email.com", "password": "pass123"}'

# Second attempt should return 400
```

### 3. Payment Without Stellar Address
```bash
# Try to create payment before setting stellar_address
# Expected: 400 Bad Request
```

### 4. Expired Session
```bash
# Create session and wait > 15 minutes
# Check status - should be "expired"
```

### 5. Wrong Payment Amount
```bash
# Send payment with amount different from session.amount_usdc
# Payment should NOT be detected as valid
```

### 6. Missing Memo
```bash
# Send payment without memo
# Payment should be ignored
```

### 7. Admin Access Control
```bash
# Try to access admin endpoint with merchant token
# Expected: 403 Forbidden
```

## Automated Testing Script

```python
# run_tests.py
import requests
import time

BASE_URL = "http://localhost:8000"

def run_all_tests():
    print("🧪 Running automated tests...\n")
    
    # Test 1: Health check
    assert requests.get(f"{BASE_URL}/health").status_code == 200
    print("✅ Health check passed")
    
    # Test 2: Register merchant
    response = requests.post(f"{BASE_URL}/auth/register", json={
        "name": "Test Merchant",
        "email": f"test{time.time()}@example.com",
        "password": "password123"
    })
    assert response.status_code == 201
    token = response.json()["access_token"]
    print("✅ Merchant registration passed")
    
    # Test 3: Update profile
    response = requests.put(f"{BASE_URL}/merchant/profile",
        headers={"Authorization": f"Bearer {token}"},
        json={"stellar_address": "GABC123"}
    )
    assert response.status_code == 200
    print("✅ Profile update passed")
    
    # Test 4: Create payment
    response = requests.post(f"{BASE_URL}/v1/payment_sessions",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "amount": 100,
            "currency": "USD",
            "success_url": "https://example.com/success",
            "cancel_url": "https://example.com/cancel"
        }
    )
    assert response.status_code == 201
    session_id = response.json()["session_id"]
    print("✅ Payment creation passed")
    
    # Test 5: Get payment status
    response = requests.get(f"{BASE_URL}/v1/payment_sessions/{session_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "created"
    print("✅ Payment status retrieval passed")
    
    print("\n🎉 All tests passed!")

if __name__ == "__main__":
    run_all_tests()
```

## Troubleshooting Tests

| Issue | Solution |
|-------|----------|
| Connection refused | Ensure server is running |
| 401 Unauthorized | Check token is valid and not expired |
| 404 Not Found | Verify endpoint URL is correct |
| 500 Internal Server Error | Check server logs for details |
| Payment not detected | Verify Stellar listener is running |
| Webhook not received | Check URL is publicly accessible |

## Next Steps

1. Write integration tests using pytest
2. Add test coverage reporting
3. Set up CI/CD pipeline with automated tests
4. Implement contract testing for webhooks
5. Add performance benchmarks
