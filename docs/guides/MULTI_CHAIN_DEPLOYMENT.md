# Multi-Chain Subscription Contracts — Deployment Guide

This guide covers deploying the Dari for Business subscription contracts to **Tron**, **Solana**, and **Stellar (Soroban)** testnets and mainnets.

> **Prerequisites**: The EVM contracts (Ethereum, Polygon, Base, BSC, Arbitrum) are deployed via Hardhat using `contracts/scripts/deploy.js`. This guide covers only the non-EVM chains.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Tron (TVM)](#tron-tvm)
3. [Solana (Anchor)](#solana-anchor)
4. [Stellar (Soroban)](#stellar-soroban)
5. [Post-Deployment](#post-deployment)
6. [Contract Architecture](#contract-architecture)

---

## Prerequisites

### Python Dependencies
```bash
pip install tronpy solders solana stellar-sdk python-dotenv
```

### Chain-Specific Tools

| Chain | Tool | Install Command |
|-------|------|----------------|
| Tron | `solc` (Solidity compiler) | `npm install -g solc` |
| Solana | Solana CLI + Anchor CLI | See [Solana docs](https://docs.solanalabs.com/cli/install) |
| Stellar | `stellar` CLI + Rust | `cargo install --locked stellar-cli --features opt` |

### Wallet Setup

Each chain requires a funded relayer wallet:

| Chain | Key Format | Env Variable |
|-------|-----------|-------------|
| Tron | Hex private key (no 0x) | `TRON_RELAYER_PRIVATE_KEY` |
| Solana | 64-byte keypair as hex | `SOLANA_RELAYER_PRIVATE_KEY` |
| Stellar | Secret key (S...) | `SOROBAN_RELAYER_SECRET_KEY` |

---

## Tron (TVM)

### Contract: `DariSubscriptionsTron.sol`

TVM-compatible Solidity contract using TRC-20 `approve()` + `transferFrom()` pull model.

### Deploy to Nile Testnet

```bash
# 1. Fund your wallet with test TRX from https://nileex.io/join/getJoinPage
# 2. Set your private key in .env
# 3. Deploy
python contracts/tron/deploy_tron.py --network nile
```

### Deploy to Mainnet

```bash
python contracts/tron/deploy_tron.py --network mainnet
```

### Output

The script will print:
```
SUBSCRIPTION_CONTRACT_TRON=<deployed-address>
```

Add this to your `.env` file.

### Supported Tokens (auto-added during deployment)

| Network | USDT | USDC |
|---------|------|------|
| Nile Testnet | `TXLAQ63Xg1NAzckPwKHvzw7CSEmLMEqcdj` | `TEMVynQpntMqkPxP6wXTW2K7e4sM3cQnAv` |
| Mainnet | `TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t` | `TEkxiTehnzSmSe2XqrBj4w32RUN966rdz8` |

---

## Solana (Anchor)

### Program: `dari_subscriptions`

Anchor program using SPL Token `approve()` delegation for pull-payments.

### Prerequisites

```bash
# Install Solana CLI
sh -c "$(curl -sSfL https://release.anza.xyz/stable/install)"

# Install Anchor CLI
cargo install --git https://github.com/coral-xyz/anchor avm
avm install latest
avm use latest

# Add WASM target (for Soroban, needed if doing both)
rustup target add wasm32-unknown-unknown
```

### Generate Relayer Keypair

```bash
# Generate a new keypair
solana-keygen new --outfile relayer-keypair.json

# Convert to hex for .env
python -c "import json; kp=json.load(open('relayer-keypair.json')); print(bytes(kp).hex())"
```

### Deploy to Devnet

```bash
# 1. Fund wallet: solana airdrop 5 --url devnet
# 2. Set SOLANA_RELAYER_PRIVATE_KEY in .env
# 3. Deploy
python contracts/solana/deploy_solana.py --network devnet
```

### Deploy to Mainnet

```bash
python contracts/solana/deploy_solana.py --network mainnet
```

### Output

```
SUBSCRIPTION_PROGRAM_SOLANA=<program-id>
```

### Supported Mints

| Network | USDC | USDT |
|---------|------|------|
| Devnet | `4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU` | `Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB` |
| Mainnet | `EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v` | `Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB` |

---

## Stellar (Soroban)

### Contract: `DariSubscriptionsContract`

Soroban smart contract using the Stellar Asset Contract (SAC) `approve()` + `transfer_from()` mechanism.

### Prerequisites

```bash
# Install Stellar CLI
cargo install --locked stellar-cli --features opt

# Add WASM target
rustup target add wasm32-unknown-unknown
```

### Generate Relayer Keypair

```bash
# Generate using stellar CLI
stellar keys generate dari-relayer --network testnet

# Get the secret key for .env
stellar keys show dari-relayer
```

### Deploy to Testnet

```bash
# 1. Fund via friendbot (automatic when generating key with --network testnet)
# 2. Set SOROBAN_RELAYER_SECRET_KEY in .env
# 3. Deploy
python contracts/soroban/deploy_soroban.py --network testnet
```

### Deploy to Mainnet

```bash
python contracts/soroban/deploy_soroban.py --network mainnet
```

### Output

```
SUBSCRIPTION_CONTRACT_SOROBAN=<contract-id>
```

### USDC Contracts

| Network | USDC SAC Contract |
|---------|------------------|
| Testnet | `CBIELTK6YBZJU5UP2WWQEUCYKLPU6AUNZ2BQ4WWFEIE3USCIHMXQDAMA` |
| Mainnet | `CCW67TSZV3SSS2HXMBQ5JFGCKJNXKZM7UQUWUZPUTHXSTZLEO7SJMI` |

---

## Post-Deployment

### 1. Update `.env`

After deploying all contracts, your `.env` should contain:

```env
# Tron
TRON_RELAYER_PRIVATE_KEY=<your-hex-key>
SUBSCRIPTION_CONTRACT_TRON=<deployed-address>

# Solana
SOLANA_RELAYER_PRIVATE_KEY=<your-64-byte-hex>
SUBSCRIPTION_PROGRAM_SOLANA=<program-id>

# Stellar
SOROBAN_RELAYER_SECRET_KEY=<your-S-key>
SUBSCRIPTION_CONTRACT_SOROBAN=<contract-id>
```

### 2. Verify the Scheduler

The subscription scheduler automatically detects and routes payments to the correct chain relayer:

```python
from app.services.subscription_scheduler import scheduler
print(scheduler.get_status())
```

### 3. Test a Subscription Flow

1. Create a subscription via the API (specifying `chain: "tron"`, `"solana"`, or `"stellar"`)
2. The user approves the contract to spend their tokens
3. The scheduler detects due payments and calls the appropriate relayer
4. Verify payment execution in the `Web3SubscriptionPayment` table

---

## Contract Architecture

All three contracts implement the same interface:

| Function | Description | Access |
|----------|-------------|--------|
| `createSubscription` | Register a new subscription on-chain | Relayer only |
| `executePayment` | Pull due payment from subscriber | Relayer only |
| `cancelSubscription` | Deactivate a subscription | Subscriber / Merchant / Relayer / Admin |
| `updateSubscription` | Update amount (can only decrease) or interval | Relayer only |

### Security Features

- **CEI Pattern**: State updates before external calls
- **Access Control**: `onlyRelayer` modifier on payment execution
- **Pause/Unpause**: Circuit breaker for emergencies (cancel always works)
- **Amount Safety**: Amount can never increase via update (prevents abuse)
- **Token Whitelist**: Only approved stablecoins accepted

### Pull-Payment Flow

```
User → approve(contract, amount) → Contract stores subscription
                                          ↓
Scheduler detects due payment → Relayer calls executePayment()
                                          ↓
Contract calls transferFrom(subscriber, merchant, amount)
```
