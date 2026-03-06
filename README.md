# Dari for Business - Multi-Chain Payment Gateway API

A Stripe-like hosted payment gateway backend that allows merchants to accept cryptocurrency payments across multiple blockchains including Stellar, Ethereum, Polygon, Base, and Tron. This is the core API service that powers the Dari for Business payment infrastructure.

## 🌟 Features

### Core Payment Features
- 🔐 JWT-based authentication for merchants and admins
- 💳 Create hosted checkout payment sessions
- 🌐 Multi-chain blockchain support (Stellar, Ethereum, Polygon, Base, Tron)
- 🪙 Multiple stablecoin support (USDC, USDT, PYUSD)
- ⭐ Real-time blockchain payment detection across all chains
- 🔔 Webhook notifications to merchants
- 🎯 No fund custody - payment verification only
- 👑 Admin dashboard APIs
- 🔄 Automatic payment status updates
- 📊 Payment analytics and history
- 💼 Merchant wallet management per blockchain

### 🏢 Enterprise Features (NEW)
- 🔗 **Payment Links** - Create reusable, shareable payment links (like Stripe Payment Links)
- 📄 **Invoice System** - Professional invoicing with line items, due dates, and reminders
- 🔄 **Subscriptions** - Recurring payments with plans, trials, and billing cycles
- 💰 **Refunds** - Full and partial refund processing
- 📈 **Merchant Analytics** - Real-time analytics dashboard, revenue reports by chain/token
- 👥 **Team Management** - Multi-user access with roles (Owner, Admin, Developer, Finance, Viewer)
- 🔑 **Idempotency Keys** - Prevent duplicate API operations
- 📬 **Event Queue** - Async event processing for webhooks and notifications

## 🛠️ Tech Stack

- **Language**: Python 3.10+
- **Framework**: FastAPI
- **Database**: PostgreSQL (SQLite for development)
- **Blockchains**: 
  - Stellar SDK (stellar-sdk)
  - Web3.py (Ethereum, Polygon, Base)
  - Tron SDK (tronpy)
- **Authentication**: JWT + API Keys
- **Async**: asyncio for blockchain monitoring
- **Validation**: Pydantic schemas

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your configuration
```

### 3. Initialize Database

```bash
python init_db.py
```

### 4. Run Application

```bash
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`

### 5. Start Blockchain Listeners (Separate Terminals)

```bash
# Stellar listener
python -m app.services.stellar_listener

# EVM chains listener (Ethereum, Polygon, Base)
python -m app.services.blockchains.evm_listener

# Tron listener
python -m app.services.blockchains.tron_listener
```

**📚 Learn More**: See [Blockchain Listeners Documentation](docs/BLOCKCHAIN_LISTENERS.md) for detailed technical information on how payment listening and verification works for each blockchain.

## 📚 API Documentation

Once running, visit:
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

### Key Endpoints

#### Authentication
- `POST /auth/register` - Register new merchant
- `POST /auth/login` - Login (returns access_token + api_key)

#### Payment Sessions
- `POST /api/sessions/create` - Create payment session
- `GET /api/sessions/{session_id}` - Get session details
- `POST /api/sessions/{session_id}/cancel` - Cancel session

#### Payment Links 🔗
- `POST /payment-links` - Create reusable payment link
- `GET /payment-links` - List payment links
- `GET /payment-links/{id}` - Get link details
- `PATCH /payment-links/{id}` - Update link
- `DELETE /payment-links/{id}` - Deactivate link
- `GET /payment-links/{id}/analytics` - Link analytics

#### Invoices 📄
- `POST /invoices` - Create invoice
- `GET /invoices` - List invoices
- `GET /invoices/{id}` - Get invoice
- `PATCH /invoices/{id}` - Update invoice
- `POST /invoices/{id}/send` - Send invoice
- `POST /invoices/{id}/remind` - Send reminder
- `POST /invoices/{id}/cancel` - Cancel invoice
- `POST /invoices/{id}/duplicate` - Duplicate invoice

#### Subscriptions 🔄
- `POST /subscriptions/plans` - Create plan
- `GET /subscriptions/plans` - List plans
- `POST /subscriptions` - Create subscription
- `GET /subscriptions` - List subscriptions
- `POST /subscriptions/{id}/cancel` - Cancel subscription
- `POST /subscriptions/{id}/pause` - Pause subscription
- `POST /subscriptions/{id}/resume` - Resume subscription

#### Refunds 💰
- `POST /refunds` - Create refund
- `GET /refunds` - List refunds
- `GET /refunds/{id}` - Get refund
- `POST /refunds/{id}/cancel` - Cancel pending refund

#### Analytics 📈
- `GET /analytics/overview` - Analytics overview
- `GET /analytics/revenue` - Revenue time series
- `GET /analytics/payments/summary` - Payment summary
- `GET /analytics/conversion` - Conversion metrics
- `GET /analytics/chains` - Chain breakdown

#### Team 👥
- `POST /team/invite` - Invite team member
- `GET /team` - List team members
- `PATCH /team/{id}` - Update member role
- `DELETE /team/{id}` - Remove member

#### Merchant
- `GET /merchant/profile` - Get merchant profile
- `PUT /merchant/profile` - Update merchant settings
- `GET /merchant/payments` - List payment history

#### Admin
- `GET /admin/merchants` - List all merchants
- `GET /admin/payments` - List all payments
- `POST /admin/webhooks/test` - Test webhook delivery
- `DELETE /admin/merchants/{id}` - Delete merchant

#### Public
- `GET /checkout/{session_id}` - Hosted checkout page
- `GET /api/sessions/{session_id}/status` - Public status check

## 📁 Architecture

```
dari-backend/
├── app/
│   ├── models/                 # SQLAlchemy database models
│   │   └── models.py          # Merchant, Payment, Session models
│   ├── routes/                # API endpoint routers
│   │   ├── auth.py            # Authentication endpoints
│   │   ├── sessions.py        # Payment session endpoints
│   │   ├── merchant.py        # Merchant management
│   │   ├── wallets.py         # Wallet management endpoints
│   │   ├── payment_links.py   # Reusable payment links
│   │   ├── invoices.py        # Invoice management
│   │   ├── subscriptions.py   # Recurring payments
│   │   ├── refunds.py         # Refund processing
│   │   ├── analytics.py       # Merchant analytics
│   │   ├── team.py            # Team management
│   │   ├── admin.py           # Admin operations
│   │   └── public.py          # Public checkout pages
│   ├── services/              # Business logic layer
│   │   ├── stellar_listener.py    # Stellar blockchain monitoring
│   │   ├── blockchains/       # Multi-chain listeners
│   │   │   ├── evm_listener.py    # EVM chains monitoring
│   │   │   ├── tron_listener.py   # Tron monitoring
│   │   │   └── registry.py        # Blockchain registry
│   │   ├── webhook_service.py # Webhook delivery
│   │   ├── price_service.py   # Token price fetching
│   │   └── token_registry.py  # Token configuration
│   ├── schemas/               # Pydantic validation schemas
│   ├── core/                  # Core utilities
│   │   ├── config.py          # Configuration management
│   │   ├── database.py        # Database connection
│   │   ├── security.py        # JWT & password hashing
│   │   └── auth.py            # Authentication logic
│   └── main.py                # FastAPI application entry
├── contracts/                 # Soroban smart contracts
│   └── escrow/                # Payment escrow contract (optional)
├── public/                    # Static hosted checkout pages
│   ├── demo.html              # Payment demo
│   └── dari-button.js         # Embeddable button widget
├── migrations/                # Database migrations
├── init_db.py                 # Database initialization
├── schema.sql                 # Database schema
├── requirements.txt           # Python dependencies
└── .env                       # Environment configuration
```

## 🔄 Payment Flow

1. **Session Creation**: Merchant creates payment session via API
2. **Checkout Redirect**: Customer redirected to hosted checkout page
3. **Chain & Token Selection**: Customer selects blockchain and token
4. **QR Display**: Customer scans QR code with crypto wallet
5. **Payment Detection**: Blockchain listener monitors for payment
6. **Validation**: Payment amount, token, and memo verified
7. **Status Update**: Database updated with transaction details
8. **Webhook Trigger**: Merchant notified via webhook
9. **Redirect**: Customer redirected to success URL

## 🌐 Environment Variables

Create a `.env` file in the backend root (see `.env.example` for full configuration):

```env
# Database
DATABASE_URL=postgresql://user:password@localhost/dari
# or for development:
# DATABASE_URL=sqlite:///./dari.db

# JWT Configuration
SECRET_KEY=your-super-secret-key-change-this
JWT_ALGORITHM=HS256
JWT_EXPIRATION_MINUTES=30

# Stellar Configuration
STELLAR_NETWORK=testnet
STELLAR_HORIZON_URL=https://horizon-testnet.stellar.org

# Ethereum Configuration
ETHEREUM_RPC_URL=https://eth-mainnet.g.alchemy.com/v2/YOUR_KEY
ETHEREUM_CONFIRMATIONS=12

# Polygon Configuration
POLYGON_RPC_URL=https://polygon-mainnet.g.alchemy.com/v2/YOUR_KEY
POLYGON_CONFIRMATIONS=128

# Base Configuration
BASE_RPC_URL=https://mainnet.base.org
BASE_CONFIRMATIONS=10

# Tron Configuration
TRON_API_URL=https://api.trongrid.io
TRON_API_KEY=your-trongrid-api-key

# Admin Account
ADMIN_EMAIL=admin@yourdomain.com
ADMIN_PASSWORD=change-this-password

# CORS
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000

# Optional: Webhook Configuration
WEBHOOK_TIMEOUT=10
WEBHOOK_RETRY_ATTEMPTS=3
```

🔒 Security

- ✅ **No Private Keys**: Server never handles private keys
- ✅ **No Fund Custody**: Payments go directly to merchant wallets
- ✅ **JWT Authentication**: Secure token-based auth with expiration
- ✅ **API Key Rotation**: Merchants can regenerate API keys
- ✅ **Input Validation**: Pydantic schemas validate all inputs
- ✅ **Password Hashing**: bcrypt for secure password storage
- ✅ **HTTPS Only**: Production enforces SSL/TLS
- ✅ **CORS Protection**: Configurable allowed origins
- ✅ **Rate Limiting**: (Recommended for production)

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

## 🐛 Troubleshooting

### Blockchain Listeners Not Working
- Check RPC URLs for all chains in `.env`
- Verify network connectivity to blockchain APIs
- Ensure listener processes are running separately
- Check API keys for Ethereum/Polygon (Alchemy) and Tron (TronGrid)

### Database Connection Issues
- Verify PostgreSQL is running
- Check `DATABASE_URL` format
- Run `python init_db.py` to reset schema

### Authentication Failures
- Verify `SECRET_KEY` is set
- Check token expiration (default 30 minutes)
- Ensure both `Authorization` and `X-API-Key` headers are sent

### CORS Errors
- Add frontend URL to `ALLOWED_ORIGINS` in `.env`
- Restart backend after config changes

## 📦 Dependencies

Key packages (see `requirements.txt` for full list):
- `fastapi` - Web framework
- `uvicorn` - ASGI server
- `sqlalchemy` - ORM
- `stellar-sdk` - Stellar blockchain interaction
- `web3` - EVM chains (Ethereum, Polygon, Base)
- `tronpy` - Tron blockchain interaction
- `pydantic` - Data validation
- `python-jose` - JWT handling
- `passlib` - Password hashing
- `httpx` - HTTP client for webhooks

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit changes (`git commit -m 'Add AmazingFeature'`)
4. Push to branch (`git push origin feature/AmazingFeature`)
5. Open Pull Request

## 📝 License

MIT License - See [LICENSE](../LICENSE) file for details

## 🔗 Related Projects

- **Frontend**: [../dari-frontend](../dari-frontend)
- **Smart Contracts**: [contracts/](contracts/)
- **Integration Examples**: [docs/react_integration_examples/](docs/react_integration_examples/)

---

**Part of the Dari for Business Payment Infrastructure** | [Main Documentation](../README.md)IN_EMAIL=admin@chainpe.com
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
