# Dual Currency, Tokenization, Security & Cross-border Payments

**Version 2.1.0** | Last Updated: March 12, 2026

This document covers the payment gateway improvements introduced in v2.1.0:

- **Dual currency tracking** — every transaction stores both the payer's and the merchant's currencies
- **Universal tokenization** — every payment session is automatically tokenized at creation
- **Security middleware** — rate limiting, OWASP security headers, and fraud risk scoring
- **Cross-border detection** — automatic identification and tagging of international transactions
- **PCI-DSS compliance helpers** — sensitive data masking

---

## Table of Contents

1. [Overview](#overview)
2. [Dual Currency Tracking](#dual-currency-tracking)
3. [Auto-Tokenization](#auto-tokenization)
4. [Cross-border Transactions](#cross-border-transactions)
5. [Fraud Risk Scoring](#fraud-risk-scoring)
6. [Security Middleware](#security-middleware)
7. [API Reference](#api-reference)
8. [Database Migration](#database-migration)
9. [Integration Examples](#integration-examples)

---

## Overview

```
                         ┌──────────────────────────────┐
  Merchant (INR, India)  │         Payment Session       │  Payer (EUR, Germany)
  ┌───────────┐          │  ┌────────────┬────────────┐  │       ┌───────────┐
  │ ₹ 4,150   │◀─────── │  │ Merchant   │ Payer      │  │──────▶│ € 54.20   │
  │ @ 83.0    │          │  │ INR        │ EUR        │  │       │ @ 1.08    │
  └───────────┘          │  └────────────┴────────────┘  │       └───────────┘
                         │  amount_fiat: $50 USD          │
                         │  is_cross_border: true         │
                         │  is_tokenized: true            │
                         │  risk_score: 15.0              │
                         └──────────────────────────────┘
```

Every payment session now carries:

| Field | Description |
|---|---|
| `payer_currency` / `payer_amount_local` | Payer's local currency and converted amount |
| `merchant_currency` / `merchant_amount_local` | Merchant's local currency and converted amount |
| `is_cross_border` | True when payer and merchant are in different countries |
| `payment_token` / `is_tokenized` | Opaque token for secure frontend transmission |
| `risk_score` | Fraud risk score 0–100 |

---

## Dual Currency Tracking

### How It Works

```
┌──────────────────────────────────────────────────────────────────────┐
│  Session Creation                                                      │
│                                                                        │
│  1. Merchant country → COUNTRY_CURRENCY_MAP → merchant_currency (INR) │
│  2. Payer country (optional) → COUNTRY_CURRENCY_MAP → payer_currency   │
│  3. convert_usdc_to_local() → exchange rate locked at session creation │
│  4. Both amounts stored permanently on payment_sessions table          │
└──────────────────────────────────────────────────────────────────────┘
```

Exchange rates are **locked at session creation time** — the rate is stored in `payer_exchange_rate` / `merchant_exchange_rate` and never re-queried for the same session. This protects both merchant and payer from rate fluctuation during checkout.

### Payer Currency Detection

The payer currency can be supplied in three ways (in priority order):

1. **Explicit in API request** — pass `payer_currency` and optional `payer_country` in `POST /api/sessions/create`
2. **Billing address country** — when the payer submits their billing address via `POST /checkout/{session_id}/payer-data`, the country is used to auto-detect the payer currency
3. **Not set** — `payer_currency` remains `null`; only merchant currency is populated

### Merchant Currency Detection

Merchant currency is resolved automatically at session creation:

1. If `merchant.base_currency` is set (configured during onboarding), that is used
2. Otherwise, the merchant's `country` field is mapped via `COUNTRY_CURRENCY_MAP`
3. Falls back to `USD` if no country is configured

---

## Auto-Tokenization

Every payment session is now tokenized automatically when it is created. You no longer need to call `POST /checkout/{session_id}/tokenize` manually (though you still can — it will refresh the token and return dual currency data).

### What Gets Tokenized

```json
{
  "session_id": "pay_abc123",
  "amount_fiat": "50.00",
  "fiat_currency": "USD",
  "amount_token": "50.02",
  "token": "USDC",
  "chain": "polygon",
  "merchant_id": "uuid...",
  "payer_currency": "EUR",
  "payer_currency_symbol": "€",
  "payer_amount_local": "54.20",
  "payer_exchange_rate": "1.084",
  "merchant_currency": "INR",
  "merchant_currency_symbol": "₹",
  "merchant_amount_local": "4150.00",
  "merchant_exchange_rate": "83.0",
  "is_cross_border": true,
  "payer_country": "Germany"
}
```

The token is an opaque `ptok_...` string stored in `payment_sessions.payment_token`. It lives in an in-memory vault with TTL equal to the session expiry (`PAYMENT_EXPIRY_MINUTES`).

### Token Flow

```
  [Session Created] ─── auto_tokenize_session() ──▶ ptok_xxx stored on session
        │
        ▼
  [Frontend] ─── receives payment_token in POST /api/sessions/create response
        │
        ▼
  [Frontend] ─── uses ptok_xxx for all subsequent calls (no raw amounts)
        │
        ▼
  [Backend] ─── GET /checkout/{id}/resolve-token?token=ptok_xxx
              ─── validates + returns real payment data
```

---

## Cross-border Transactions

A transaction is marked `is_cross_border = true` when:

- `payer_country` and merchant's `country` are set **and** differ
- OR `payer_currency` and `merchant_currency` differ (currency-based fallback)

Cross-border transactions automatically:
- Add `+10` to the fraud risk score
- Get tagged in the payment list response and webhooks
- Are indexed for fast analytics queries

### Supported Currencies

100+ countries are mapped. See `app/services/currency_service.py` — `COUNTRY_CURRENCY_MAP`. All conversions use live exchange rates from `exchangerate-api.com` (60-second cache).

---

## Fraud Risk Scoring

`compute_risk_score()` in `app/core/security_middleware.py` returns a score from **0 (no risk) to 100 (high risk)** and a list of triggered flags.

### Scoring Factors

| Factor | Score Added | Flag |
|---|---|---|
| Transaction > $10,000 | +25 | `high_value_transaction` |
| Transaction $5,000–$10,000 | +15 | `elevated_value_transaction` |
| Cross-border transaction | +10 | `cross_border` |
| Payer in high-risk country | +30 | `high_risk_payer_country` |
| Merchant in high-risk country | +20 | `high_risk_merchant_country` |
| Disposable email domain | +15 | `disposable_email` |

### High-risk Countries

Transactions from or to these jurisdictions receive elevated scoring: North Korea, Iran, Syria, Cuba, Crimea, Venezuela, Myanmar, Afghanistan.

### Risk Score in Responses

The `risk_score` and `risk_flags` are returned in:
- `GET /api/sessions/{session_id}` — `PaymentSessionStatus`
- `GET /merchant/payments` — `PaymentListItem`

Risk scoring is **advisory only** in the current version — transactions are not automatically blocked. You can add blocking logic by checking `risk_score >= threshold` in the session creation route.

---

## Security Middleware

`SecurityHeadersMiddleware` in `app/core/security_middleware.py` is applied globally.

### Rate Limiting

- **Limit**: 120 requests per minute, per IP
- **Window**: Rolling 60-second window (in-memory per worker)
- **Response on breach**: `HTTP 429` with `Retry-After: 60` header

### Security Headers

| Header | Value |
|---|---|
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `X-XSS-Protection` | `1; mode=block` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=()` |
| `Cache-Control` | `no-store, no-cache, must-revalidate` |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` *(HTTPS only)* |

### PCI-DSS Sensitive Data Masking

Use `mask_sensitive_value()` when logging potentially sensitive values. It shows the first 4 and last 2 characters with `***` in between:

```python
from app.core.security_middleware import mask_sensitive_value

mask_sensitive_value("4111111111111111")  # → "4111***11"
mask_sensitive_value("user@example.com") # → "user***om"
```

---

## API Reference

### Create Payment Session

`POST /api/sessions/create`

**New request fields:**

| Field | Type | Description |
|---|---|---|
| `payer_currency` | `string` (optional) | Payer's local currency code, e.g. `"EUR"` |
| `payer_country` | `string` (optional) | Payer's country for cross-border detection |

**New response fields:**

| Field | Type | Description |
|---|---|---|
| `payer_currency` | `string` | Resolved payer currency code |
| `payer_amount_local` | `decimal` | Amount in payer's currency |
| `merchant_currency` | `string` | Merchant's local currency code |
| `merchant_amount_local` | `decimal` | Amount in merchant's currency |
| `is_cross_border` | `boolean` | True if payer and merchant are in different countries |
| `payment_token` | `string` | Auto-generated `ptok_xxx` token |
| `is_tokenized` | `boolean` | Always `true` on new sessions |

**Example:**

```bash
curl -X POST https://api.dari.business/api/sessions/create \
  -H "Authorization: Bearer API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": 50.00,
    "currency": "USD",
    "payer_country": "Germany",
    "accepted_tokens": ["USDC"],
    "accepted_chains": ["polygon"],
    "order_id": "ORDER-001",
    "success_url": "https://store.com/success",
    "cancel_url": "https://store.com/cart"
  }'
```

```json
{
  "session_id": "pay_abc123",
  "checkout_url": "https://api.dari.business/checkout/pay_abc123",
  "amount": "50.00",
  "currency": "USD",
  "accepted_tokens": ["USDC"],
  "accepted_chains": ["polygon"],
  "expires_at": "2026-03-12T15:30:00Z",
  "status": "created",
  "payer_currency": "EUR",
  "payer_amount_local": "46.10",
  "merchant_currency": "INR",
  "merchant_amount_local": "4150.00",
  "is_cross_border": true,
  "payment_token": "ptok_xxxxxxxyyyyyyy",
  "is_tokenized": true
}
```

---

### Get Session Status

`GET /api/sessions/{session_id}`

**New response fields:**

| Field | Type | Description |
|---|---|---|
| `payer_currency` | `string` | Payer currency code |
| `payer_currency_symbol` | `string` | Payer currency symbol (€) |
| `payer_amount_local` | `float` | Amount in payer's currency |
| `payer_exchange_rate` | `float` | Rate used at session creation |
| `merchant_currency` | `string` | Merchant currency code |
| `merchant_currency_symbol` | `string` | Merchant currency symbol (₹) |
| `merchant_amount_local` | `float` | Amount in merchant's currency |
| `merchant_exchange_rate` | `float` | Rate used at session creation |
| `is_cross_border` | `boolean` | Cross-border flag |
| `is_tokenized` | `boolean` | Tokenization status |
| `risk_score` | `float` | Fraud risk score 0–100 |

---

### Submit Payer Data

`POST /checkout/{session_id}/payer-data`

When `billing_country` is provided and `payer_currency` was not set at session creation, the payer currency is **auto-detected** from the billing country. The `is_cross_border` flag and `risk_score` are updated at this point.

**Example body:**
```json
{
  "email": "buyer@example.com",
  "name": "Jane Doe",
  "billing_country": "Germany",
  "billing_city": "Berlin",
  "billing_postal_code": "10115"
}
```

After this call, `GET /api/sessions/{session_id}` will return populated `payer_currency`, `payer_amount_local`, and an updated `risk_score`.

---

### Tokenize Checkout (Manual Refresh)

`POST /checkout/{session_id}/tokenize`

Previously only returned `payment_token`, `expires_in_seconds`, `signature`. Now also returns:

```json
{
  "payment_token": "ptok_xxx",
  "expires_in_seconds": 1800,
  "signature": "abc123...",
  "payer_currency": "EUR",
  "payer_amount_local": 46.10,
  "merchant_currency": "INR",
  "merchant_amount_local": 4150.00
}
```

---

### Merchant Payment List

`GET /merchant/payments`

Each `PaymentListItem` now includes:

| Field | Type |
|---|---|
| `token` | `string` — which token was used |
| `chain` | `string` — which chain was used |
| `payer_currency` | `string` |
| `payer_amount_local` | `float` |
| `merchant_currency` | `string` |
| `merchant_amount_local` | `float` |
| `is_cross_border` | `boolean` |
| `is_tokenized` | `boolean` |
| `risk_score` | `float` |

---

### Webhook Payload

Webhook events sent to `webhook_url` now include dual currency:

```json
{
  "event": "payment.success",
  "session_id": "pay_abc123",
  "amount": "50.02",
  "currency": "USDC",
  "chain": "polygon",
  "token": "USDC",
  "tx_hash": "0xabc...",
  "status": "confirmed",
  "timestamp": "2026-03-12T15:30:00Z",
  "payer_currency": "EUR",
  "payer_amount_local": 46.10,
  "merchant_currency": "INR",
  "merchant_amount_local": 4150.00,
  "is_cross_border": true
}
```

---

## Database Migration

Run [`migrations/dual_currency_and_security.sql`](../migrations/dual_currency_and_security.sql) against your PostgreSQL database:

```bash
psql $DATABASE_URL -f migrations/dual_currency_and_security.sql
```

This is safe to run on existing databases — all `ALTER TABLE` statements use `IF NOT EXISTS`. The migration adds:

- 14 new columns to `payment_sessions`
- 5 performance indexes

**New columns summary:**

| Column | Type | Description |
|---|---|---|
| `is_tokenized` | `BOOLEAN DEFAULT FALSE` | Whether session was auto-tokenized |
| `token_created_at` | `TIMESTAMP` | When the payment token was issued |
| `payer_currency` | `VARCHAR(10)` | Payer's ISO 4217 currency code |
| `payer_currency_symbol` | `VARCHAR(10)` | Payer's currency symbol |
| `payer_amount_local` | `NUMERIC(14,2)` | Amount in payer's local currency |
| `payer_exchange_rate` | `NUMERIC(18,8)` | Rate locked at session creation |
| `merchant_currency` | `VARCHAR(10)` | Merchant's ISO 4217 currency code |
| `merchant_currency_symbol` | `VARCHAR(10)` | Merchant's currency symbol |
| `merchant_amount_local` | `NUMERIC(14,2)` | Amount in merchant's local currency |
| `merchant_exchange_rate` | `NUMERIC(18,8)` | Rate locked at session creation |
| `is_cross_border` | `BOOLEAN DEFAULT FALSE` | Cross-border flag |
| `payer_country` | `VARCHAR(100)` | Payer's country |
| `risk_score` | `NUMERIC(5,2)` | Fraud risk score 0–100 |
| `risk_flags` | `JSONB` | Array of triggered risk flags |

---

## Integration Examples

### React — Display Dual Currency

```tsx
const response = await fetch('/api/sessions/create', {
  method: 'POST',
  headers: { 'Authorization': `Bearer ${apiKey}`, 'Content-Type': 'application/json' },
  body: JSON.stringify({
    amount: 50.00,
    currency: 'USD',
    payer_country: userCountry,  // e.g. from browser locale
    order_id: 'ORDER-001',
    success_url: window.location.origin + '/success',
    cancel_url: window.location.origin + '/cart',
  }),
});

const session = await response.json();

// Show both currencies on your checkout page
console.log(`You pay: ${session.payer_amount_local} ${session.payer_currency}`);
console.log(`Merchant receives: ${session.merchant_amount_local} ${session.merchant_currency}`);
console.log(`Cross-border: ${session.is_cross_border}`);
```

### Python — Check for High-risk Payments

```python
from app.core.security_middleware import compute_risk_score

risk_score, flags = compute_risk_score(
    amount_usd=15000,
    payer_country="Germany",
    merchant_country="India",
    is_cross_border=True,
    payer_email="user@example.com",
)

if risk_score >= 50:
    # Flag for manual review
    notify_compliance_team(session_id, risk_score, flags)
```

### Webhook Handler — Dual Currency

```python
@app.post("/webhook")
async def handle_webhook(payload: dict):
    if payload["event"] == "payment.success":
        # Record in both currencies for accounting
        record_payment(
            session_id=payload["session_id"],
            amount_usd=float(payload["amount"]),
            merchant_currency=payload.get("merchant_currency"),
            merchant_local=payload.get("merchant_amount_local"),
            payer_currency=payload.get("payer_currency"),
            payer_local=payload.get("payer_amount_local"),
            is_cross_border=payload.get("is_cross_border", False),
        )
```

---

## Files Changed

| File | Change |
|---|---|
| `app/models/models.py` | 14 new columns on `PaymentSession` |
| `app/schemas/schemas.py` | `PaymentSessionCreate`, `PaymentSessionResponse`, `PaymentSessionStatus`, `PaymentListItem`, `WebhookPayload`, `TokenizeCheckoutResponse` updated |
| `app/services/payment_tokenization.py` | `build_session_token_payload()`, `auto_tokenize_session()` added |
| `app/core/security_middleware.py` | **New** — `SecurityHeadersMiddleware`, `compute_risk_score()`, `mask_sensitive_value()` |
| `app/routes/sessions.py` | Dual currency + risk scoring + auto-tokenize on session create |
| `app/routes/payments.py` | Dual currency + auto-tokenize on session create |
| `app/routes/payment_links.py` | Dual currency + auto-tokenize on link-based sessions |
| `app/routes/checkout.py` | Payer currency auto-detection, risk update on payer-data, token includes dual currency |
| `app/routes/merchant_payments.py` | `_session_to_list_item()` includes dual currency + risk fields |
| `app/services/webhook_service.py` | Webhook payload includes dual currency |
| `app/main.py` | `SecurityHeadersMiddleware` registered |
| `migrations/dual_currency_and_security.sql` | **New** — migration for all 14 columns + 5 indexes |
