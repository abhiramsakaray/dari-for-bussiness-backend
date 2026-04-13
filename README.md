# ChainPe Backend - Multi-Chain Payment Processing Platform

A FastAPI-based backend for processing cryptocurrency and blockchain payments with support for multiple chains, instant/scheduled refunds, subscriptions, and comprehensive merchant management.

**Status**: ✅ Production Ready (April 5, 2026)

---

## 🎯 Project Overview

ChainPe Backend is a comprehensive payment processing platform that enables merchants to:
- Accept payments across multiple blockchain networks (Polygon, Stellar, Soroban, Tron, etc.)
- Process full and partial refunds with real-time blockchain confirmation
- Manage recurring subscription payments
- Create payment links and invoices
- Track payment analytics and generate tax reports

**Production Features**: 
- ✅ Real blockchain transaction processing
- ✅ Multi-chain support (Polygon mainnet & testnet, Stellar)
- ✅ Merchant wallet management
- ✅ Webhook notifications with HMAC-SHA256 signing
- ✅ Gasless relayer infrastructure
- ✅ Enterprise compliance and security features

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- PostgreSQL 13+
- Redis (for caching)
- Environment variables (see `.env` setup)

### Installation

```bash
# Clone repository
git clone https://github.com/abhiramsakaray/dari-for-bussiness-backend.git
cd chainpe-backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Initialize database
python scripts/init_db.py

# Start server
python app/main.py
```

Server runs on: `http://localhost:8003`

---

## 📋 Core Features

### 1. **Multi-Chain Payments**
- Support for EVM chains (Polygon, Ethereum)
- Stellar network integration
- Soroban smart contracts
- Real-time transaction confirmation
- Automatic currency precision handling

### 2. **Refund System** ✅ COMPLETED
- **Full & Partial Refunds**: Process any amount
- **Instant Processing**: Real-time blockchain transactions
- **Scheduled Processing**: Automatic batch processing every 60+ minutes
- **Recovery System**: Handle failed refunds with address validation
- **Chain-specific Handling**: Stellar address lookup, Polygon checksums

**Recent Fixes (April 5, 2026)**:
- Fixed Web3 transaction signing with correct chain IDs
- Implemented real blockchain transactions (no more mock hashes)
- Added chain-aware wallet validation
- Recovery endpoint for missing/invalid addresses

### 3. **Subscription Management**
- Recurring payment automation
- Multiple subscription tiers
- Flexible billing cycles
- Plan management and status tracking

### 4. **Payment Links & Invoices**
- Generate shareable payment links
- Create and track invoices
- Automatic payment status updates
- Invoice PDF generation

### 5. **Merchant Management**
- Merchant onboarding workflow
- API key management
- Balance tracking (platform & external wallets)
- Settlement tracking (in-platform vs external)
- Team member management

### 6. **Webhooks & Notifications**
- Real-time event notifications
- HMAC-SHA256 secure signing
- Automatic retry with exponential backoff (5 attempts)
- Event audit log
- Manual retry capability

### 7. **Analytics & Reporting**
- Transaction history
- Revenue analytics
- Tax report generation
- Cross-border transaction tracking
- Risk assessment and compliance

---

## 📁 Project Architecture

```
chainpe-backend/
├── app/
│   ├── core/                      # Configuration & utilities
│   │   ├── auth.py               # JWT authentication
│   │   ├── cache.py              # Redis caching
│   │   ├── database.py           # SQLAlchemy setup
│   │   ├── config.py             # Environment configuration
│   │   └── security_middleware.py # CORS, rate limiting
│   ├── models/
│   │   └── models.py             # SQLAlchemy ORM models
│   ├── schemas/                  # Pydantic validation schemas
│   ├── routes/
│   │   ├── payments.py           # Payment endpoints
│   │   ├── refunds.py            # Refund processing ✅
│   │   ├── subscriptions.py      # Subscription management
│   │   ├── merchant.py           # Merchant operations
│   │   ├── webhooks.py           # Webhook management
│   │   ├── admin.py              # Admin operations
│   │   └── [more routes...]
│   ├── services/
│   │   ├── refund_processor.py   # Refund logic ✅
│   │   ├── refund_scheduler.py   # Background jobs ✅
│   │   ├── blockchain_relayer.py # Multi-chain integration ✅
│   │   ├── webhook_service.py    # Webhook handling
│   │   └── [more services...]
│   └── main.py                   # FastAPI app initialization
├── migrations/                    # SQL database migrations
├── scripts/
│   ├── init_db.py                # Database initialization
│   ├── generate_api_keys.py      # Key generation utilities
│   └── [more utilities...]
├── docs/                         # 📚 Documentation & scripts
│   ├── IMPLEMENTATION_COMPLETE.md
│   ├── REAL_BLOCKCHAIN_INTEGRATION.md
│   ├── REFUND_FEATURES.md
│   ├── [10+ more documentation files]
│   ├── check_relayer_config.py        # Config validation script
│   ├── reset_and_reprocess_refunds.py # Refund recovery script
│   ├── [4+ more utility scripts]
├── requirements.txt
└── README.md
```

---

## 🔌 API Endpoints Overview

### Payments
```
POST   /payments/create                 # Create payment session
GET    /payments/{session_id}           # Get payment details
GET    /payments/status/{session_id}    # Check payment status
POST   /payments/webhook/callback       # Webhook callback handler
```

### Refunds ✅
```
POST   /refunds                         # Create refund
GET    /refunds/{refund_id}             # Get refund details
GET    /refunds/status/{session_id}     # List refunds for payment
POST   /refunds/{refund_id}/retry       # Retry failed refund
POST   /refunds/{refund_id}/force-retry # Force retry on-chain
PATCH  /refunds/{refund_id}/update-address  # Update wallet address
POST   /refunds/process-pending         # Manual trigger processing
```

### Subscriptions
```
POST   /subscriptions/create            # Create subscription
GET    /subscriptions/{sub_id}          # Get subscription
PATCH  /subscriptions/{sub_id}/cancel   # Cancel subscription
POST   /subscriptions/{sub_id}/pause    # Pause subscription
```

### Webhooks
```
POST   /webhooks/register               # Register webhook URL
GET    /webhooks/list                   # List webhooks
POST   /webhooks/{webhook_id}/retry     # Retry failed webhook
DELETE /webhooks/{webhook_id}           # Unregister webhook
```

### Merchant Management
```
POST   /merchant/register               # Onboarding
GET    /merchant/profile                # Get merchant info
GET    /merchant/balance                # Check balance
GET    /merchant/transactions           # Transaction history
```

---

## 📊 Database Models

Key entities:
- **PaymentSession**: Core payment records
- **Refund**: Refund transactions (with status tracking)
- **Merchant**: Merchant accounts
- **Subscription**: Recurring payment subscriptions
- **PaymentEvent**: Audit log
- **Webhook**: Registered webhook endpoints
- **RelayerTransaction**: Blockchain transaction logs

See [models.py](app/models/models.py) for complete schema.

---

## ✅ Roadmap & Status

### Phase 1: Core Payment Processing ✅ DONE
- [x] Payment session creation
- [x] Multi-chain support setup
- [x] Database schema
- [x] Authentication & authorization

### Phase 2: Blockchain Integration ✅ DONE (April 5, 2026)
- [x] Polygon integration (mainnet & Amoy testnet)
- [x] Stellar network integration
- [x] Web3.py transaction signing
- [x] Real blockchain confirmations
- [x] Chain ID validation and dynamic configuration
- [x] Gas price calculation

### Phase 3: Refund System ✅ DONE (April 5, 2026)
- [x] Full & partial refund support
- [x] Instant refund processing
- [x] Scheduled batch processing (60+ minutes)
- [x] Refund failure handling
- [x] Chain-specific wallet validation
- [x] Recovery mechanism for missing addresses
- [x] Real blockchain transaction hashes (replaced mock `0x1111...`)
- [x] **Recovery Examples**:
  - Polygon: `36cb54a1548d1bb93085d2ba7a58556f69e5c2b088d1845a3c7e28236e34152d`
  - Polygon: `b8415dea6863fa68ca839974b5ea0f361f5fcb1a536dc38062925f009110a525`

### Phase 4: Subscriptions & Recurring Payments ✅ DONE
- [x] Subscription management
- [x] Recurring payment automation
- [x] Plan tiers and pricing
- [x] Auto-renewal and cancellation

### Phase 5: Webhooks & Notifications ✅ DONE
- [x] Event-based webhooks
- [x] HMAC-SHA256 signing
- [x] Automatic retry (5 attempts)
- [x] Event audit log
- [x] Manual retry capability

### Phase 6: Admin & Analytics ✅ DONE
- [x] Admin dashboard endpoints
- [x] Transaction analytics
- [x] Revenue reports
- [x] Tax report generation
- [x] Admin scheduler control

### Phase 7: Security & Compliance ✅ DONE
- [x] JWT authentication
- [x] Rate limiting
- [x] CORS configuration
- [x] Webhook HMAC signing
- [x] PCI compliance features
- [x] Cross-border risk assessment

### Phase 8: Documentation & Organization ✅ DONE (April 5, 2026)
- [x] Reorganize docs to `/docs` folder
- [x] Move utility scripts to `/docs` folder
- [x] Clean root directory
- [x] Update README with current status
- [x] Document recovery procedures

---

## 🔧 Configuration

### Environment Variables

Create `.env` file in root:

```env
# Server
ENV=dev
DEBUG=true
LOG_LEVEL=INFO

# Database
DATABASE_URL=postgresql://user:password@localhost/chainpe

# Redis
REDIS_URL=redis://localhost:6379

# Blockchain - Polygon
POLYGON_RPC_URL=https://rpc-amoy.polygon.technology
RELAYER_PRIVATE_KEY=<your_private_key>

# Blockchain - Stellar
STELLAR_SERVER_URL=https://horizon-testnet.stellar.org
STELLAR_SECRET_KEY=<your_secret_key>

# API Keys & Security
JWT_SECRET_KEY=<random_secret>
API_KEY_PREFIX=sk_
WEBHOOK_SIGNING_KEY=<random_key>

# CORS
ALLOWED_ORIGINS=http://localhost:3000,https://yourdomain.com

# Scheduler
ENABLE_SCHEDULER=true
SCHEDULER_INTERVAL_MINUTES=60
```

---

## 🧪 Testing

### Run Tests
```bash
pytest tests/
```

### Utility Scripts (in `/docs`)

**Check Relayer Configuration**:
```bash
python docs/check_relayer_config.py
```

**Reset & Reprocess Failed Refunds**:
```bash
python docs/reset_and_reprocess_refunds.py
```

**Update Stellar Refund Address**:
```bash
python docs/update_stellar_refund.py
```

**Test Instant vs Scheduled Processing**:
```bash
python docs/test_instant_vs_scheduled.py
```

---

## 📚 Documentation

Comprehensive guides available in `/docs`:

| Document | Purpose |
|----------|---------|
| [IMPLEMENTATION_COMPLETE.md](docs/IMPLEMENTATION_COMPLETE.md) | Feature implementation overview |
| [REAL_BLOCKCHAIN_INTEGRATION.md](docs/REAL_BLOCKCHAIN_INTEGRATION.md) | Blockchain setup guide |
| [REFUND_FEATURES.md](docs/REFUND_FEATURES.md) | Refund system documentation |
| [INSTANT_VS_SCHEDULED_REFUNDS.md](docs/INSTANT_VS_SCHEDULED_REFUNDS.md) | Processing modes explained |
| [WEBHOOKS_INTEGRATION.md](docs/WEBHOOKS_INTEGRATION.md) | Webhook setup guide |
| [SCHEDULER_IMPLEMENTATION.md](docs/SCHEDULER_IMPLEMENTATION.md) | Background job configuration |
| [SECURITY_AND_COMPLIANCE.md](docs/SECURITY_AND_COMPLIANCE.md) | Security best practices |

---

## 🐛 Recent Fixes (April 5, 2026)

### Refund Recovery System
**Problem**: 2 Polygon refunds showed COMPLETED but had fake transaction hashes.

**Solutions Implemented**:
1. **Chain ID Validation**: Dynamic chain ID from RPC (not hardcoded 137)
2. **Web3 Property Names**: Corrected `raw_transaction` (snake_case)
3. **Settings References**: Fixed `relayer_key` usage for signing
4. **Address Recovery**: Added PATCH endpoint for updating missing addresses
5. **Chain-Specific Handling**: Stellar address lookup from session metadata

**Results**:
- ✅ 2 Polygon refunds now have real blockchain tx hashes
- ✅ Stellar refund recovery mechanism in place
- ✅ No more mock transaction hashes (`0x1111...`)
- ✅ All 3 refunds in clean recoverable state

---

## � Billing Currency Fix (April 12, 2026)

### 🔴 Critical Issue
The billing page displays hardcoded USD prices with the user's currency symbol, creating incorrect price displays.

**Problem Example**:
```
User in India sees: ₹0, ₹29, ₹99  ← Wrong! These are USD prices with INR symbol
Expected: ₹0, ₹2,400, ₹8,200    ← Correct INR prices
```

### ✅ Solution Implemented
Backend now provides **currency-aware pricing** through the billing API.

### 🔧 Backend Implementation

#### Currency Conversion Logic
```python
PLAN_PRICES_USD = {
    'free': 0,
    'growth': 29,
    'business': 99,
    'enterprise': None
}

CURRENCY_RATES = {
    'USD': 1.0,
    'INR': 83.0,      # 1 USD = 83 INR
    'EUR': 0.92,      # 1 USD = 0.92 EUR
    'GBP': 0.79,      # 1 USD = 0.79 GBP
    # ... more currencies
}

def get_plan_price_in_currency(plan_id: str, currency: str) -> float:
    """Convert plan price to user's currency"""
    usd_price = PLAN_PRICES_USD.get(plan_id)
    if usd_price is None or usd_price == 0:
        return usd_price
    
    rate = CURRENCY_RATES.get(currency, 1.0)
    converted_price = usd_price * rate
    
    # Round appropriately per currency
    if currency == 'INR':
        return round(converted_price / 100) * 100
    else:
        return round(converted_price, 2)
```

#### API Response Update
The `GET /billing` endpoint now includes `available_plans`:

```json
{
  "tier": "growth",
  "currency": "INR",
  "monthly_price": 2400,
  
  "available_plans": {
    "free": {
      "id": "free",
      "name": "Free",
      "price": 0,
      "currency": "INR",
      "features": {
        "transaction_fee": 2.9,
        "monthly_volume_limit": 10000,
        "team_members": 1
      }
    },
    "growth": {
      "id": "growth",
      "name": "Growth",
      "price": 2400,
      "currency": "INR",
      "features": {
        "transaction_fee": 0.9,
        "monthly_volume_limit": 50000,
        "team_members": 3
      }
    },
    "business": {
      "id": "business",
      "name": "Business",
      "price": 8200,
      "currency": "INR",
      "features": {
        "transaction_fee": 0.5,
        "monthly_volume_limit": null,
        "team_members": 10
      }
    },
    "enterprise": {
      "id": "enterprise",
      "name": "Enterprise",
      "price": null,
      "currency": "INR",
      "contact_sales": true
    }
  }
}
```

### 📊 Price Conversion Table
| Plan | USD | INR | EUR | GBP |
|------|-----|-----|-----|-----|
| Free | $0 | ₹0 | €0 | £0 |
| Growth | $29 | ₹2,400 | €27 | £23 |
| Business | $99 | ₹8,200 | €91 | £78 |
| Enterprise | Custom | Custom | Custom | Custom |

### ✨ Results
- ✅ Backend provides prices in user's currency
- ✅ Frontend uses backend prices instead of hardcoded values
- ✅ Correct currency symbols with correct prices
- ✅ Supports unlimited currencies via exchange rates
- ✅ Proper rounding per currency (₹100 increments for INR, ¢2 for USD/EUR/GBP)

---

## �📞 Support & Contact

For issues, questions, or contributions:
- Create an issue on GitHub
- See `/docs` folder for detailed guides
- Check utility scripts for automated troubleshooting

---

## 📄 License

MIT License - See LICENSE file for details

---

## 🔗 Links

- **GitHub**: https://github.com/abhiramsakaray/dari-for-bussiness-backend
- **Documentation**: See `/docs` folder
- **API Docs**: `http://localhost:8003/docs` (when running)
- **Blockchain Networks**: 
  - Polygon Amoy (testnet): Chain ID 80002
  - Stellar Testnet: https://horizon-testnet.stellar.org

---

**Last Updated**: April 5, 2026  
**Version**: 1.0.0 (Production Ready)  
**Maintainer**: Abhiram Sakaray

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

See [TESTING.md](docs/guides/TESTING.md) for comprehensive testing guide.

## Security

- ✅ No private keys stored
- ✅ No fund custody
- ✅ JWT authentication
- ✅ Input validation
- ✅ HTTPS only in production
- ✅ Rate limiting

## License

MIT
