# Blockchain Payment Listeners - Technical Documentation

## Overview

Dari for Business uses dedicated blockchain listeners to monitor payments across multiple blockchains in real-time. Each listener operates independently as a background service, monitoring the blockchain for payments to merchant wallet addresses.

**Architecture**: The system uses **direct blockchain monitoring** - no smart contracts or intermediary services are required for payment verification. Payments go directly from customers to merchant wallets.

---

## Table of Contents

1. [Stellar Listener](#stellar-listener)
2. [EVM Listener (Ethereum, Polygon, Base)](#evm-listener)
3. [Tron Listener](#tron-listener)
4. [Payment Verification Flow](#payment-verification-flow)
5. [Running Listeners](#running-listeners)
6. [Configuration](#configuration)
7. [Monitoring & Debugging](#monitoring--debugging)

---

## Stellar Listener

**File**: `app/services/stellar_listener.py`

### How It Works

The Stellar listener monitors payments to merchant Stellar addresses by streaming payment operations from the Horizon API.

#### Key Features

- **Supported Assets**: USDC, USDT, XLM (native)
- **Streaming API**: Uses Horizon's streaming endpoint for real-time updates
- **Memo-based Identification**: Matches payments to sessions using memo field
- **Multi-merchant**: Monitors all active merchants with configured Stellar addresses

#### Technical Details

```python
# API: Stellar Horizon API
# Endpoint: /accounts/{address}/payments

# Streaming connection to Horizon
payments_stream = server.payments()
    .for_account(merchant_address)
    .cursor(cursor)
    .stream()
```

#### Payment Verification Steps

1. **Stream Connection**: Establishes streaming connection to Horizon API for each merchant address
2. **Payment Detection**: Listens for payment operations (payment, path_payment_strict_receive, path_payment_strict_send)
3. **Memo Extraction**: Extracts transaction memo to identify payment session
4. **Asset Validation**: Verifies asset is USDC (GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN) or XLM
5. **Amount Verification**: Confirms payment amount matches expected amount (±0.01 tolerance)
6. **Destination Check**: Validates payment went to correct merchant address
7. **Database Update**: Marks payment session as PAID and stores transaction hash
8. **Webhook Notification**: Triggers webhook to notify merchant

#### Code Example

```python
async def validate_and_process_payment(
    self,
    tx_hash: str,
    destination: str,
    amount: str,
    memo: Optional[str],
    asset: Asset
):
    # Find session by memo
    session = db.query(PaymentSession).filter(
        PaymentSession.id == memo
    ).first()
    
    # Validate destination matches merchant
    if destination != session.merchant.stellar_address:
        return False
    
    # Validate amount
    expected_amount = float(session.amount_usdc)
    received_amount = float(amount)
    
    if abs(received_amount - expected_amount) > 0.01:
        return False
    
    # Mark as paid
    session.status = PaymentStatus.PAID
    session.tx_hash = tx_hash
    session.paid_at = datetime.utcnow()
    db.commit()
```

#### Error Handling

- **Connection Timeouts**: 3 retry attempts with 5-second delays
- **Horizon Errors**: Logged and skipped, moves to next merchant
- **Invalid Address**: Validation before streaming starts

---

## EVM Listener

**File**: `app/services/blockchains/evm_listener.py`

### How It Works

The EVM listener monitors ERC20 token transfers across Ethereum, Polygon, and Base by polling for Transfer events.

#### Key Features

- **Supported Chains**: Ethereum, Polygon, Base
- **Supported Tokens**: USDC, USDT, PYUSD
- **Event-based**: Monitors ERC20 Transfer events
- **Confirmation Tracking**: Waits for required confirmations before processing
- **Multi-RPC**: Falls back to alternative RPCs if primary fails

#### Technical Details

```python
# Ethereum Confirmations: 12 blocks (~3 minutes)
# Polygon Confirmations: 128 blocks (~4 minutes)
# Base Confirmations: 10 blocks (~20 seconds)

# ERC20 Transfer Event Signature
Transfer(address indexed from, address indexed to, uint256 value)
Topic: 0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef
```

#### Payment Verification Steps

1. **Block Polling**: Polls for new blocks every 5-15 seconds (chain-dependent)
2. **Log Filtering**: Fetches Transfer event logs for tracked token contracts
3. **Address Matching**: Filters transfers to watched merchant addresses
4. **Amount Decoding**: Decodes transfer amount from log data
5. **Confirmation Waiting**: Waits for required confirmations (chain-specific)
6. **Database Lookup**: Finds payment session by matching amount and destination
7. **Update & Notify**: Marks as paid and sends webhook

#### Code Example

```python
async def _process_transfer_log(self, log: Dict, current_block: int):
    # Decode addresses from topics
    from_address = "0x" + topics[1].hex()[-40:]
    to_address = "0x" + topics[2].hex()[-40:]
    
    # Check if to our watched address
    if to_address.lower() not in self._watched_addresses:
        return
    
    # Decode amount
    amount_raw = int(log["data"], 16)
    amount = Decimal(amount_raw) / Decimal(10 ** token.decimals)
    
    # Calculate confirmations
    block_number = log["blockNumber"]
    confirmations = current_block - block_number
    
    # Only process if enough confirmations
    if confirmations >= self.config.confirmations_required:
        await self._notify_payment(payment_info)
```

#### Confirmation Requirements

| Chain | Confirmations | Time |
|-------|--------------|------|
| Ethereum | 12 blocks | ~3 minutes |
| Polygon | 128 blocks | ~4 minutes |
| Base | 10 blocks | ~20 seconds |

#### Token Addresses

**Ethereum Mainnet:**
- USDC: `0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48`
- USDT: `0xdAC17F958D2ee523a2206206994597C13D831ec7`
- PYUSD: `0x6c3ea9036406852006290770BEdFcAbA0e23A0e8`

**Polygon Mainnet:**
- USDC: `0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359`
- USDT: `0xc2132D05D31c914a87C6611C10748AEb04B58e8F`

**Base Mainnet:**
- USDC: `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`

#### Error Handling

- **RPC Failures**: Automatic fallback to alternative RPC endpoints
- **Block Reorganizations**: Re-processes recent blocks on reorg detection
- **Rate Limiting**: Exponential backoff with jitter

---

## Tron Listener

**File**: `app/services/blockchains/tron_listener.py`

### How It Works

The Tron listener monitors TRC20 token transfers using the TronGrid API.

#### Key Features

- **Supported Tokens**: USDT (TRC20), USDC (TRC20)
- **API-based**: Uses TronGrid REST API
- **High Throughput**: Optimal for USDT which has high transaction volume on Tron
- **Fast Finality**: ~19 block confirmations (~57 seconds)

#### Technical Details

```python
# API: TronGrid API
# Endpoint: /v1/accounts/{address}/transactions/trc20

# TRC20 USDT Contract
USDT_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"

# Poll interval: 10 seconds
# Confirmations: 19 blocks (~57 seconds)
```

#### Payment Verification Steps

1. **API Polling**: Polls TronGrid API every 10 seconds for new TRC20 transfers
2. **Address Filtering**: Filters transfers to watched merchant addresses
3. **Token Validation**: Verifies token contract is USDT or USDC
4. **Amount Parsing**: Decodes transfer value (6 decimals for USDT/USDC)
5. **Timestamp Tracking**: Tracks last processed timestamp to avoid duplicates
6. **Session Matching**: Finds payment session by amount and destination
7. **Update Database**: Marks as paid with transaction hash

#### Code Example

```python
async def _process_transfer(self, transfer: Dict):
    # Extract details
    token_address = transfer["token_info"]["address"]
    tx_hash = transfer["transaction_id"]
    to_address = transfer["to"]
    value = transfer["value"]
    
    # Convert amount (6 decimals for USDT)
    amount_raw = int(value)
    amount = Decimal(amount_raw) / Decimal(10 ** 6)
    
    # Create payment info
    payment = PaymentInfo(
        tx_hash=tx_hash,
        chain="tron",
        token_symbol="USDT",
        to_address=to_address,
        amount=str(amount),
        confirmations=19
    )
    
    await self._notify_payment(payment)
```

#### API Configuration

```bash
# TronGrid API (requires API key for production)
API_URL=https://api.trongrid.io
TRON_API_KEY=your-api-key-here

# Rate Limits (with API key)
# Free tier: 100 requests/second
# Pro tier: 1000 requests/second
```

#### Error Handling

- **API Errors**: Logs error and retries after delay
- **Rate Limiting**: Respects TronGrid rate limits with backoff
- **Invalid Transactions**: Skips and continues processing

---

## Payment Verification Flow

### Universal Flow (All Chains)

```
1. Customer initiates payment
   ↓
2. Blockchain listener detects transaction
   ↓
3. Extract payment details (amount, destination, token)
   ↓
4. Match to payment session (by memo or amount+destination)
   ↓
5. Validate payment amount matches expected amount
   ↓
6. Validate destination matches merchant wallet
   ↓
7. Wait for required confirmations
   ↓
8. Mark session as PAID in database
   ↓
9. Store transaction hash
   ↓
10. Send webhook notification to merchant
```

### Session Matching Strategies

#### Stellar (Memo-based)
- Payment includes memo field with session_id
- Direct session lookup: `WHERE id = memo`
- Most reliable method

#### EVM & Tron (Amount + Destination)
- No memo support in token transfers
- Match by: destination address + token + amount
- Query: `WHERE merchant_wallet = to_address AND amount = value AND status = 'created'`

### Validation Checks

All listeners perform these validations:

1. ✅ **Destination Address**: Payment sent to correct merchant wallet
2. ✅ **Token/Asset**: Correct token used (USDC, USDT, etc.)
3. ✅ **Amount**: Amount matches expected (±0.01 tolerance)
4. ✅ **Session Status**: Session is still in 'created' status (not expired/paid)
5. ✅ **Confirmations**: Sufficient block confirmations received

---

## Running Listeners

### Start All Listeners

```bash
# Terminal 1: Stellar
python -m app.services.stellar_listener

# Terminal 2: EVM (Ethereum, Polygon, Base)
python -m app.services.blockchains.evm_listener

# Terminal 3: Tron
python -m app.services.blockchains.tron_listener
```

### Background/Production

```bash
# Using systemd (Linux)
sudo systemctl start dari-stellar-listener
sudo systemctl start dari-evm-listener
sudo systemctl start dari-tron-listener

# Using PM2 (Node.js process manager)
pm2 start "python -m app.services.stellar_listener" --name stellar
pm2 start "python -m app.services.blockchains.evm_listener" --name evm
pm2 start "python -m app.services.blockchains.tron_listener" --name tron

# Using Docker Compose
docker-compose up -d stellar-listener evm-listener tron-listener
```

###監視 (Monitoring)

```bash
# Check logs
tail -f logs/stellar_listener.log
tail -f logs/evm_listener.log
tail -f logs/tron_listener.log

# PM2 monitoring
pm2 monit

# Health checks
curl http://localhost:8000/health
```

---

## Configuration

### Environment Variables

```bash
# Stellar Configuration
STELLAR_NETWORK=mainnet
STELLAR_HORIZON_URL=https://horizon.stellar.org
USDC_ASSET_CODE=USDC
USDC_ASSET_ISSUER=GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN

# Ethereum Configuration
ETHEREUM_RPC_URL=https://eth-mainnet.g.alchemy.com/v2/YOUR_KEY
ETHEREUM_CONFIRMATIONS=12
ETHEREUM_POLL_INTERVAL=15

# Polygon Configuration
POLYGON_RPC_URL=https://polygon-mainnet.g.alchemy.com/v2/YOUR_KEY
POLYGON_CONFIRMATIONS=128
POLYGON_POLL_INTERVAL=5

# Base Configuration
BASE_RPC_URL=https://mainnet.base.org
BASE_CONFIRMATIONS=10
BASE_POLL_INTERVAL=5

# Tron Configuration
TRON_API_URL=https://api.trongrid.io
TRON_API_KEY=your-trongrid-api-key
TRON_POLL_INTERVAL=10
```

### Merchant Wallet Setup

Merchants must configure their wallet addresses for each chain:

```python
# Database: merchant_wallets table
{
  "merchant_id": "uuid",
  "chain": "polygon",
  "wallet_address": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb",
  "is_active": true
}
```

API endpoint: `POST /api/wallets`

---

## Monitoring & Debugging

### Log Levels

```python
# Set in .env
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR

# Output example
2026-03-04 10:23:45 - stellar_listener - INFO - 💰 Processing payment: tx=abc12345... dest=GDZST3X... asset=USDC
2026-03-04 10:23:46 - stellar_listener - INFO - ✅ Valid payment: 10.00 USDC for session sess_abc123
```

### Common Issues

#### ❌ No Payments Detected

**Symptoms**: Listener runs but doesn't detect payments

**Troubleshooting**:
1. Check merchant wallet addresses configured
2. Verify RPC/API URLs are accessible
3. Check blockchain explorer for actual transaction
4. Verify token addresses match configuration

#### ❌ Payment Detected But Not Processed

**Symptoms**: Listener logs payment but doesn't mark as paid

**Troubleshooting**:
1. Check memo field (Stellar) - must match session_id
2. Verify amount matches exactly (check decimals)
3. Confirm session is still in 'created' status
4. Check destination address matches merchant wallet

#### ❌ Listener Crashes/Restarts

**Symptoms**: Listener stops or restart loops

**Troubleshooting**:
1. Check RPC connection (rate limits, API keys)
2. Review error logs for specific exception
3. Verify database connection
4. Check memory usage (large block ranges)

### Debug Commands

```bash
# Test Stellar connection
python -c "from stellar_sdk import Server; s = Server('https://horizon.stellar.org'); print(s.root())"

# Test EVM connection
python -c "from web3 import Web3; w3 = Web3(Web3.HTTPProvider('https://eth.llamarpc.com')); print(w3.eth.block_number)"

# Test Tron connection
curl https://api.trongrid.io/wallet/getnowblock

# Check database connection
python -c "from app.core.database import SessionLocal; db = SessionLocal(); print('DB Connected')"
```

---

## Security Considerations

### ✅ Best Practices

1. **No Private Keys**: Listeners only read blockchain data, never sign transactions
2. **Address Validation**: All addresses validated before watching
3. **Amount Tolerance**: Small tolerance (±0.01) prevents rounding issues
4. **Confirmation Waiting**: Prevents double-spend attacks
5. **Database Transactions**: Atomic updates prevent race conditions
6. **API Keys**: Store in environment variables, never hardcode
7. **Rate Limiting**: Respect blockchain API rate limits
8. **Error Logging**: Comprehensive logging for audit trail

### ⚠️ Important Notes

- **Finality**: Always wait for sufficient confirmations before marking as paid
- **Idempotency**: Listeners handle duplicate events gracefully
- **Reconnection**: Automatic reconnection with exponential backoff
- **Cursor/Timestamp**: Tracks progress to avoid reprocessing on restart

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     Dari for Business                        │
│                     Payment Gateway API                      │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ Creates Payment Session
                       │
        ┌──────────────┼──────────────┐
        │              │              │
        ▼              ▼              ▼
   ┌─────────┐   ┌─────────┐   ┌─────────┐
   │ Stellar │   │   EVM   │   │  Tron   │
   │Listener │   │ Listener│   │Listener │
   └────┬────┘   └────┬────┘   └────┬────┘
        │             │             │
        │ Monitor     │ Monitor     │ Monitor
        │ Horizon API │ RPC Nodes   │ TronGrid
        │             │             │
        ▼             ▼             ▼
   ┌─────────┐   ┌─────────┐   ┌─────────┐
   │ Stellar │   │Ethereum │   │  Tron   │
   │ Network │   │ Polygon │   │ Network │
   │         │   │  Base   │   │         │
   └─────────┘   └─────────┘   └─────────┘
        ▲             ▲             ▲
        │             │             │
        │ Customer    │ Customer    │ Customer
        │ Payment     │ Payment     │ Payment
        │             │             │
   ┌─────────┐   ┌─────────┐   ┌─────────┐
   │Customer │   │Customer │   │Customer │
   │ Wallet  │   │ Wallet  │   │ Wallet  │
   └─────────┘   └─────────┘   └─────────┘
```

---

## Performance Metrics

| Chain | Detection Time | Confirmation Time | Throughput |
|-------|---------------|-------------------|------------|
| Stellar | ~5 seconds | Instant | 1000+ TPS |
| Ethereum | ~15 seconds | ~3 minutes | 15-30 TPS |
| Polygon | ~5 seconds | ~4 minutes | 1000+ TPS |
| Base | ~5 seconds | ~20 seconds | 100+ TPS |
| Tron | ~10 seconds | ~57 seconds | 2000+ TPS |

---

## Conclusion

Dari for Business uses a robust, multi-chain blockchain listener architecture that:

- ✅ Monitors payments in real-time across 5+ blockchains
- ✅ Validates payments without smart contracts
- ✅ Ensures finality through confirmation requirements
- ✅ Scales horizontally by running independent listeners
- ✅ Provides comprehensive error handling and logging
- ✅ Maintains security by never handling private keys

All payment verification happens **on-chain** with **direct blockchain monitoring** - no intermediaries, no custody, no smart contract dependencies.
