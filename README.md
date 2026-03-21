# Dari SDK

SDK for integrating with the Dari backend: create payments, subscriptions, payment links, invoices, and refunds.

## Features

- Simple, class-based API
- Handles authentication, errors, and HTTP requests
- Available for Node.js (JavaScript) and Python

---

## Installation

### JavaScript (Node.js)

```bash
npm install dari-sdk
```

### Python

```bash
pip install dari-sdk
```

---

## Usage

### JavaScript

```js
const DariClient = require('dari-sdk');
const client = new DariClient('API_KEY');

// Create a payment session
const payment = await client.payments.create({
  amount: 100,
  currency: 'USD',
  success_url: 'https://merchant.com/success',
  cancel_url: 'https://merchant.com/cancel'
});
```

### Python

```python
from dari_sdk import DariClient

client = DariClient('API_KEY')

payment = client.payments.create({
    "amount": 100,
    "currency": "USD",
    "success_url": "https://merchant.com/success",
    "cancel_url": "https://merchant.com/cancel"
})
```

---

## API Overview

- `payments.create(data)`
- `payments.status(session_id)`
- `subscriptions.create(data)`
- `subscriptions.plans()`
- `payment_links.create(data)`
- `invoices.create(data)`
- `refunds.check_eligibility(session_id)`

See full API docs for request/response details.

---

## Folder Structure

```
src/
  dari_client.py (Python)
  index.js (JavaScript)
  modules/
  utils/
  __init__.py
```

---

## Contributing

- Fork, branch, and submit PRs
- Add tests for new features

---

## License

MIT

---

For full API documentation and advanced usage, see [API_DOCS.md](API_DOCS.md) or visit our developer portal.
ADMIN_PASSWORD=change-this-password

# CORS
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000

# Optional: Webhook Configuration
WEBHOOK_TIMEOUT=10
WEBHOOK_RETRY_ATTEMPTS=3
```

## 🚀 Deployment

### Recommended Platforms
- **Render** (recommended)
- **Railway**
- **Fly.io**
- **Heroku**

### Deployment Steps

1. **Prepare Database**
   ```bash
   # Create PostgreSQL database
   # Run migrations
   python init_db.py
   ```

2. **Set Environment Variables**
   - Configure all `.env` variables in platform settings
   - Use secure random values for `SECRET_KEY`

3. **Deploy Main API**
   ```bash
   # Install dependencies
   pip install -r requirements.txt
   
   # Start server
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

4. **Deploy Blockchain Listeners**
   ```bash
   # Run as separate background workers/services
   python -m app.services.stellar_listener
   python -m app.services.blockchains.evm_listener
   python -m app.services.blockchains.tron_listener
   ```

   **⚠️ Critical**: The blockchain listeners MUST run as separate processes/workers to monitor blockchain payments in real-time across all supported chains.

### Render Configuration

Create `render.yaml`:
```yaml
services:
  - type: web
    name: dari-api
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT
    
  - type: worker
    name: dari-stellar-listener
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: python -m app.services.stellar_listener
    
  - type: worker
    name: dari-evm-listener
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: python -m app.services.blockchains.evm_listener
    
  - type: worker
    name: dari-tron-listener
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: python -m app.services.blockchains.tron_listener
```

## 🧪 Testing

```bash
# Run API tests
python test_api.py

# Test specific endpoints
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"test123","business_name":"Test Store"}'
```

See [TESTING.md](TESTING.md) for comprehensive testing guide.

## Security

- ✅ No private keys stored
- ✅ No fund custody
- ✅ JWT authentication
- ✅ Input validation
- ✅ HTTPS only in production
- ✅ Rate limiting

## License

MIT
