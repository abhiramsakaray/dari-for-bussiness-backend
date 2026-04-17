# Quick Start Guide - Launch Your Payment Gateway

**Time to Production:** 4-8 hours  
**Status:** ✅ All features implemented

---

## Prerequisites

```bash
# Install Python dependencies
pip install -r requirements.txt
pip install stellar-sdk eth-account

# Install Node.js dependencies (for contract deployment)
cd contracts
npm install
cd ..
```

---

## Step 1: Configure Environment (15 minutes)

```bash
# Copy example environment file
cp .env.example .env

# Edit .env and set these REQUIRED values:
```

### Required Settings
```bash
# Database (use PostgreSQL for production)
DATABASE_URL=postgresql://user:password@localhost:5432/dari_payments

# Security (MUST change these!)
JWT_SECRET=$(openssl rand -hex 32)
API_KEY_SECRET=$(openssl rand -hex 32)
PII_ENCRYPTION_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")

# Network mode
USE_MAINNET=false  # Set to true for production

# Admin credentials
ADMIN_EMAIL=admin@yourdomain.com
ADMIN_PASSWORD=your-strong-password-here

# Application URL
APP_BASE_URL=http://localhost:8000  # Change to your domain in production

# Relayer wallet (for gasless transactions)
RELAYER_PRIVATE_KEY=0x...  # Generate with: openssl rand -hex 32
```

### Optional: RPC Endpoints (Recommended for Production)
```bash
# Use private RPC providers for better reliability
ETHEREUM_MAINNET_RPC_URL=https://eth-mainnet.g.alchemy.com/v2/YOUR_KEY
POLYGON_MAINNET_RPC_URL=https://polygon-mainnet.g.alchemy.com/v2/YOUR_KEY
AVALANCHE_MAINNET_RPC_URL=https://avalanche-mainnet.g.alchemy.com/v2/YOUR_KEY
BASE_MAINNET_RPC_URL=https://base-mainnet.g.alchemy.com/v2/YOUR_KEY
BSC_MAINNET_RPC_URL=https://bsc-dataseed.bnbchain.org
ARBITRUM_MAINNET_RPC_URL=https://arb-mainnet.g.alchemy.com/v2/YOUR_KEY
```

---

## Step 2: Initialize Database (5 minutes)

```bash
# Create database tables
python init_db.py

# Verify database connection
python -c "from app.core.database import engine; print('✅ Database connected')"
```

---

## Step 3: Deploy Smart Contracts (2-4 hours)

### A. Deploy to EVM Chains (Ethereum, Polygon, Base, BSC, Arbitrum, Avalanche)

```bash
cd contracts

# Testnet deployments (for testing)
npx hardhat run scripts/deploy.js --network sepolia           # Ethereum testnet
npx hardhat run scripts/deploy.js --network polygonAmoy       # Polygon testnet
npx hardhat run scripts/deploy.js --network baseSepolia       # Base testnet
npx hardhat run scripts/deploy.js --network bscTestnet        # BSC testnet
npx hardhat run scripts/deploy.js --network arbitrumSepolia   # Arbitrum testnet
npx hardhat run scripts/deploy.js --network fuji              # Avalanche testnet

# Mainnet deployments (for production)
npx hardhat run scripts/deploy.js --network ethereum    # Ethereum
npx hardhat run scripts/deploy.js --network polygon     # Polygon
npx hardhat run scripts/deploy.js --network base        # Base
npx hardhat run scripts/deploy.js --network bsc         # BSC
npx hardhat run scripts/deploy.js --network arbitrum    # Arbitrum
npx hardhat run scripts/deploy.js --network avalanche   # Avalanche

cd ..
```

### B. Update .env with Contract Addresses

After each deployment, add the proxy address to `.env`:

```bash
SUBSCRIPTION_CONTRACT_ETHEREUM=0x...
SUBSCRIPTION_CONTRACT_POLYGON=0x...
SUBSCRIPTION_CONTRACT_BASE=0x...
SUBSCRIPTION_CONTRACT_BSC=0x...
SUBSCRIPTION_CONTRACT_ARBITRUM=0x...
SUBSCRIPTION_CONTRACT_AVALANCHE=0x...
```

### C. Deploy to Stellar/Soroban (Optional)

```bash
# Install Stellar CLI
cargo install --locked stellar-cli --features opt

# Deploy Soroban contract
python contracts/soroban/deploy_soroban.py --network testnet

# Update .env
SUBSCRIPTION_CONTRACT_SOROBAN=C...
```

### D. Deploy to Solana (Optional)

```bash
# Install Anchor CLI
cargo install --git https://github.com/coral-xyz/anchor avm
avm install latest && avm use latest

# Deploy Solana program
python contracts/solana/deploy_solana.py --network devnet

# Update .env
SUBSCRIPTION_PROGRAM_SOLANA=...
```

### E. Deploy to Tron (Optional)

```bash
# Deploy Tron contract
python contracts/tron/deploy_tron.py --network nile

# Update .env
SUBSCRIPTION_CONTRACT_TRON=T...
```

---

## Step 4: Start the API Server (2 minutes)

```bash
# Development mode
python app/main.py

# Production mode (with Gunicorn)
gunicorn app.main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

Server will be available at: `http://localhost:8000`

API Documentation: `http://localhost:8000/docs`

---

## Step 5: Start Blockchain Listeners (2 minutes)

```bash
# In a separate terminal
python run_listeners.py

# Or start specific chains only
python run_listeners.py polygon avalanche stellar
```

---

## Step 6: Test the System (1-2 hours)

### A. Create a Test Merchant

```bash
curl -X POST http://localhost:8000/merchant/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "merchant@test.com",
    "password": "Test123!@#",
    "business_name": "Test Store",
    "country": "US"
  }'
```

### B. Complete Onboarding

```bash
# Login to get access token
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "merchant@test.com",
    "password": "Test123!@#"
  }'

# Complete onboarding (generates wallets)
curl -X POST http://localhost:8000/onboarding/complete \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "business_name": "Test Store",
    "chains": ["polygon", "avalanche", "stellar"],
    "tokens": ["USDC", "USDT"]
  }'
```

### C. Create a Payment Session

```bash
curl -X POST http://localhost:8000/payments/create \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": "10.00",
    "currency": "USD",
    "chain": "polygon",
    "token": "USDC",
    "description": "Test payment"
  }'
```

### D. Check Wallet Addresses

```bash
curl -X GET http://localhost:8000/merchant/wallets \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

Verify that addresses are real (not placeholders):
- Stellar: `G...` (56 chars)
- EVM chains: `0x...` (42 chars)
- Solana: base58 (~44 chars)

### E. Test Payment Detection

1. Send USDC to the generated wallet address
2. Wait for blockchain listener to detect payment
3. Check payment status:

```bash
curl -X GET http://localhost:8000/payments/status/SESSION_ID \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

Status should change: `CREATED` → `PENDING` → `CONFIRMED`

---

## Step 7: Production Deployment

### A. Security Checklist
- [ ] Set `USE_MAINNET=true`
- [ ] Set strong `JWT_SECRET` (32+ chars)
- [ ] Set `ENVIRONMENT=production`
- [ ] Change `ADMIN_PASSWORD` from default
- [ ] Set specific `CORS_ORIGINS` (not `*`)
- [ ] Use PostgreSQL (not SQLite)
- [ ] Use HTTPS/TLS
- [ ] Set up firewall rules
- [ ] Enable rate limiting

### B. Infrastructure
- [ ] Deploy behind reverse proxy (NGINX/Caddy)
- [ ] Set up SSL certificate (Let's Encrypt)
- [ ] Configure domain name
- [ ] Set up monitoring (Prometheus/Grafana)
- [ ] Set up log aggregation (ELK/Loki)
- [ ] Configure backups (database + .env)

### C. Blockchain
- [ ] Deploy contracts to mainnet
- [ ] Fund relayer wallets with gas tokens
- [ ] Use private RPC endpoints
- [ ] Set up RPC failover
- [ ] Monitor gas prices

### D. Run as Services (Linux)

```bash
# API service
sudo nano /etc/systemd/system/dari-api.service
```

```ini
[Unit]
Description=Dari Payment Gateway API
After=postgresql.service

[Service]
WorkingDirectory=/opt/dari-backend
ExecStart=/opt/dari-backend/venv/bin/gunicorn app.main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
Restart=always
EnvironmentFile=/opt/dari-backend/.env

[Install]
WantedBy=multi-user.target
```

```bash
# Blockchain listeners service
sudo nano /etc/systemd/system/dari-listeners.service
```

```ini
[Unit]
Description=Dari Blockchain Listeners
After=dari-api.service

[Service]
WorkingDirectory=/opt/dari-backend
ExecStart=/opt/dari-backend/venv/bin/python run_listeners.py
Restart=always
EnvironmentFile=/opt/dari-backend/.env

[Install]
WantedBy=multi-user.target
```

```bash
# Enable and start services
sudo systemctl enable dari-api dari-listeners
sudo systemctl start dari-api dari-listeners

# Check status
sudo systemctl status dari-api
sudo systemctl status dari-listeners
```

---

## Supported Chains & Tokens

| Chain | USDC | USDT | PYUSD | Recurring | Status |
|-------|------|------|-------|-----------|--------|
| Stellar | ✅ | ✅ | ❌ | ✅ | Production Ready |
| Ethereum | ✅ | ✅ | ✅ | ✅ | Production Ready |
| Polygon | ✅ | ✅ | ❌ | ✅ | Production Ready |
| Base | ✅ | ❌ | ❌ | ✅ | Production Ready |
| BSC | ✅ | ✅ | ❌ | ✅ | Production Ready |
| Arbitrum | ✅ | ✅ | ❌ | ✅ | Production Ready |
| Avalanche | ✅ | ✅ | ❌ | ✅ | Production Ready |
| Tron | ✅ | ✅ | ❌ | ✅ | Production Ready |
| Solana | ✅ | ❌ | ❌ | ✅ | Partial (no listener) |
| Soroban | ✅ | ❌ | ❌ | ✅ | Production Ready |

---

## API Endpoints Quick Reference

### Authentication
- `POST /auth/register` - Register merchant
- `POST /auth/login` - Login
- `POST /auth/refresh` - Refresh token

### Payments
- `POST /payments/create` - Create payment
- `GET /payments/{id}` - Get payment
- `GET /payments/status/{id}` - Check status

### Subscriptions
- `POST /subscriptions/create` - Create subscription
- `GET /subscriptions/{id}` - Get subscription
- `PATCH /subscriptions/{id}/cancel` - Cancel

### Refunds
- `POST /refunds` - Create refund
- `GET /refunds` - List refunds

### Webhooks
- `POST /webhooks/register` - Register webhook
- `GET /webhooks/list` - List webhooks

### Merchant
- `GET /merchant/profile` - Get profile
- `GET /merchant/balance` - Check balance
- `GET /merchant/wallets` - List wallets

---

## Troubleshooting

### Database Connection Error
```bash
# Check PostgreSQL is running
sudo systemctl status postgresql

# Test connection
psql -U user -d dari_payments -h localhost
```

### Blockchain Listener Not Detecting Payments
```bash
# Check listener status
curl http://localhost:8000/admin/blockchain/status

# Check logs
tail -f dari_payments.log | grep "Payment detected"

# Verify RPC endpoint
curl -X POST YOUR_RPC_URL \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}'
```

### Contract Deployment Failed
```bash
# Check relayer wallet has gas tokens
# Ethereum: ETH
# Polygon: MATIC
# Avalanche: AVAX
# BSC: BNB
# Arbitrum: ETH
# Base: ETH

# Check gas price
npx hardhat run scripts/check-gas.js --network polygon
```

### Wallet Generation Returns Placeholder
```bash
# Install required libraries
pip install stellar-sdk eth-account

# Verify installation
python -c "from stellar_sdk import Keypair; print('✅ stellar-sdk installed')"
python -c "from eth_account import Account; print('✅ eth-account installed')"
```

---

## Support & Resources

- **API Documentation:** `http://localhost:8000/docs`
- **MVP Readiness Assessment:** `MVP_READINESS_ASSESSMENT.md`
- **Implementation Complete:** `IMPLEMENTATION_COMPLETE.md`
- **Deployment Guide:** `docs/blockchain/DEPLOYMENT_GUIDE.md`
- **Blockchain Integration:** `docs/blockchain/REAL_BLOCKCHAIN_INTEGRATION.md`

---

## Next Steps After Launch

1. Monitor transaction volume and success rates
2. Set up alerts for failed payments/refunds
3. Build official SDKs (JavaScript, Python, PHP)
4. Add more chains (Optimism, zkSync, Fantom)
5. Implement advanced fraud detection
6. Add fiat on/off ramp integration
7. Build merchant dashboard UI
8. Add multi-signature wallet support

---

**You're ready to launch! 🚀**

Estimated total time: 4-8 hours from start to production.
