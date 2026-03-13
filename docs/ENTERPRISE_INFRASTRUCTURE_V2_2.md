# Dari for Business v2.2.0 — Enterprise Infrastructure Guide

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Payment State Machine](#payment-state-machine)
3. [Idempotency System](#idempotency-system)
4. [Token Vault (Redis)](#token-vault-redis)
5. [Webhook HMAC Signing](#webhook-hmac-signing)
6. [Security Infrastructure](#security-infrastructure)
7. [Fraud Detection Engine](#fraud-detection-engine)
8. [Multi-Provider FX Rates](#multi-provider-fx-rates)
9. [AML & Compliance](#aml--compliance)
10. [Currency Precision](#currency-precision)
11. [Immutable Ledger](#immutable-ledger)
12. [Monitoring & Observability](#monitoring--observability)
13. [Database Schema](#database-schema)
14. [Migration Guide](#migration-guide)
15. [Configuration Reference](#configuration-reference)
16. [Compliance & Regulations](#compliance--regulations)
17. [Frontend Integration Guide](#frontend-integration-guide)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Dari for Business v2.2.0                        │
│                  Enterprise Payment Infrastructure                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │
│  │ FastAPI   │  │ Security │  │ Metrics  │  │ Request Logging  │   │
│  │ CORS      │→ │ Headers  │→ │ Prom.    │→ │ Middleware       │   │
│  │ Middleware│  │ + Rate   │  │ Middleware│  │                  │   │
│  └──────────┘  │ + Replay │  └──────────┘  └──────────────────┘   │
│                └──────────┘                                         │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                      Route Layer                             │   │
│  │  sessions · payments · checkout · webhooks · admin           │   │
│  │  payment_links · invoices · subscriptions · refunds          │   │
│  └──────────────┬──────────────────────────────┬───────────────┘   │
│                 │                              │                    │
│  ┌──────────────▼──────────────┐  ┌───────────▼────────────────┐  │
│  │      Service Layer          │  │     Infrastructure          │  │
│  │                             │  │                             │  │
│  │  State Machine              │  │  Redis Token Vault          │  │
│  │  Compliance Service         │  │  DB-backed Idempotency      │  │
│  │  Ledger Service             │  │  Price Service (3 FX APIs)  │  │
│  │  Currency Precision         │  │  Webhook HMAC Signing       │  │
│  │  Fraud Detection            │  │  Prometheus Metrics         │  │
│  └──────────────┬──────────────┘  └───────────┬────────────────┘  │
│                 │                              │                    │
│  ┌──────────────▼──────────────────────────────▼───────────────┐   │
│  │              Data Layer                                      │   │
│  │  PostgreSQL · SQLAlchemy ORM · Alembic Migrations            │   │
│  │                                                              │   │
│  │  Tables: merchants, payment_sessions, payment_events,        │   │
│  │  ledger_entries, payment_state_transitions,                  │   │
│  │  compliance_screenings, idempotency_keys, ...                │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │              Blockchain Layer                                 │   │
│  │  Stellar · Ethereum · Polygon · Base · Tron · (Solana)       │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### Component Boundaries (Microservice-Ready)

The monolith is structured with clear boundaries for future extraction:

| Component | Module Path | Future Service |
|-----------|------------|----------------|
| Session Management | `app/routes/sessions.py` | Payment Session Service |
| State Machine | `app/services/state_machine.py` | Payment Core Service |
| FX / Pricing | `app/services/price_service.py` | Pricing Service |
| Compliance | `app/services/compliance_service.py` | Compliance Service |
| Ledger | `app/services/ledger_service.py` | Accounting Service |
| Token Vault | `app/services/payment_tokenization.py` | Vault Service |
| Webhooks | `app/services/webhook_service.py` | Notification Service |
| Monitoring | `app/core/monitoring.py` | Observability Sidecar |

---

## Payment State Machine

### State Diagram

```
                    ┌──────────┐
              ┌─────│  CREATED │─────┐
              │     └────┬─────┘     │
              │          │           │
         EXPIRED    PENDING      FAILED
              │          │           │
              ▼     ┌────▼─────┐     ▼
         ┌────────┐ │  PENDING │ ┌────────┐
         │EXPIRED │ └────┬─────┘ │FAILED  │──→ CREATED (retry)
         └────────┘      │       └────────┘
          ▲              │
          │    ┌─────────┼─────────┐
          │    │         │         │
          │ PROCESSING  CONFIRMED FAILED
          │    │         │
          │ ┌──▼──────┐  │
          │ │PROCESSING│  │
          │ └──┬──────┘  │
          │    │         │
          │ CONFIRMED    │
          │    │    ┌────▼─────┐
          └────┼────│CONFIRMED │ (= PAID)
               │    └────┬─────┘
               │         │
               │    ┌────▼───────────┐
               │    │ REFUNDED /     │
               │    │ PARTIALLY_     │
               │    │ REFUNDED       │
               │    └────────────────┘
```

### Valid Transitions

| From State | Allowed To States |
|------------|-------------------|
| `CREATED` | `PENDING`, `EXPIRED`, `FAILED` |
| `PENDING` | `PROCESSING`, `CONFIRMED`, `PAID`, `EXPIRED`, `FAILED` |
| `PROCESSING` | `CONFIRMED`, `PAID`, `FAILED` |
| `CONFIRMED` | `REFUNDED`, `PARTIALLY_REFUNDED` |
| `PAID` | `REFUNDED`, `PARTIALLY_REFUNDED` |
| `FAILED` | `CREATED` (retry) |
| `EXPIRED` | `CREATED` (retry) |
| `REFUNDED` | *(terminal)* |
| `PARTIALLY_REFUNDED` | `REFUNDED` |

### Usage

```python
from app.services.state_machine import transition_payment, InvalidTransitionError
from app.models.models import PaymentStatus

try:
    transition_payment(
        session=payment_session,
        to_state=PaymentStatus.CONFIRMED,
        db=db,
        trigger="blockchain_confirmation",
        actor="listener_polygon",
    )
    db.commit()
except InvalidTransitionError as e:
    # Invalid transition — log and handle
    logger.error(f"Cannot transition: {e}")
```

Every transition creates:
- A `PaymentStateTransition` audit record
- A `PaymentEvent` record

---

## Idempotency System

The system uses **database-backed idempotency keys** to prevent duplicate operations.

### How It Works

1. Client sends `Idempotency-Key: <unique-key>` header
2. Middleware checks DB for existing key
3. If new: creates record, processes request, stores response
4. If duplicate + completed: returns cached response
5. If duplicate + processing: returns `409 Conflict`
6. Keys expire after 24 hours

### Supported Endpoints

- `POST /api/v1/payments`
- `POST /api/v1/payment-links`
- `POST /api/v1/invoices`
- `POST /api/v1/subscriptions`
- `POST /api/v1/refunds`

### Client Example

```bash
curl -X POST /api/sessions/create \
  -H "Idempotency-Key: order-12345-attempt-1" \
  -H "Authorization: Bearer <token>" \
  -d '{"amount": 100, "currency": "USD"}'
```

---

## Token Vault (Redis)

Payment tokens (`ptok_xxxx`) are short-lived opaque references that protect sensitive payment data.

### Architecture

```
Client                  Backend                   Redis / Memory
  │                       │                           │
  │ POST /tokenize        │                           │
  │──────────────────────→│                           │
  │                       │  SET ptok:xxx payload     │
  │                       │──────────────────────────→│
  │   ← ptok_xxxx         │                           │
  │←──────────────────────│                           │
  │                       │                           │
  │ POST /pay (ptok_xxxx) │                           │
  │──────────────────────→│                           │
  │                       │  GET ptok:xxx             │
  │                       │──────────────────────────→│
  │                       │  ← payload               │
  │                       │←──────────────────────────│
  │   ← payment result    │                           │
  │←──────────────────────│                           │
```

### Configuration

```env
REDIS_ENABLED=true
REDIS_URL=redis://localhost:6379/0
REDIS_TOKEN_DB=1
```

When `REDIS_ENABLED=false` or Redis is unreachable, the system automatically falls back to an in-memory vault.

---

## Webhook HMAC Signing

All webhook payloads are signed with HMAC-SHA256.

### Signature Header Format

```
X-Payment-Signature: t=1719849600,v1=5257a869e7ecebeda32affa62cdca3fa51cad7e77a0e56ff536d0ce8e108d8bd
```

### Verification (Merchant-Side)

```python
import hmac
import hashlib
import time

def verify_dari_webhook(payload_body: bytes, signature_header: str, secret: str):
    parts = dict(p.split("=", 1) for p in signature_header.split(","))
    timestamp = parts["t"]
    expected_sig = parts["v1"]

    # Replay protection: reject if > 5 minutes old
    if abs(time.time() - int(timestamp)) > 300:
        raise ValueError("Webhook too old")

    signed_payload = f"{timestamp}.".encode() + payload_body
    computed = hmac.new(
        secret.encode(), signed_payload, hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(computed, expected_sig):
        raise ValueError("Invalid signature")

    return True
```

### Node.js Verification

```javascript
const crypto = require('crypto');

function verifyDariWebhook(body, signatureHeader, secret) {
  const parts = Object.fromEntries(
    signatureHeader.split(',').map(p => p.split('='))
  );

  // Replay protection
  if (Math.abs(Date.now() / 1000 - parseInt(parts.t)) > 300) {
    throw new Error('Webhook too old');
  }

  const signedPayload = `${parts.t}.${body}`;
  const computed = crypto
    .createHmac('sha256', secret)
    .update(signedPayload)
    .digest('hex');

  if (!crypto.timingSafeEqual(Buffer.from(computed), Buffer.from(parts.v1))) {
    throw new Error('Invalid signature');
  }

  return true;
}
```

---

## Security Infrastructure

### Layers

| Layer | Component | Description |
|-------|-----------|-------------|
| Transport | TLS/HSTS | Strict Transport Security with preload |
| Rate Limiting | Per-IP | 120 req/min per IP address |
| Replay Protection | Nonce + Timestamp | X-Request-Nonce + X-Request-Timestamp headers |
| Request Signing | HMAC-SHA256 | Optional X-Request-Signature verification |
| Security Headers | OWASP | X-Content-Type-Options, X-Frame-Options, CSP, etc. |
| Data Masking | PCI-DSS | Sensitive fields masked in logs |

### Request Replay Protection

```bash
# Client sends unique nonce and timestamp with each request
curl -X POST /api/sessions/create \
  -H "X-Request-Nonce: $(uuidgen)" \
  -H "X-Request-Timestamp: $(date +%s)" \
  -H "Authorization: Bearer <token>" \
  -d '{"amount": 100}'
```

The server rejects:
- Timestamps older than 5 minutes
- Duplicate nonces within the 5-minute window

### Request Signature Verification

For high-security integrations, clients can sign requests:

```
Signature = HMAC-SHA256(secret, "<METHOD>\n<PATH>\n<SHA256(body)>")
```

Sent as `X-Request-Signature` header.

---

## Fraud Detection Engine

### Risk Score Factors (0-100)

| Factor | Points | Condition |
|--------|--------|-----------|
| High value | +25 | Amount > $10,000 |
| Elevated value | +15 | Amount > $5,000 |
| Cross-border | +10 | Payer ≠ Merchant country |
| Sanctioned country | +30 | OFAC sanctioned list |
| Elevated risk country | +15 | FATF high-risk |
| High-risk merchant country | +20 | Merchant in sanctioned country |
| Disposable email | +15 | Known throwaway domain |
| Suspicious IP | +10 | Known VPN/proxy ranges |
| Automated client | +5 | Bot-like User-Agent |
| Missing User-Agent | +10 | No UA header |
| Weak device fingerprint | +10 | Fingerprint < 8 chars |
| High velocity | +20 | > 20 txns/hour |
| Elevated velocity | +10 | > 10 txns/hour |

### Risk Thresholds

| Risk Level | Score Range | Action |
|------------|-------------|--------|
| Low | 0-25 | Auto-approve |
| Medium | 26-50 | Flag for review |
| High | 51-75 | Enhanced verification |
| Critical | 76-100 | Block transaction |

---

## Multi-Provider FX Rates

### Provider Priority

```
1. ExchangeRate-API  (free, no key required)
   ↓ fallback
2. OpenExchangeRates (requires OPENEXCHANGERATES_APP_ID)
   ↓ fallback
3. Fixer.io          (requires FIXER_API_KEY)
   ↓ fallback
4. Default rate: 1.0 (safety fallback)
```

### Configuration

```env
# Primary (always available)
# No config needed for ExchangeRate-API

# Fallback #1
OPENEXCHANGERATES_APP_ID=your_app_id

# Fallback #2
FIXER_API_KEY=your_api_key
```

### Caching

All FX rates are cached for 60 seconds to reduce API calls and improve latency.

---

## AML & Compliance

### Screening Pipeline

```
Payment Session
     │
     ▼
┌──────────────────┐
│ 1. OFAC Screening │──→ BLOCK if sanctioned country
└────────┬─────────┘
         │
┌────────▼─────────┐
│ 2. Jurisdiction   │──→ FLAG if FATF high-risk
└────────┬─────────┘
         │
┌────────▼─────────┐
│ 3. Amount Check   │──→ FLAG if > $10K CTR threshold
│    Structuring    │──→ FLAG if 24h cumulative near threshold
└────────┬─────────┘
         │
┌────────▼─────────┐
│ 4. Velocity Check │──→ FLAG if > 50 txns/hr (merchant)
│                   │──→ FLAG if > 10 txns/hr (payer)
└────────┬─────────┘
         │
┌────────▼─────────┐
│ 5. Wallet Screen  │──→ BLOCK if sanctioned prefix
└────────┬─────────┘
         │
         ▼
   ComplianceResult
   (pass / flag / block)
```

### Sanctioned Countries (OFAC)

North Korea, Iran, Syria, Cuba, Crimea, Donetsk, Luhansk

### High-Risk Jurisdictions (FATF)

Myanmar, Afghanistan, Yemen, South Sudan, Libya, Somalia, DRC, Venezuela, Pakistan, Nigeria, Haiti, Cayman Islands, Panama

### Audit Trail

Every screening result is persisted to `compliance_screenings` with:
- Screening type and result
- Risk level
- Entity details
- Full JSON details

---

## Currency Precision

### Fiat Currencies (ISO 4217)

| Currency | Precision | Example |
|----------|-----------|---------|
| USD, EUR, GBP, INR | 2 | $100.50 |
| JPY, KRW, VND | 0 | ¥1000 |
| KWD, BHD, OMR | 3 | KD 10.500 |

### Crypto / Stablecoins

| Token | Precision | Example |
|-------|-----------|---------|
| USDC, USDT, PYUSD | 6 | 100.123456 |
| BTC | 8 | 0.00123456 |
| ETH, MATIC | 18 | 0.123456789012345678 |
| XLM | 7 | 100.1234567 |

### Usage

```python
from app.services.currency_precision import round_amount, format_amount, validate_amount
from decimal import Decimal

# Round to correct precision
amount = round_amount(Decimal("100.12345"), "USD")  # → 100.12
amount = round_amount(Decimal("100.12345"), "JPY")  # → 100

# Format for display
display = format_amount(Decimal("100.5"), "USD")  # → "100.50"
display = format_amount(Decimal("1000"), "JPY")   # → "1000"

# Validate amount
is_valid, error = validate_amount(Decimal("100.123"), "USD")
# → (False, "USD supports at most 2 decimal places")
```

---

## Immutable Ledger

### Entry Types

| Type | Direction | Description |
|------|-----------|-------------|
| `CREDIT` | credit | Payment received |
| `DEBIT` | debit | Funds disbursed |
| `CONVERSION` | debit | Currency exchange |
| `SETTLEMENT` | credit | Funds settled to merchant |
| `FEE` | debit | Platform fee |
| `REFUND_DEBIT` | debit | Refund from merchant |
| `REFUND_CREDIT` | credit | Refund to payer |

### Hash Chain

Each entry's hash is computed as:

```
entry_hash = SHA256(prev_hash + ":" + canonical_json(entry_data))
```

This creates a tamper-evident chain. Any modification breaks the hash chain, which can be verified with:

```python
from app.services.ledger_service import verify_chain_integrity

is_valid, entries_checked = verify_chain_integrity(merchant_id, db)
```

### Recording Payments

```python
from app.services.ledger_service import record_payment_received

record_payment_received(
    db,
    merchant_id=str(merchant.id),
    session_id=session.id,
    token_amount=Decimal("100.50"),
    token_symbol="USDC",
    fiat_amount=Decimal("100.50"),
    fiat_currency="USD",
    exchange_rate=Decimal("1.0"),
    balance_after=merchant.balance_usdc,
)
```

---

## Monitoring & Observability

### Prometheus Metrics

Scrape endpoint: `GET /metrics`

| Metric | Type | Labels |
|--------|------|--------|
| `http_requests_total` | Counter | method, endpoint, status |
| `http_request_duration_seconds` | Histogram | method, endpoint |
| `payments_created_total` | Counter | currency, chain |
| `payments_completed_total` | Counter | currency, chain, status |
| `payment_amount_usd` | Histogram | - |
| `compliance_screenings_total` | Counter | result |
| `webhooks_sent_total` | Counter | status |
| `active_payment_sessions` | Gauge | - |

### Grafana Dashboard Queries

```promql
# Request rate
rate(http_requests_total[5m])

# P95 latency
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))

# Payment success rate
rate(payments_completed_total{status="paid"}[1h])
/ rate(payments_created_total[1h])

# Compliance block rate
rate(compliance_screenings_total{result="block"}[1h])
```

### Structured Logging

When `STRUCTURED_LOGGING=true`, all logs emit JSON:

```json
{
  "event": "Payment confirmed",
  "level": "info",
  "timestamp": "2024-01-15T10:30:00Z",
  "session_id": "pay_abc123",
  "amount": "100.50",
  "currency": "USDC"
}
```

### Audit Trail

Security-relevant events are logged with `AUDIT:` prefix:

```python
from app.core.monitoring import log_audit_event

log_audit_event(
    event_type="payment.confirmed",
    actor="blockchain_listener",
    resource_type="payment_session",
    resource_id="pay_abc123",
    details={"tx_hash": "0x...", "chain": "polygon"},
)
```

---

## Database Schema

### New Tables (v2.2.0)

```sql
-- Immutable financial ledger
ledger_entries (
    id, merchant_id, session_id,
    entry_type, amount, currency, direction,
    counter_amount, counter_currency, exchange_rate,
    reference_type, reference_id, description,
    balance_after, entry_hash, prev_hash, created_at
)

-- Payment state machine audit
payment_state_transitions (
    id, session_id, from_state, to_state,
    trigger, actor, metadata, created_at
)

-- Compliance screening audit
compliance_screenings (
    id, session_id, merchant_id,
    screening_type, result, risk_level,
    entity_type, entity_value, country,
    details, created_at
)
```

### Updated Enums

`PaymentStatus` now includes: `CREATED`, `PENDING`, `PROCESSING`, `CONFIRMED`, `PAID`, `EXPIRED`, `FAILED`, `REFUNDED`, `PARTIALLY_REFUNDED`

---

## Migration Guide

### From v2.1.0 to v2.2.0

1. **Install new dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Run migration:**
   ```bash
   psql -U your_user -d your_db -f migrations/enterprise_infrastructure_v2_2.sql
   ```

3. **Configure Redis (optional):**
   ```env
   REDIS_ENABLED=true
   REDIS_URL=redis://localhost:6379/0
   ```

4. **Configure FX fallbacks (optional):**
   ```env
   OPENEXCHANGERATES_APP_ID=your_id
   FIXER_API_KEY=your_key
   ```

5. **Restart the application:**
   ```bash
   uvicorn app.main:app --reload
   ```

### Breaking Changes

- `PaymentStatus` enum now includes `PROCESSING` and `CONFIRMED`
- Webhook payloads include `X-Payment-Signature` header (merchants should update verification)
- Token vault defaults to Redis when `REDIS_ENABLED=true`

### Backward Compatibility

- `PAID` status is preserved as a legacy alias for `CONFIRMED`
- In-memory token vault still works when Redis is disabled
- All existing API endpoints remain identical
- Webhook signature header is additive (existing integrations without verification continue to work)

---

## Configuration Reference

### New Environment Variables (v2.2.0)

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_ENABLED` | `false` | Enable Redis for token vault |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `REDIS_TOKEN_DB` | `1` | Redis DB number for tokens |
| `OPENEXCHANGERATES_APP_ID` | `""` | OpenExchangeRates API key |
| `FIXER_API_KEY` | `""` | Fixer.io API key |
| `AML_ENABLED` | `true` | Enable AML screening |
| `AML_THRESHOLD_USD` | `10000` | CTR reporting threshold |
| `AML_HIGH_RISK_THRESHOLD_USD` | `3000` | Enhanced due diligence threshold |
| `PROMETHEUS_ENABLED` | `true` | Enable Prometheus metrics |
| `STRUCTURED_LOGGING` | `true` | Enable JSON structured logs |
| `WEBHOOK_HMAC_ALGO` | `sha256` | Webhook signature algorithm |

---

## Compliance & Regulations

### Supported Standards

| Standard | Coverage | Implementation |
|----------|----------|----------------|
| **PCI-DSS** | Data masking, no card data storage | `mask_sensitive_value()` in security middleware |
| **OFAC** | Sanctions screening | `compliance_service.screen_country()` |
| **FATF** | High-risk jurisdiction detection | `compliance_service.HIGH_RISK_JURISDICTIONS` |
| **BSA/AML** | Transaction monitoring, CTR thresholds | `compliance_service.screen_transaction_amount()` |
| **SAR** | Suspicious activity detection | Velocity checks + structuring detection |
| **GDPR** | Data minimization | Token vault with TTL auto-expiry |
| **SOX** | Audit trails | Immutable ledger with hash chains |

### Reporting

- **CTR (Currency Transaction Report):** Auto-flagged when single transaction > $10,000 USD
- **Structuring Detection:** Flagged when 24-hour cumulative approaches 80% of CTR threshold
- **Velocity Alerts:** Flagged when transaction frequency exceeds normal patterns
- **All screenings are logged** in `compliance_screenings` table for audit

### Data Retention

| Data Type | Retention | Justification |
|-----------|-----------|---------------|
| Payment sessions | Indefinite | Business records |
| Ledger entries | Indefinite (immutable) | Financial audit trail |
| Compliance screenings | 7 years | BSA/AML requirement |
| Payment tokens | 30 minutes (TTL) | Ephemeral by design |
| Idempotency keys | 24 hours | Duplicate prevention |
| State transitions | Indefinite | Audit trail |

---

## Frontend Integration Guide

### Session Creation with v2.2.0 Features

```javascript
// Create payment session with compliance metadata
const response = await fetch('/api/sessions/create', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`,
    'Idempotency-Key': `order-${orderId}-${Date.now()}`,
    'X-Request-Nonce': crypto.randomUUID(),
    'X-Request-Timestamp': Math.floor(Date.now() / 1000).toString(),
  },
  body: JSON.stringify({
    amount: 99.99,
    currency: 'USD',
    payer_country: 'US',
    payer_currency: 'USD',
    success_url: 'https://shop.example.com/success',
    cancel_url: 'https://shop.example.com/cancel',
  }),
});

const session = await response.json();
// session.checkout_url → redirect customer here
// session.risk_score → check fraud score
// session.payment_token → tokenized reference
```

### Webhook Verification (React/Node Backend)

```javascript
// Express.js webhook handler
app.post('/webhooks/dari', express.raw({ type: 'application/json' }), (req, res) => {
  const signature = req.headers['x-payment-signature'];

  try {
    verifyDariWebhook(req.body, signature, process.env.DARI_WEBHOOK_SECRET);
  } catch (err) {
    return res.status(400).send('Invalid signature');
  }

  const event = JSON.parse(req.body);

  switch (event.event) {
    case 'payment.success':
      // Handle successful payment
      fulfillOrder(event.session_id, {
        amount: event.amount,
        currency: event.currency,
        txHash: event.tx_hash,
        payerCurrency: event.payer_currency,
        merchantCurrency: event.merchant_currency,
      });
      break;
  }

  res.json({ received: true });
});
```

### Payment Status Polling

```javascript
async function pollPaymentStatus(sessionId) {
  const response = await fetch(`/api/sessions/${sessionId}/status`);
  const data = await response.json();

  // v2.2.0 status values: created, pending, processing, confirmed, paid, expired, failed
  switch (data.status) {
    case 'confirmed':
    case 'paid':
      showSuccess(data);
      break;
    case 'processing':
      showProcessing(data);
      setTimeout(() => pollPaymentStatus(sessionId), 3000);
      break;
    case 'pending':
      showPending(data);
      setTimeout(() => pollPaymentStatus(sessionId), 5000);
      break;
    case 'expired':
      showExpired();
      break;
    case 'failed':
      showError(data);
      break;
  }
}
```

### Ledger Verification (Admin)

```python
# Verify merchant ledger integrity
import requests

response = requests.get(
    f'/api/admin/merchants/{merchant_id}/ledger/verify',
    headers={'Authorization': f'Bearer {admin_token}'}
)

result = response.json()
# { "valid": true, "entries_checked": 1234 }
```

---

## Files Changed in v2.2.0

| File | Change |
|------|--------|
| `app/core/config.py` | Added Redis, FX, AML, monitoring settings |
| `app/core/security_middleware.py` | Replay protection, expanded fraud engine, TLS |
| `app/core/monitoring.py` | **NEW** — Prometheus metrics + structured logging |
| `app/models/models.py` | Added PROCESSING/CONFIRMED status, LedgerEntry, PaymentStateTransition, ComplianceScreening |
| `app/services/state_machine.py` | **NEW** — Payment state machine with validation |
| `app/services/currency_precision.py` | **NEW** — Currency precision maps and formatters |
| `app/services/compliance_service.py` | **NEW** — AML/OFAC/velocity screening |
| `app/services/ledger_service.py` | **NEW** — Immutable hash-chained ledger |
| `app/services/price_service.py` | Multi-provider FX (ExchangeRate-API + OXR + Fixer) |
| `app/services/payment_tokenization.py` | Redis vault with in-memory fallback |
| `app/services/webhook_service.py` | HMAC-SHA256 signing + verification |
| `app/main.py` | MetricsMiddleware, /metrics endpoint, structured logging |
| `requirements.txt` | Added redis, prometheus-client, structlog |
| `migrations/enterprise_infrastructure_v2_2.sql` | **NEW** — 3 tables + enum updates |
