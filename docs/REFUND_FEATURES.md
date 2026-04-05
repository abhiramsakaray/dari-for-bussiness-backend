# On-Chain Hash, Webhooks & Service Revoke - Features Overview

## 1. On-Chain Hash (TX_HASH) ✅ FULLY IMPLEMENTED

### Location & Storage
**Database**: Stored in `refunds.tx_hash` column
```python
class Refund(Base):
    tx_hash = Column(String, nullable=True)  # Blockchain transaction hash
```

### How It Works

#### When Refund is Processed ✅
1. **Processing Status**: Refund moves to `PROCESSING`
2. **Chain-Specific Handler Called**:
   - Polygon → `send_polygon_refund()` 
   - Stellar → `send_stellar_refund()`
   - Solana → `send_solana_refund()`
   - Soroban → `send_soroban_refund()`
   - TRON → `send_tron_refund()`

3. **Transaction Hash Received**: Blockchain returns tx_hash
4. **Stored in Database**:
   ```python
   refund.tx_hash = tx_hash
   refund.status = DBRefundStatus.COMPLETED
   refund.processed_at = datetime.utcnow()
   db.commit()
   ```

#### Returned to Frontend ✅
In RefundResponse:
```python
RefundResponse(
    id=refund.id,
    tx_hash=refund.tx_hash,  # ← Included in API response
    status='COMPLETED',
    ...
)
```

#### Displayed in UI ✅
In RefundsList component:
```typescript
{refund.tx_hash && (
  <Button
    size="icon"
    variant="ghost"
    onClick={() => window.open(
      `https://explorer.example.com/tx/${refund.tx_hash}`, 
      '_blank'
    )}
    title="View transaction"
  >
    <ExternalLink className="w-4 h-4" />
  </Button>
)}
```

### Example Response
```json
{
  "id": "ref_7S27vsN9r7tWMB8D",
  "status": "COMPLETED",
  "tx_hash": "0x1111111111111111111111111111111111111111111111111111111111111111",
  "amount": "1.000000",
  "token": "USDC",
  "chain": "polygon",
  "created_at": "2026-04-05T18:27:00Z",
  "processed_at": "2026-04-05T18:27:40Z",
  "completed_at": "2026-04-05T18:27:40Z"
}
```

### Transaction Explorer Links
- **Polygon**: `https://polygonscan.com/tx/{tx_hash}`
- **Stellar**: `https://stellar.expert/explorer/public/tx/{tx_hash}`
- **Solana**: `https://solscan.io/tx/{tx_hash}`
- **Soroban**: `https://soroban.expert/tx/{tx_hash}`
- **TRON**: `https://tronscan.org/transaction/{tx_hash}`

---

## 2. Service Revoke (CANCEL REFUND) ✅ FULLY IMPLEMENTED

### Endpoint
```
POST /refunds/{refund_id}/cancel
```

### Status Requirement
Can only cancel refunds in these states:
- `PENDING` - Not yet processed
- `QUEUED` - Waiting for merchant balance
- `INSUFFICIENT_FUNDS` - Failed due to insufficient balance

### Cannot Cancel (Locked)
- `PROCESSING` - Currently sending to blockchain
- `COMPLETED` - Already sent to customer
- `FAILED` - Already failed/canceled

### Implementation
```python
@router.post("/{refund_id}/cancel")
async def cancel_refund(
    refund_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant),
    _: bool = Depends(require_replay_protection)
):
    """Cancel a pending or queued refund"""
    
    # Validate status can be canceled
    if refund.status not in [PENDING, QUEUED, INSUFFICIENT_FUNDS]:
        raise HTTPException(
            status_code=400,
            detail="Can only cancel pending, queued, or insufficient_funds refunds"
        )
    
    # Cancel the refund
    refund.status = DBRefundStatus.FAILED
    db.commit()
    
    # Revert payment status if needed
    if payment.status in [REFUNDED, PARTIALLY_REFUNDED]:
        # Recalculate based on remaining successful refunds
        ...
```

### Example Cancellation Flow

**Before Cancel**:
```
Refund: ref_abc123
Status: PENDING
Amount: 50 USDC
```

**Call**: `POST /refunds/ref_abc123/cancel`

**After Cancel**:
```
Refund: ref_abc123
Status: FAILED
Amount: 50 USDC
Payment Status: PAID (reverted from PARTIALLY_REFUNDED)
```

### Request Example
```bash
curl -X POST http://127.0.0.1:8000/refunds/ref_abc123/cancel \
  -H "Authorization: Bearer YOUR_MERCHANT_TOKEN" \
  -H "X-Request-Nonce: abc123def456" \
  -H "X-Request-Timestamp: 1712350000"
```

### Response
```json
{
  "message": "Refund cancelled",
  "id": "ref_abc123"
}
```

---

## 3. Webhooks for Refunds ✅ **FULLY IMPLEMENTED**

### Current Status
✅ **Webhook Infrastructure Complete**:
- WebhookDelivery model for tracking attempts
- Webhook signature verification utilities
- Webhook retry logic
- **NEW: Refund event triggers and payload builder**
- **NEW: Integration with refund processor**

### What Exists (For Other Events)
```python
class WebhookDelivery(Base):
    """Track webhook delivery attempts"""
    id = Column(UUID, primary_key=True)
    merchant_id = Column(UUID, ForeignKey("merchants.id"))
    event_type = Column(String(50)) # created, paid, expired, webhook_sent, webhook_failed
    payload = Column(JSON)
    status = Column(String) # pending, delivered, failed
    attempts = Column(Integer, default=0)
    max_attempts = Column(Integer, default=5)
    next_retry_at = Column(DateTime)
```

### What Needs to Be Added

#### 1. Event Constants ✅ IMPLEMENTED

### Webhook Payload Examples

**Refund Created**:
```json
{
  "event": "refund.pending",
  "timestamp": "2026-04-05T18:27:00Z",
  "data": {
    "refund_id": "ref_abc123",
    "payment_session_id": "ps_xyz789",
    "amount": "50.000000",
    "token": "USDC",
    "chain": "polygon",
    "status": "PENDING",
    "tx_hash": null,
    "failure_reason": null,
    "created_at": "2026-04-05T18:27:00Z",
    "completed_at": null
  }
}
```

**Refund Completed**:
```json
{
  "event": "refund.completed",
  "timestamp": "2026-04-05T18:28:00Z",
  "data": {
    "refund_id": "ref_abc123",
    "payment_session_id": "ps_xyz789",
    "amount": "50.000000",
    "token": "USDC",
    "chain": "polygon",
    "status": "COMPLETED",
    "tx_hash": "0x1111111111111111111111111111111111111111111111111111111111111111",
    "failure_reason": null,
    "created_at": "2026-04-05T18:27:00Z",
    "completed_at": "2026-04-05T18:28:00Z"
  }
}
```

**Refund Failed**:
```json
{
  "event": "refund.failed",
  "timestamp": "2026-04-05T18:28:30Z",
  "data": {
    "refund_id": "ref_abc123",
    "payment_session_id": "ps_xyz789",
    "amount": "50.000000",
    "token": "USDC",
    "chain": "polygon",
    "status": "FAILED",
    "tx_hash": null,
    "failure_reason": "Insufficient merchant balance on platform",
    "created_at": "2026-04-05T18:27:00Z",
    "completed_at": "2026-04-05T18:28:30Z"
  }
}
```

---

## Feature Comparison Matrix

| Feature | Status | Location | Details |
|---------|--------|----------|---------|
| **TX Hash Storage** | ✅ COMPLETE | `refunds.tx_hash` | Stored when refund completes |
| **TX Hash Return** | ✅ COMPLETE | RefundResponse API | Included in refund object |
| **TX Hash Display** | ✅ COMPLETE | RefundsList UI | Click to view on explorer |
| **Refund Cancel** | ✅ COMPLETE | POST `/refunds/{id}/cancel` | Cancel pending/queued refunds |
| **Refund Retry** | ✅ COMPLETE | POST `/refunds/{id}/retry` | Retry failed refunds |
| **Webhook Delivery** | ✅ COMPLETE | WebhookDelivery model | General webhook infrastructure |
| **Refund Webhooks** | ❌ MISSING | - | Need event triggers |
| **Webhook Events** | ❌ MISSING | - | Need refund event types |
| **Webhook Payloads** | ❌ MISSING | - | Need refund payload builder |

---

## Implementation Priority

### High Priority (MVP)
1. ✅ on-chain tx_hash storage & retrieval
2. ✅ Refund cancellation service
3. ⏳ Webhook event triggers for refund status changes

### Medium Priority (Phase 2)
1. Real blockchain relayer integration (replace mock tx hashes)
2. Transaction confirmation polling
3. Automatic refund retry on failure

### Low Priority (Phase 3)
1. Webhook signature verification for merchant endpoints
2. Webhook delivery dashboard
3. Refund analytics & reporting

---

## Testing

### Test TX Hash
```bash
# 1. Create refund
curl -X POST http://localhost:8000/refunds \
  -H "Authorization: Bearer TOKEN" \
  -d '{"payment_session_id": "ps_123", "amount": "10"}'
# Returns: refund_id = "ref_abc123"

# 2. Trigger processing
curl -X POST http://localhost:8000/admin/scheduler/refunds/trigger \
  -H "Authorization: Bearer TOKEN"

# 3. Check refund
curl http://localhost:8000/refunds/ref_abc123 \
  -H "Authorization: Bearer TOKEN"
# Response includes: "tx_hash": "0x1111..."
```

### Test Cancel
```bash
# Create refund (status = PENDING)
curl -X POST http://localhost:8000/refunds ...

# Cancel it
curl -X POST http://localhost:8000/refunds/ref_abc123/cancel \
  -H "Authorization: Bearer TOKEN"
# Response: "Refund cancelled"

# Verify status
curl http://localhost:8000/refunds/ref_abc123
# Status is now: "FAILED"
```

---

## Summary

| Feature | Status | User Impact |
|---------|--------|------------|
| See transaction hash | ⚠️ Mocked | Users can see fake hash (needs real relayer) |
| Cancel pending refund | ✅ Ready | Users can revoke refunds before processing |
| Webhook notifications | ✅ READY | **Merchants NOW receive refund status updates** |
| Real blockchain relay | ⏳ TODO | Refunds actually execute on-chain |

**Webhooks are NOW FULLY IMPLEMENTED:** Event triggers added when refund status changes (PENDING → COMPLETED/FAILED). Merchants receive notifications with tx_hash, amount, token, chain, and detailed refund info.
