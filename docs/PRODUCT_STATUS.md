# Dari for Business - Multi-Chain Stablecoin Payment Gateway

## Product Overview

**Dari for Business** is a Stripe-like hosted payment gateway enabling merchants to accept stablecoin payments (USDC, USDT, PYUSD) across multiple blockchains. The platform provides a non-custodial solution where payments flow directly to merchant wallets.

### Supported Networks
| Network | Status | Stablecoins |
|---------|--------|-------------|
| Stellar | ✅ Production | USDC |
| Polygon | ✅ Ready | USDC, USDT |
| Ethereum | ✅ Ready | USDC, USDT, PYUSD |
| Base | ✅ Ready | USDC |
| Tron | ✅ Ready | USDT, USDC |
| Solana | 🔄 Roadmap | USDC, USDT |

### Key Features

1. **Multi-Chain Support** - Accept payments on customer's preferred blockchain
2. **Multiple Stablecoins** - USDC, USDT, and PYUSD support
3. **Non-Custodial** - Payments go directly to merchant wallets
4. **Real-Time Price Conversion** - Automatic fiat-to-crypto conversion via CoinGecko
5. **Unified Checkout** - Single hosted checkout page for all payment methods
6. **Webhook Notifications** - Real-time payment event callbacks
7. **Backward Compatible** - Existing Stellar-only integrations continue working

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Dari for Business                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │   FastAPI    │  │   Pydantic   │  │    SQLAlchemy 2.0    │   │
│  │   Backend    │  │   Schemas    │  │    PostgreSQL/SQLite │   │
│  └──────────────┘  └──────────────┘  └──────────────────────┘   │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                  Blockchain Abstraction Layer               ││
│  ├─────────────────────────────────────────────────────────────┤│
│  │ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐        ││
│  │ │  Stellar │ │   EVM    │ │   Tron   │ │  Solana  │        ││
│  │ │ Listener │ │ Listener │ │ Listener │ │ Listener │        ││
│  │ └──────────┘ └──────────┘ └──────────┘ └──────────┘        ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │    Token     │  │    Price     │  │      Webhook         │   │
│  │   Registry   │  │   Service    │  │      Service         │   │
│  └──────────────┘  └──────────────┘  └──────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## API Endpoints

### Authentication
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/register` | Register new merchant |
| POST | `/api/auth/login` | Login and get JWT token |

### Merchant Management
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/merchant/me` | Get merchant profile |
| PUT | `/api/merchant/settings` | Update merchant settings |
| POST | `/api/merchant/api-keys` | Generate API key |

### Wallet Management (NEW)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/wallets` | List merchant wallets |
| POST | `/api/wallets` | Add wallet for a chain |
| PUT | `/api/wallets/{id}` | Update wallet |
| DELETE | `/api/wallets/{id}` | Remove wallet |

### Payment Sessions
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/sessions` | Create payment session |
| GET | `/api/sessions/{id}` | Get session details |
| GET | `/api/sessions/{id}/status` | Check payment status |
| GET | `/api/sessions/{id}/options` | Get payment options (NEW) |
| POST | `/api/sessions/{id}/select` | Select payment method (NEW) |

### Hosted Checkout
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/checkout/{session_id}` | Render checkout page |

---

## Payment Flow

```
1. Merchant creates session
   POST /api/sessions
   {
     "amount_fiat": 100.00,
     "fiat_currency": "USD",
     "accepted_tokens": ["USDC", "USDT"],
     "accepted_chains": ["polygon", "stellar"]
   }

2. Customer opens checkout page
   /checkout/{session_id}

3. Checkout fetches payment options
   GET /api/sessions/{id}/options
   → Returns: { USDC/Polygon: 100.02, USDT/Tron: 100.05, ... }

4. Customer selects payment method
   POST /api/sessions/{id}/select
   { "token": "USDC", "chain": "polygon" }

5. Customer sends payment to merchant wallet

6. Blockchain listener detects payment
   → Updates session status to "paid"
   → Sends webhook to merchant

7. Customer redirected to success_url
```

---

## Database Schema

### New Tables

#### `tokens`
```sql
- id: SERIAL PRIMARY KEY
- symbol: VARCHAR(10) -- USDC, USDT, PYUSD
- name: VARCHAR(50)
- chain: VARCHAR(20) -- stellar, ethereum, polygon, base, tron
- contract_address: VARCHAR(100)
- decimals: INTEGER
- is_active: BOOLEAN
```

#### `merchant_wallets`
```sql
- id: SERIAL PRIMARY KEY
- merchant_id: FK → merchants
- chain: VARCHAR(20)
- wallet_address: VARCHAR(100)
- is_active: BOOLEAN
- is_verified: BOOLEAN
```

#### `payment_events`
```sql
- id: SERIAL PRIMARY KEY
- session_id: FK → payment_sessions
- event_type: VARCHAR(50)
- data: JSONB
- created_at: TIMESTAMP
```

### Updated `payment_sessions`
New columns:
- `token`: Selected token (USDC, USDT, PYUSD)
- `chain`: Selected blockchain
- `amount_token`: Amount in selected token
- `accepted_tokens`: JSON array of accepted tokens
- `accepted_chains`: JSON array of accepted chains
- `merchant_wallet`: Wallet address for this payment
- `block_number`: Block where payment was confirmed
- `confirmations`: Number of confirmations

---

## Services

### BlockchainRegistry
Central registry managing all blockchain listeners. Provides unified interface for:
- Starting/stopping listeners
- Verifying payments across chains
- Querying token balances

### Token Registry
Maintains list of supported tokens with:
- Contract addresses per chain
- Decimal precision
- CoinGecko IDs for price feeds

### Price Service
Real-time fiat-to-crypto conversion using CoinGecko API:
- 60-second cache to respect rate limits
- Supports USD, EUR, GBP conversion
- Handles stablecoin price depegs

### Webhook Service
Enhanced webhook payloads now include:
```json
{
  "event": "payment.success",
  "session_id": "sess_xxx",
  "amount": 100.00,
  "currency": "USDC",
  "chain": "polygon",
  "token": "USDC",
  "tx_hash": "0x...",
  "block_number": 12345678,
  "confirmations": 12
}
```

---

## Configuration

### Environment Variables

```env
# Database
DATABASE_URL=postgresql://user:pass@host:5432/dari

# Stellar
STELLAR_NETWORK=public
STELLAR_HORIZON_URL=https://horizon.stellar.org

# EVM Chains
ETHEREUM_ENABLED=true
ETHEREUM_RPC_URL=https://eth-mainnet.g.alchemy.com/v2/YOUR_KEY
POLYGON_ENABLED=true
POLYGON_RPC_URL=https://polygon-mainnet.g.alchemy.com/v2/YOUR_KEY
BASE_ENABLED=true
BASE_RPC_URL=https://mainnet.base.org

# Tron
TRON_ENABLED=true
TRON_API_KEY=your-trongrid-api-key

# Security
JWT_SECRET_KEY=your-secret-key
API_KEY_SECRET=your-api-key-secret
```

---

## Installation

```bash
# Clone repository
git clone https://github.com/your-org/dari-backend.git
cd dari-backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt

# Run migrations
psql -d dari_db -f migrations/multichain_upgrade.sql

# Start server
uvicorn app.main:app --reload
```

---

## Integration Examples

### JavaScript SDK
```javascript
const dari = new DariClient('your_api_key');

const session = await dari.createSession({
  amount_fiat: 100.00,
  fiat_currency: 'USD',
  accepted_tokens: ['USDC', 'USDT'],
  accepted_chains: ['polygon', 'stellar'],
  success_url: 'https://yourstore.com/success',
  cancel_url: 'https://yourstore.com/cancel'
});

// Redirect customer to checkout
window.location.href = session.checkout_url;
```

### Webhook Handler
```javascript
app.post('/webhook', (req, res) => {
  const { event, session_id, chain, token, amount } = req.body;
  
  if (event === 'payment.success') {
    console.log(`Payment received: ${amount} ${token} on ${chain}`);
    // Update order status
  }
  
  res.json({ received: true });
});
```

---

## File Structure

```
app/
├── main.py                      # FastAPI application
├── core/
│   ├── config.py               # Multi-chain settings
│   ├── database.py             # SQLAlchemy setup
│   └── auth.py                 # JWT authentication
├── models/
│   └── models.py               # Database models (Token, MerchantWallet, etc)
├── schemas/
│   └── schemas.py              # Pydantic schemas
├── routes/
│   ├── sessions.py             # Payment session endpoints
│   ├── wallets.py              # Wallet management (NEW)
│   ├── checkout.py             # Hosted checkout page
│   └── ...
├── services/
│   ├── token_registry.py       # Token configuration (NEW)
│   ├── price_service.py        # Fiat-to-crypto conversion (NEW)
│   ├── webhook_service.py      # Merchant notifications
│   └── blockchains/
│       ├── base.py             # Abstract listener class (NEW)
│       ├── registry.py         # Blockchain registry (NEW)
│       ├── stellar_listener.py # Stellar payments (NEW)
│       ├── evm_listener.py     # Ethereum/Polygon/Base (NEW)
│       └── tron_listener.py    # Tron network (NEW)
└── templates/
    ├── checkout.html           # Legacy checkout
    └── checkout_multichain.html# New multi-chain checkout (NEW)

migrations/
└── multichain_upgrade.sql      # Database migration (NEW)
```

---

## Roadmap

- [ ] Solana listener implementation
- [ ] Bitcoin Lightning support
- [ ] Merchant dashboard UI
- [ ] Subscription/recurring payments
- [ ] Multi-currency settlement
- [ ] KYC/AML integration
- [ ] Mobile SDK (iOS/Android)

---

## License

MIT License - See LICENSE file for details.
