# Payment Session Management - Timeout & Deep Link Implementation

**Date**: April 9, 2026  
**Status**: ✅ Complete  
**Changes**: Session timeout, deep linking

---

## Overview

Fixed critical payment session management issues:
1. **Session Expiration**: Changed from unlimited to **15-minute timeout from when payment STARTS** (not from session creation)
2. **Deep Link Support**: Added `dari:` protocol support for mobile app payment initiation
3. **Database Schema**: Added `payment_started_at` field to track when user begins payment

---

## Changes Made

### 1. Database Schema Update ✅
**File**: [add_payment_started_at.sql](migrations/add_payment_started_at.sql)

```sql
ALTER TABLE payment_sessions
ADD COLUMN payment_started_at TIMESTAMP NULL;

CREATE INDEX idx_payment_sessions_payment_started_at 
ON payment_sessions(payment_started_at);
```

**Purpose**: Track when user actually starts the payment process

---

### 2. Model Update ✅
**File**: [models.py](app/models/models.py)

```python
# Timestamps
created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
payment_started_at = Column(DateTime, nullable=True)  # NEW: When user starts payment
expires_at = Column(DateTime, nullable=True)  # Now calculated from payment_started_at + 15 min
paid_at = Column(DateTime, nullable=True)
```

**Change**: Added `payment_started_at` field to PaymentSession model

---

### 3. Checkout Page Logic ✅
**File**: [checkout.py](app/routes/checkout.py)

#### Before
```python
# Expiration calculated from created_at (unlimited until payment started)
expiry_time = session.created_at + timedelta(minutes=settings.PAYMENT_EXPIRY_MINUTES)
```

#### After
```python
# Set payment_started_at on first page load
if not session.payment_started_at:
    session.payment_started_at = datetime.utcnow()
    db.commit()

# Expiration calculated from payment_started_at
payment_timeout_minutes = settings.PAYMENT_EXPIRY_MINUTES  # 15 minutes
expiry_time = session.payment_started_at + timedelta(minutes=payment_timeout_minutes)
```

**Impact**: 
- Timeout now starts when user opens the payment page
- 15-minute window from first page load
- Consistent across all payment attempts

---

### 4. Payment Status Endpoint ✅
**File**: [payments.py](app/routes/payments.py)

Updated `GET /v1/payment_sessions/{session_id}` to check expiration using `payment_started_at`:

```python
if session.payment_started_at:
    expiry_time = session.payment_started_at + timedelta(minutes=payment_timeout_minutes)
else:
    expiry_time = session.created_at + timedelta(minutes=payment_timeout_minutes)
```

**Purpose**: Backward compatible with old sessions that don't have `payment_started_at`

---

### 5. Deep Link Protocol Support ✅
**File**: [checkout.py](app/routes/checkout.py)

#### New Deep Link Format
```
dari://pay/{SESSION_ID}?chain=CHAIN&amount=AMOUNT&merchant=MERCHANT_NAME&token=TOKEN
```

#### Example
```
dari://pay/pay-abc123?chain=polygon&amount=99.99&merchant=Coffee%20Shop&token=USDC
```

**Features**:
- Mobile app can intercept `dari://` protocol
- Includes chain, amount, merchant, and token info
- URL-safe encoding for merchant names
- Session ID includes safe characters

#### Implementation
```python
# Generate Dari App Deep Link
dari_deep_link = f"dari://pay/{session_id_safe}?chain={current_chain}&amount={amount_token_val}&merchant={merchant_name_safe}&token={current_token}"

# Create QR code from deep link
dari_qr_data = dari_deep_link
```

**QR Code**: Scanning the Dari QR code triggers the deep link

---

### 6. Configuration Update ✅
**File**: [config.py](app/core/config.py)

```python
# Before
PAYMENT_EXPIRY_MINUTES: int = 30

# After
PAYMENT_EXPIRY_MINUTES: int = 15  # Payment timeout from when user starts (opens checkout page)
```

**Reason**: Align with new startup-based timeout

---

## Technical Flow

### Timeline: Payment Session Lifecycle

```
Session Created (pay_xxx)
└─ created_at = 2026-04-09 10:00:00 UTC
└─ payment_started_at = NULL

User Opens Payment Link
└─ [Checkout Page Loads]
└─ payment_started_at = 2026-04-09 10:02:00 UTC (first page load)
└─ expires_at = 10:17:00 UTC (15 minutes later)

User Has 15 Minutes To Completed Payment
├─ 10:02 → 10:17 (15 min window to scan QR or connect wallet)
├─ Can reload page (doesn't reset timer)
└─ At 10:18, session becomes EXPIRED

After Expiration
└─ Status set to EXPIRED
└─ Page shows "Session Expired" message
└─ User must create new payment session
```

---

## API Changes

### Checkout Page Endpoint
```
GET /checkout/{session_id}

Response includes:
- expires_at: Absolute expiration time (now based on payment_started_at)
- dari_deep_link: "dari://pay/session?..." deep link
- dari_qr_b64: QR code image (encodes deep link)
```

### Payment Status Endpoint
```
GET /v1/payment_sessions/{session_id}

Smart expiration check:
- Uses payment_started_at if available
- Falls back to created_at for old sessions  
- Marks expired sessions automatically
```

---

## Deep Link Flow

### Mobile App Integration Example

```javascript
// Register deep link handler in Dari Mobile App
const deepLinkHandler = (url) => {
  // dari://pay/{session_id}?chain=polygon&amount=99.99&merchant=Store&token=USDC
  const params = new URLSearchParams(url.split('?')[1]);
  
  const sessionId = url.split('/pay/')[1].split('?')[0];
  const chain = params.get('chain');
  const amount = params.get('amount');
  const token = params.get('token');
  const merchant = params.get('merchant');
  
  // Navigate to payment screen with pre-filled data
  navigateToPayment({
    sessionId,
    chain,
    amount,
    token,
    merchant
  });
}
```

### Checkout Page QR Code

User scans **Dari QR Code** with their mobile device:
1. Mobile device detects `dari://` protocol
2. Dari app receives deep link with session & payment info
3. App pre-fills wallet, chain, and amount
4. User confirms and sends transaction

---

## Testing Checklist

- [ ] Database migration applies successfully
- [ ] `payment_started_at` field created in `payment_sessions` table
- [ ] Checkout page sets `payment_started_at` on first load
- [ ] Expiration calculated from `payment_started_at + 15 min`
- [ ] Reloading page doesn't reset expiration timer
- [ ] Session expires exactly 15 minutes after first page load
- [ ] Expired sessions show "Session Expired" message
- [ ] Deep link format: `dari://pay/{session}?chain=X&amount=Y&merchant=Z&token=T`
- [ ] Deep link QR code generates correctly
- [ ] Old sessions (without `payment_started_at`) still work
- [ ] Payment status endpoint checks both `payment_started_at` and `created_at`
- [ ] Integration with mobile app (if applicable)

---

## Backward Compatibility

✅ **Fully backward compatible**

- Old payment sessions without `payment_started_at` still work
- Expiration falls back to `created_at` for legacy sessions
- No required data migration (field is nullable)
- Existing payment URLs continue to work

---

## Configuration

### Timeout Duration
Default: **15 minutes**

To adjust, update `.env`:
```
PAYMENT_EXPIRY_MINUTES=15
```

### Deep Link Protocol
- **Format**: `dari://`
- **Registered with**: Mobile app manifest
- **Fallback**: Web browser shows payment page

---

## Files Changed

| File | Change | Impact |
|------|--------|--------|
| [models.py](app/models/models.py) | Added `payment_started_at` field | ⭐ Core change |
| [checkout.py](app/routes/checkout.py) | Set start time & calculate expiration | ⭐ Core change |
| [payments.py](app/routes/payments.py) | Updated status endpoint expiration logic | ⭐ Core change |
| [config.py](app/core/config.py) | Changed timeout to 15 minutes | ⚙️ Configuration |
| [add_payment_started_at.sql](migrations/) | Database schema update | 📊 Schema |

---

## Migration Steps

1. **Apply Database Migration**
   ```bash
   psql -U user -d database -f migrations/add_payment_started_at.sql
   ```

2. **Deploy Updated Code**
   - Push new code with all changes
   - No service restart required for Python changes

3. **Verify**
   ```bash
   # Check migration applied
   psql -U user -d database -c "\d payment_sessions"
   # Should show: payment_started_at | timestamp without time zone | NULL
   ```

4. **Monitor**
   - Check payment session expiration times
   - Monitor deep link usage (if mobile app available)
   - Verify timeout behavior in logs

---

## Future Enhancements

- [ ] Configurable timeout per merchant
- [ ] Extend timeout option (user clicks "Give me more time")
- [ ] Countdown timer on payment page
- [ ] SMS/Email notification when session about to expire
- [ ] Deep link analytics (track mobile app opens)
- [ ] One-click payment from deep link (pre-signed transaction)
- [ ] Payment timeout webhook notification

---

## Summary

✅ **Payment sessions now expire 15 minutes from when the user opens the payment page**  
✅ **Deep link support enables mobile app integration with `dari://` protocol**  
✅ **Fully backward compatible with existing sessions**  
✅ **Database migration included for schema update**

**Impact**: Users have a clear, consistent 15-minute window to complete payment, and mobile app can integrate seamlessly.

---

**Created**: April 9, 2026  
**Version**: 1.0  
**Author**: Development Team
