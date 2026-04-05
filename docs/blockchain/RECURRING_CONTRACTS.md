# Recurring Payment Contracts — Per-Chain Guide

Dari for Business uses smart contracts for automated recurring (subscription) payments. This guide covers the contract architecture and deployment for each supported chain.

---

## EVM Chains (Ethereum, Polygon, Base, BSC, Arbitrum)

### Contract: `DariSubscriptions.sol`

All 5 EVM chains share the **same Solidity contract** — `contracts/src/DariSubscriptions.sol`.

**Architecture:** UUPS upgradeable proxy pattern (OpenZeppelin)

**Key features:**
- Subscribers approve the contract to spend USDC/USDT via ERC-20 `approve()`
- Backend's gasless relayer calls `createSubscription()` and `executePayment()`
- Only the authorized relayer can execute payments (prevents unauthorized charges)
- Subscribers and merchants can cancel at any time
- Circuit breaker (pause/unpause) for emergencies
- Reentrancy protection on all state-changing functions

### Flow

```
1. Customer → ERC-20.approve(DariSubscriptions, amount)
2. Relayer → DariSubscriptions.createSubscription(subscriber, merchant, token, amount, interval)
3. Every interval:
   Scheduler detects due subscription → Relayer → DariSubscriptions.executePayment(subId)
   Contract → ERC-20.transferFrom(subscriber → merchant)
```

### Deploy Commands

```bash
cd contracts

# Install dependencies
npm install

# Deploy (UUPS proxy pattern)
npx hardhat run scripts/deploy.js --network <NETWORK>
```

| Network Key | Chain | Chain ID |
|-------------|-------|----------|
| `sepolia` | Ethereum Testnet | 11155111 |
| `ethereum` | Ethereum Mainnet | 1 |
| `polygonAmoy` | Polygon Testnet | 80002 |
| `polygon` | Polygon Mainnet | 137 |
| `baseSepolia` | Base Testnet | 84532 |
| `base` | Base Mainnet | 8453 |
| `bscTestnet` | BSC Testnet | 97 |
| `bsc` | BSC Mainnet | 56 |
| `arbitrumSepolia` | Arbitrum Testnet | 421614 |
| `arbitrum` | Arbitrum Mainnet | 42161 |

### Post-Deploy Setup

```javascript
// 1. Set the backend relayer wallet
await contract.setRelayer("0xYOUR_RELAYER_ADDRESS");

// 2. Whitelist stablecoins
await contract.addSupportedToken("USDC_CONTRACT_ADDRESS");
await contract.addSupportedToken("USDT_CONTRACT_ADDRESS");
```

### Gas Estimates

| Operation | Gas (approx) | Cost @ 30 gwei |
|-----------|-------------|----------------|
| createSubscription | ~150,000 | ~$0.15 |
| executePayment | ~85,000 | ~$0.08 |
| cancelSubscription | ~50,000 | ~$0.05 |

> On L2s (Polygon, Base, BSC, Arbitrum), gas costs are typically **<$0.01** per operation.

### Backend Configuration

After deploying to each chain, set these in `.env`:

```env
SUBSCRIPTION_CONTRACT_ETHEREUM=0x...
SUBSCRIPTION_CONTRACT_POLYGON=0x...
SUBSCRIPTION_CONTRACT_BASE=0x...
SUBSCRIPTION_CONTRACT_BSC=0x...
SUBSCRIPTION_CONTRACT_ARBITRUM=0x...

# Fund the relayer wallet with gas on each chain
RELAYER_PRIVATE_KEY=0x...

# Enable the scheduler
WEB3_SUBSCRIPTIONS_ENABLED=true
SCHEDULER_INTERVAL_SECONDS=60
SCHEDULER_BATCH_SIZE=100
```

---

## Tron

### Contract: TRC-20 Approval-Based

Tron uses the same approval-based model but with TRC-20 tokens instead of ERC-20.

**Status:** The EVM contract `DariSubscriptions.sol` **cannot** be deployed directly on Tron because Tron uses a modified EVM (TVM). However, the logic is compatible via Tron's Solidity compiler.

### Tron Deployment

```bash
# Use TronBox instead of Hardhat
npm install -g tronbox

# In a separate tron-contracts directory:
tronbox compile
tronbox migrate --network nile      # Testnet
tronbox migrate --network mainnet   # Mainnet
```

**Tron-specific notes:**
- Use `tronWeb.transactionBuilder.triggerSmartContract()` for relayer calls
- Energy and bandwidth are consumed instead of gas
- USDT (TRC-20): `TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t` (mainnet)
- USDC (TRC-20): `TEkxiTehnzSmSe2XqrBj4w32RUN966rdz8` (mainnet)

### Alternative: Off-Chain Scheduling

For Tron subscriptions, the backend can use off-chain scheduling:
1. Store subscription details in the database
2. When payment is due, prompt the customer to sign a transaction
3. Use the Tron listener to confirm the payment

This approach avoids the need for a Tron-specific contract.

---

## Solana

### Program: Anchor-Based SPL Token Subscription

Solana uses **Programs** (not smart contracts) written in Rust with the Anchor framework.

**Status:** Planned. The architecture is designed but the program is not yet deployed.

### Planned Architecture

```rust
// Anchor program: dari_subscriptions
pub mod dari_subscriptions {
    // create_subscription(subscriber, merchant, token_mint, amount, interval)
    // execute_payment(subscription_id)  — called by relayer
    // cancel_subscription(subscription_id)
}
```

**Solana-specific notes:**
- Uses SPL Token `approve()` delegation (similar to ERC-20 approve)
- USDC Mint: `EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v` (mainnet)
- Requires `solders` and `anchorpy` pip packages for the backend listener
- Programs are deployed to Solana Devnet/Mainnet via `anchor deploy`
- Transaction fees are ~$0.00025 per transaction

### Backend Integration (When Ready)

```env
SOLANA_ENABLED=true
SOLANA_MAINNET_RPC_URL=https://api.mainnet-beta.solana.com
SOLANA_SUBSCRIPTION_PROGRAM_ID=<PROGRAM_ADDRESS>
```

The `solana_listener.py` would use `solders` to subscribe to SPL token transfer events on merchant deposit addresses.

---

## Stellar

### Contract: Soroban Smart Contract (Optional)

Stellar supports recurring payments via Soroban smart contracts on the Stellar network.

**Status:** Optional. Basic Stellar payments work without contracts via the Horizon API listener. Soroban escrow support is available for advanced use cases.

**Stellar-specific notes:**
- USDC Issuer (mainnet): `GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN`
- Uses memo field for payment routing
- Transactions cost ~0.00001 XLM (~$0.000005)

---

## Summary: Contract Deployment Status

| Chain | Contract | Status | Deploy Tool |
|-------|----------|--------|-------------|
| Ethereum | `DariSubscriptions.sol` | ✅ Ready | Hardhat |
| Polygon | `DariSubscriptions.sol` | ✅ Ready | Hardhat |
| Base | `DariSubscriptions.sol` | ✅ Ready | Hardhat |
| BSC | `DariSubscriptions.sol` | ✅ Ready | Hardhat |
| Arbitrum | `DariSubscriptions.sol` | ✅ Ready | Hardhat |
| Tron | TVM adaptation needed | ⚠️ Off-chain fallback available | TronBox |
| Solana | Anchor program | 🔜 Planned | Anchor |
| Stellar | Soroban (optional) | ℹ️ Horizon-based | Soroban CLI |
