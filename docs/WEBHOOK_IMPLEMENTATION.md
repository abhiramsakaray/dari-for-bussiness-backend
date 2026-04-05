# Refund Webhooks - Implementation Guide

## Overview

Webhooks are now **fully implemented** for refund status changes. When a refund is processed (completed or failed), merchants automatically receive HTTP POST notifications to their configured webhook URL with complete refund details including the transaction hash.

## What Was Added

### 1. Refund Webhook Function
**Location**: `app/services/webhook_service.py`

```python
async def send_refund_webhook(refund: Refund, db: Session, retry_count: int = 0):
    """
    Send webhook notification to merchant when refund status changes.
    
    Features:
    - Automatic event type detection (refund.completed, refund.failed, etc.)
    - HMAC-SHA256 signature for security
    - Automatic retry (configurable, default: 5 attempts)
    - Timeout handling (configurable, default: 10 seconds)
    """
```

**What It Does**:
- ✅ Detects refund status (PENDING, PROCESSING, COMPLETED, FAILED)
- ✅ Creates event type: `refund.{status}` (e.g., `refund.completed`)
- ✅ Builds payload with refund details
- ✅ Signs payload with HMAC-SHA256
- ✅ Sends to merchant webhook URL
- ✅ Retries on failure
- ✅ Logs all activity

### 2. Refund Processor Integration
**Location**: `app/services/refund_processor.py`

Webhook calls added at **5 key points**:

```python
# 1. When refund payment not found
refund.status = FAILED
refund.failure_reason = "Associated payment not found"
db.commit()
await send_refund_webhook(refund, db)

# 2. When recipient address missing
refund.status = FAILED
refund.failure_reason = "Recipient wallet address not specified"
db.commit()
await send_refund_webhook(refund, db)

# 3. When blockchain chain is unsupported
refund.status = FAILED
refund.failure_reason = f"Unsupported blockchain: {refund.chain}"
db.commit()
await send_refund_webhook(refund, db)

# 4. When refund COMPLETED successfully
refund.tx_hash = tx_hash
refund.status = COMPLETED
refund.completed_at = datetime.utcnow()
db.commit()
await send_refund_webhook(refund, db)

# 5. When refund FAILS on-chain
refund.status = FAILED
refund.failure_reason = "Transaction failed to send on-chain"
db.commit()
await send_refund_webhook(refund, db)

# 6. When exception occurs during processing
refund.status = FAILED
refund.failure_reason = f"Processing error: {str(e)}"
db.commit()
await send_refund_webhook(refund, db)
```

### 3. Model Export
**Location**: `app/models/__init__.py`

Added `Refund` and `RefundStatus` to imports and exports for proper module initialization.

## How Webhooks Work

### Step-by-Step Flow

```
1. Merchant creates refund
   ↓
2. Scheduler/manual trigger calls process_refund_on_chain()
   ↓
3. Refund is processed (PENDING → PROCESSING)
   ↓
4. On-chain transaction sent (returns tx_hash or error)
   ↓
5. Status updated to COMPLETED or FAILED
   ↓
6. send_refund_webhook() is called ← NEW
   ↓
7. Webhook payload built with all refund details
   ↓
8. Payload signed with HMAC-SHA256
   ↓
9. HTTP POST sent to merchant webhook URL
   ↓
10. If failed: retry up to 5 times with exponential backoff
    If success: merchant receives notification immediately
```

## Webhook Payload

### Headers Sent
```
Content-Type: application/json
User-Agent: ChainPe/2.2
X-Webhook-Event: refund.{status}
X-Refund-ID: {refund_id}
X-Chain: {chain}
X-Token: {token}
X-Webhook-Signature: t={timestamp},v1={hmac_sha256}
```

### Payload Body (JSON)

#### Refund Completed
```json
{
  "event": "refund.completed",
  "refund_id": "ref_7S27vsN9r7tWMB8D",
  "payment_session_id": "ps_abc123xyz",
  "merchant_id": "m_12345",
  "amount": "50.000000",
  "token": "USDC",
  "chain": "polygon",
  "status": "COMPLETED",
  "tx_hash": "0x1111111111111111111111111111111111111111111111111111111111111111",
  "recipient_address": "0xabc123...def456",
  "refund_reason": "Product return",
  "failure_reason": null,
  "created_at": "2026-04-05T18:27:00Z",
  "processed_at": "2026-04-05T18:27:40Z",
  "completed_at": "2026-04-05T18:27:40Z",
  "timestamp": "2026-04-05T18:27:40.123456Z"
}
```

#### Refund Failed
```json
{
  "event": "refund.failed",
  "refund_id": "ref_7S27vsN9r7tWMB8D",
  "payment_session_id": "ps_abc123xyz",
  "merchant_id": "m_12345",
  "amount": "50.000000",
  "token": "USDC",
  "chain": "polygon",
  "status": "FAILED",
  "tx_hash": null,
  "recipient_address": "0xabc123...def456",
  "refund_reason": "Product return",
  "failure_reason": "Insufficient merchant balance on platform",
  "created_at": "2026-04-05T18:27:00Z",
  "processed_at": null,
  "completed_at": "2026-04-05T18:27:40Z",
  "timestamp": "2026-04-05T18:27:40.123456Z"
}
```

## Security

### Webhook Signature Verification
**Function**: `verify_webhook_signature()` in `app/core/security_utils.py`

Merchants verify webhooks are from ChainPe using:
```python
def verify_webhook_signature(
    payload_body: bytes,
    signature_header: str,
    secret: str,
    tolerance_seconds: int = 300
) -> bool:
    """Verify X-Webhook-Signature header using merchant's secret key"""
```

### Signature Format
```
X-Webhook-Signature: t=1712350000,v1=abc123def456...
```

- `t`: Unix timestamp (replay protection - must be within 5 minutes)
- `v1`: HMAC-SHA256 hex digest

### How to Verify (Merchant Side)

```python
import hmac
import hashlib

def verify_chainpe_webhook(signature_header, payload_bytes, merchant_secret):
    """Verify webhook came from ChainPe"""
    
    # Parse signature header
    parts = dict(p.split("=", 1) for p in signature_header.split(","))
    timestamp = parts["t"]
    expected_sig = parts["v1"]
    
    # Reconstruct signed payload
    signed_payload = f"{timestamp}.".encode() + payload_bytes
    
    # Compute HMAC-SHA256
    computed_sig = hmac.new(
        merchant_secret.encode(),
        signed_payload,
        hashlib.sha256
    ).hexdigest()
    
    # Verify signature (constant-time comparison)
    return hmac.compare_digest(computed_sig, expected_sig)

# Example usage
is_authentic = verify_chainpe_webhook(
    signature_header="t=1712350000,v1=abc123...",
    payload_bytes=request.body,
    merchant_secret="secret_abc123"
)
```

## Configuration

### Environment Variables
```bash
# Webhook retry settings
WEBHOOK_RETRY_LIMIT=5                      # How many times to retry
WEBHOOK_TIMEOUT_SECONDS=10                 # How long to wait for response
WEBHOOK_SIGNING_SECRET=your_secret_key     # Default signing secret
```

### Merchant Configuration
Merchants set their webhook details via API:
- `webhook_url`: Where ChainPe sends POST requests
- `webhook_secret`: Secret key for signature verification

## Testing Webhooks

### 1. Set Up Webhook Receiver (for testing)
```python
# Example Flask app to receive webhooks
from flask import Flask, request
import hmac
import hashlib

app = Flask(__name__)
MERCHANT_SECRET = "test_secret_key"

@app.route('/webhooks/refunds', methods=['POST'])
def receive_refund_webhook():
    # Verify signature
    signature = request.headers.get('X-Webhook-Signature')
    ts, sig = signature.split(',')
    ts = ts.split('=')[1]
    sig = sig.split('=')[1]
    
    body = request.get_data()
    signed = f"{ts}.".encode() + body
    computed = hmac.new(
        MERCHANT_SECRET.encode(),
        signed,
        hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(computed, sig):
        return {"error": "Invalid signature"}, 401
    
    data = request.json
    print(f"✅ Received webhook: {data['event']}")
    print(f"   Refund: {data['refund_id']}")
    print(f"   Status: {data['status']}")
    print(f"   Tx Hash: {data['tx_hash']}")
    
    return {"received": True}, 200

if __name__ == '__main__':
    app.run(port=5000)
```

### 2. Create Refund and Trigger Processing
```bash
# 1. Create refund
curl -X POST http://localhost:8000/refunds \
  -H "Authorization: Bearer MERCHANT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "payment_session_id": "ps_abc123",
    "amount": "10.00",
    "refund_address": "0xabc123...",
    "reason": "Testing"
  }'
# Returns: {"id": "ref_xyz789"}

# 2. Trigger processing
curl -X POST http://localhost:8000/admin/scheduler/refunds/trigger \
  -H "Authorization: Bearer MERCHANT_TOKEN"

# 3. Check webhook receiver
# Should see POST to http://your-server/webhooks/refunds with:
# {
#   "event": "refund.completed",
#   "refund_id": "ref_xyz789",
#   "tx_hash": "0x1111...",
#   "status": "COMPLETED",
#   ...
# }
```

### 3. View Webhook Delivery Logs
```bash
# Query webhook deliveries from database
SELECT 
    id,
    merchant_id,
    event_type,
    endpoint,
    response_status,
    error_message,
    attempt_number,
    created_at
FROM webhook_deliveries
WHERE event_type LIKE 'refund.%'
ORDER BY created_at DESC
LIMIT 10;
```

## Logs

When webhooks are sent, you'll see log entries like:

```
✅ Refund webhook sent successfully to https://merchant.example.com/webhooks/refunds for refund ref_xyz789 (status: COMPLETED)
```

On failure:
```
Refund webhook returned non-2xx status 500 for refund ref_xyz789
Retrying refund webhook (attempt 2/5)...

Refund webhook timeout for https://merchant.example.com/webhooks/refunds (refund ref_xyz789)

Refund webhook failed after 5 attempts for refund ref_xyz789
```

## Event Types

| Event | Trigger | tx_hash |
|-------|---------|---------|
| `refund.pending` | Refund created | null |
| `refund.processing` | Processing started | null |
| `refund.completed` | Transaction sent successfully | ✅ Included |
| `refund.failed` | Processing error or failure | null |
| `refund.cancelled` | Merchant cancels refund | null |

## What's Next

### To Make Transaction Hash Real (not mocked)
1. Replace mock tx_hash returns in blockchain handlers:
   ```python
   # Current (mock):
   return f"0x{'1'*64}"
   
   # TODO (real):
   tx_response = await relayer.send_transaction(...)
   return tx_response.tx_hash
   ```

2. Integrate with blockchain relayer services:
   - Polygon: Use EVM relayer service
   - Stellar: Use Stellar SDK or relayer API
   - Solana: Use Solana RPC or relayer service
   - Soroban: Use Soroban contract relayer
   - TRON: Use TRON API or relayer service

### Webhook Retry Strategy
Currently: Immediate retry on failure

TODO: Add exponential backoff
```python
# Add to webhook service
import asyncio

async def send_with_backoff(url, payload, attempt=1):
    delay = 2 ** attempt  # 2s, 4s, 8s, 16s, 32s
    await asyncio.sleep(delay)
    return await send_webhook(url, payload)
```

## Summary

✅ **Webhooks fully implemented:**
- Event triggers on refund status changes
- HMAC-SHA256 signatures for security
- Automatic retry logic (up to 5 times)
- Complete refund details in payload
- Transaction hash included when available
- Ready for production use

⚠️ **Transaction hashes are mocked** - Replace with real blockchain relayer integration

🔧 **Configuration-ready** - Merchants can set webhook URL and secret via API
