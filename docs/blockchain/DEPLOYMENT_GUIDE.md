# Deployment & Setup Guide

Complete guide to deploy Dari for Business payment gateway across all supported blockchains.

## Prerequisites

- Python 3.10+
- PostgreSQL 14+
- Node.js 18+ (for contract deployment)
- Funded deployer wallet (for gas fees)

## Quick Start

```bash
# 1. Clone and install
git clone https://github.com/abhiramsakaray/dari-for-bussiness-backend.git
cd dari-for-bussiness-backend
pip install -r requirements.txt

# 2. Copy and configure environment
cp .env.example .env
# Edit .env with your credentials

# 3. Initialize database
python init_db.py

# 4. Start API server
uvicorn app.main:app --host 0.0.0.0 --port 8001

# 5. Start blockchain listeners (separate terminal)
python run_listeners.py                     # All enabled chains
python run_listeners.py polygon bsc tron    # Specific chains only
```

---

## Environment Variables

### Core

| Variable | Description | Required |
|----------|-------------|----------|
| `DATABASE_URL` | PostgreSQL connection string | ✅ |
| `JWT_SECRET` | JWT signing secret (min 32 chars) | ✅ |
| `APP_BASE_URL` | Public URL of your API | ✅ |
| `USE_MAINNET` | `true` for production, `false` for testnet | ✅ |
| `RELAYER_PRIVATE_KEY` | Deployer/relayer wallet private key | ✅ |

### Chain Enable/Disable

| Variable | Default | Description |
|----------|---------|-------------|
| `STELLAR_ENABLED` | `true` | Stellar network |
| `ETHEREUM_ENABLED` | `true` | Ethereum mainnet/Sepolia |
| `POLYGON_ENABLED` | `true` | Polygon mainnet/Amoy |
| `BASE_ENABLED` | `true` | Base mainnet/Sepolia |
| `BSC_ENABLED` | `true` | BNB Smart Chain |
| `ARBITRUM_ENABLED` | `true` | Arbitrum One |
| `TRON_ENABLED` | `true` | Tron network |
| `SOLANA_ENABLED` | `false` | Solana (requires solders) |

### RPC URLs (override defaults)

| Variable | Default |
|----------|---------|
| `ETHEREUM_MAINNET_RPC_URL` | `https://eth.llamarpc.com` |
| `POLYGON_MAINNET_RPC_URL` | `https://polygon-rpc.com` |
| `BASE_MAINNET_RPC_URL` | `https://mainnet.base.org` |
| `BSC_MAINNET_RPC_URL` | `https://bsc-dataseed.bnbchain.org` |
| `ARBITRUM_MAINNET_RPC_URL` | `https://arb1.arbitrum.io/rpc` |
| `SOLANA_MAINNET_RPC_URL` | `https://api.mainnet-beta.solana.com` |

> **Tip:** Use private RPC providers (Alchemy, Infura, QuickNode) for production to avoid rate limits.

### Subscription Contract Addresses

After deploying `DariSubscriptions.sol`, set the proxy addresses:

| Variable | Description |
|----------|-------------|
| `SUBSCRIPTION_CONTRACT_ETHEREUM` | Ethereum proxy address |
| `SUBSCRIPTION_CONTRACT_POLYGON` | Polygon proxy address |
| `SUBSCRIPTION_CONTRACT_BASE` | Base proxy address |
| `SUBSCRIPTION_CONTRACT_BSC` | BSC proxy address |
| `SUBSCRIPTION_CONTRACT_ARBITRUM` | Arbitrum proxy address |

---

## Contract Deployment (EVM Chains)

The `DariSubscriptions.sol` contract works on **all EVM chains**: Ethereum, Polygon, Base, BSC, Arbitrum.

### Setup

```bash
cd contracts
npm install
```

### Deploy to Each Chain

```bash
# Testnet deployments
npx hardhat run scripts/deploy.js --network sepolia           # Ethereum testnet
npx hardhat run scripts/deploy.js --network polygonAmoy       # Polygon testnet
npx hardhat run scripts/deploy.js --network baseSepolia       # Base testnet
npx hardhat run scripts/deploy.js --network bscTestnet        # BSC testnet
npx hardhat run scripts/deploy.js --network arbitrumSepolia   # Arbitrum testnet

# Mainnet deployments
npx hardhat run scripts/deploy.js --network ethereum    # Ethereum
npx hardhat run scripts/deploy.js --network polygon     # Polygon
npx hardhat run scripts/deploy.js --network base        # Base
npx hardhat run scripts/deploy.js --network bsc         # BSC
npx hardhat run scripts/deploy.js --network arbitrum    # Arbitrum
```

### Verify Contracts

```bash
npx hardhat verify --network polygon <PROXY_ADDRESS>
npx hardhat verify --network bsc <PROXY_ADDRESS>
npx hardhat verify --network arbitrum <PROXY_ADDRESS>
```

### Post-Deploy Checklist

For each chain:

1. **Set the relayer address** — the backend wallet that executes subscription payments:
   ```
   contract.setRelayer(RELAYER_WALLET_ADDRESS)
   ```

2. **Whitelist stablecoins** — add USDC and USDT addresses:
   ```
   contract.addSupportedToken(USDC_ADDRESS)
   contract.addSupportedToken(USDT_ADDRESS)
   ```

3. **Update `.env`** — set `SUBSCRIPTION_CONTRACT_<CHAIN>=<PROXY_ADDRESS>`

4. **Enable the scheduler**:
   ```
   WEB3_SUBSCRIPTIONS_ENABLED=true
   SCHEDULER_INTERVAL_SECONDS=60
   ```

---

## Supported Tokens Per Chain

| Chain | USDC | USDT | PYUSD | Notes |
|-------|------|------|-------|-------|
| Stellar | ✅ | ✅ | ❌ | Uses Horizon API |
| Ethereum | ✅ | ✅ | ✅ | High gas, use for large payments |
| Polygon | ✅ | ✅ | ❌ | Low gas, recommended for most payments |
| Base | ✅ | ❌ | ❌ | L2, very low gas |
| BSC | ✅ | ✅ | ❌ | Low gas, large user base |
| Arbitrum | ✅ | ✅ | ❌ | L2, low gas, fast finality |
| Tron | ✅ | ✅ | ❌ | Uses TronGrid API |
| Solana | ✅ | ❌ | ❌ | Uses SPL tokens |

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  FastAPI Server (API)                │
│  • Merchant CRUD, Payment Sessions, Invoices        │
│  • Tax Reports, Analytics, Webhook delivery         │
└──────────────┬──────────────────────────┬───────────┘
               │                          │
    ┌──────────▼──────────┐    ┌─────────▼──────────┐
    │  Blockchain Registry │    │  Subscription      │
    │  (Payment Listeners) │    │  Scheduler (cron)  │
    └──────────┬──────────┘    └─────────┬──────────┘
               │                          │
    ┌──────────▼──────────────────────────▼──────────┐
    │              Blockchain Networks                │
    │  Stellar │ Ethereum │ Polygon │ Base            │
    │  BSC │ Arbitrum │ Tron │ Solana                 │
    └────────────────────────────────────────────────┘
```

**Listeners** poll each chain for incoming stablecoin transfers to merchant deposit addresses. When a payment matches a session, it's confirmed and the merchant is notified via webhook.

**Subscription Scheduler** runs every 60s, finds due subscriptions, and uses the gasless relayer to call `executePayment()` on the `DariSubscriptions` contract.

---

## Production Checklist

- [ ] Set `USE_MAINNET=true`
- [ ] Use a strong `JWT_SECRET` (32+ chars, random)
- [ ] Set `ENVIRONMENT=production` (hides error details)
- [ ] Use PostgreSQL (not SQLite)
- [ ] Use private RPC endpoints (Alchemy/Infura/QuickNode)
- [ ] Deploy subscription contracts on desired chains
- [ ] Fund the relayer wallet with gas tokens (ETH, MATIC, BNB, etc.)
- [ ] Set `WEBHOOK_SIGNING_SECRET` for global fallback
- [ ] Enable rate limiting (`RATE_LIMIT_ENABLED=true`)
- [ ] Run behind NGINX/Caddy with HTTPS
- [ ] Set up log rotation and monitoring
- [ ] Run listeners as a separate process (or systemd service)

---

## Running as Services (Linux)

### API Server

```ini
# /etc/systemd/system/dari-api.service
[Unit]
Description=Dari Payment Gateway API
After=postgresql.service

[Service]
WorkingDirectory=/opt/dari-backend
ExecStart=/opt/dari-backend/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8001 --workers 4
Restart=always
EnvironmentFile=/opt/dari-backend/.env

[Install]
WantedBy=multi-user.target
```

### Blockchain Listeners

```ini
# /etc/systemd/system/dari-listeners.service
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
sudo systemctl enable dari-api dari-listeners
sudo systemctl start dari-api dari-listeners
```
