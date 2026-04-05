# Multi-Chain Subscription Smart Contracts — Technical Specification

## Overview

Dari for Business uses smart contracts on each supported blockchain to enable **server-side recurring payments** without requiring the user's private key. The user only signs a one-time token approval, and the platform's relayer executes payments automatically.

---

## Contract Comparison Matrix

| Feature | EVM (Ethereum/Polygon/Base/BSC/Arbitrum) | Tron (TVM) | Solana (Anchor) | Stellar (Soroban) |
|---------|------|------|--------|---------|
| **Language** | Solidity 0.8.24 | Solidity 0.8.18 | Rust (Anchor) | Rust (Soroban SDK) |
| **Token Standard** | ERC-20 | TRC-20 | SPL Token | Stellar Asset Contract (SAC) |
| **Approval Mechanism** | `approve()` | `approve()` | `approve()` (delegation) | `approve()` |
| **Pull Mechanism** | `transferFrom()` | `transferFrom()` | `token::transfer` via delegate | `transfer_from()` via SAC |
| **Upgradeability** | UUPS Proxy | None (TVM limitation) | Program upgrade authority | Contract upgrade (admin) |
| **Storage Model** | Mapping slots | Mapping slots | PDA accounts | Persistent storage |
| **Subscription ID** | Auto-increment uint256 | Auto-increment uint256 | u64 + PDA seeds | u64 in persistent storage |

---

## Subscription Lifecycle

```
┌──────────────────────────────────────────────────────────────┐
│  1. User calls token.approve(contract, amount × N_cycles)   │
│  2. Relayer calls contract.createSubscription(...)           │
│  3. Scheduler detects next_payment ≤ now                    │
│  4. Relayer calls contract.executePayment(sub_id)           │
│  5. Contract calls token.transferFrom(user → merchant)      │
│  6. contract.nextPayment = block.timestamp + interval       │
│  7. Repeat from step 3                                      │
│                                                              │
│  Cancel: user/merchant/relayer calls cancelSubscription()   │
└──────────────────────────────────────────────────────────────┘
```

---

## File Index

### Smart Contracts

| File | Chain | Description |
|------|-------|-------------|
| `contracts/src/DariSubscriptions.sol` | EVM | Main UUPS-upgradeable contract |
| `contracts/tron/DariSubscriptionsTron.sol` | Tron | TVM-compatible adaptation |
| `contracts/solana/dari_subscriptions/src/lib.rs` | Solana | Anchor program |
| `contracts/soroban/dari_subscriptions/src/lib.rs` | Stellar | Soroban contract |

### Deploy Scripts

| File | Chain |
|------|-------|
| `contracts/scripts/deploy.js` | EVM (Hardhat) |
| `contracts/tron/deploy_tron.py` | Tron |
| `contracts/solana/deploy_solana.py` | Solana |
| `contracts/soroban/deploy_soroban.py` | Stellar |

### Backend Relayers

| File | Chain | SDK |
|------|-------|-----|
| `app/services/gasless_relayer.py` | EVM | web3.py |
| `app/services/tron_relayer.py` | Tron | tronpy |
| `app/services/solana_relayer.py` | Solana | solders + solana-py |
| `app/services/soroban_relayer.py` | Stellar | stellar-sdk |

### Scheduler

| File | Description |
|------|-------------|
| `app/services/subscription_scheduler.py` | Dispatches to chain-specific relayers |

---

## Security Model

### Access Control

- **executePayment**: Relayer only
- **createSubscription**: Relayer only
- **cancelSubscription**: Subscriber, Merchant, Relayer, or Admin
- **updateSubscription**: Relayer only (amount can only decrease)
- **pause/unpause**: Admin only
- **cancel during pause**: Always allowed (users can exit)

### Safety Patterns

1. **CEI (Checks-Effects-Interactions)**: All contracts update state before making external calls
2. **Reentrancy Guard**: Manual lock (Tron), program-level (Solana/Soroban)
3. **Amount Cannot Increase**: `updateSubscription` rejects `newAmount > oldAmount`
4. **Token Whitelist**: Only admin-approved tokens can be used
5. **Minimum Interval**: All contracts enforce ≥ 3600 seconds (1 hour)

---

## Environment Variables

```env
# EVM
RELAYER_PRIVATE_KEY=0x...
SUBSCRIPTION_CONTRACT_ETHEREUM=0x...
SUBSCRIPTION_CONTRACT_POLYGON=0x...
SUBSCRIPTION_CONTRACT_BASE=0x...
SUBSCRIPTION_CONTRACT_BSC=0x...
SUBSCRIPTION_CONTRACT_ARBITRUM=0x...

# Tron
TRON_RELAYER_PRIVATE_KEY=<hex>
SUBSCRIPTION_CONTRACT_TRON=<base58>

# Solana
SOLANA_RELAYER_PRIVATE_KEY=<64-byte-hex>
SUBSCRIPTION_PROGRAM_SOLANA=<base58>

# Stellar
SOROBAN_RELAYER_SECRET_KEY=S...
SUBSCRIPTION_CONTRACT_SOROBAN=<contract-id>
```
