# Frontend Integration Guide — V3 Features

**Dari for Business Backend** | API Reference for New Endpoints

---

## Table of Contents

1. [Overview](#overview)
2. [Authentication](#authentication)
3. [MRR & ARR Analytics](#mrr--arr-analytics)
4. [Payment Tracking](#payment-tracking)
5. [Subscription Tracking](#subscription-tracking)
6. [Payer Data Collection](#payer-data-collection)
7. [Payment Tokenization](#payment-tokenization)
8. [Caching & Performance](#caching--performance)
9. [Checkout Flow (Updated)](#checkout-flow-updated)
10. [TypeScript Types](#typescript-types)
11. [React Integration Examples](#react-integration-examples)

---

## Overview

### New Features in This Release

| Feature | Endpoints | Description |
|---------|-----------|-------------|
| MRR / ARR | 2 | Monthly & Annual Recurring Revenue with local currency |
| Payment Tracking | 1 | Detailed payment lifecycle with event timeline |
| Subscription Tracking | 1 | Subscription lifecycle with payment history |
| Payer Data Collection | 1 | Collect customer info before payment |
| Payment Tokenization | 2 | Tokenize checkout data for secure transmission |
| Cache Stats | 1 | Server cache hit/miss statistics |

### Base URL

```
Development: http://localhost:8000
Production:  https://api.chainpe.com
```

---

## Authentication

All merchant endpoints require a Bearer token. Obtain one via login or Google auth:

```
Authorization: Bearer <access_token>
```

The token is returned in the `POST /auth/login` or `POST /auth/google` response.

---

## MRR & ARR Analytics

### GET /analytics/mrr-arr

Returns current MRR and ARR figures in USD and optionally in the merchant's local currency.

**Headers:** `Authorization: Bearer <token>`

**Response:**

```json
{
  "mrr_usd": "1250.00",
  "arr_usd": "15000.00",
  "mrr_local": {
    "amount": "104125.00",
    "currency": "INR",
    "rate": "83.30"
  },
  "arr_local": {
    "amount": "1249500.00",
    "currency": "INR",
    "rate": "83.30"
  },
  "active_subscriptions": 47,
  "new_this_period": 5,
  "churned_this_period": 1,
  "net_revenue_change_pct": "8.4",
  "period": "month"
}
```

**Notes:**
- `mrr_local` / `arr_local` are `null` if the merchant's currency is USD or if conversion fails.
- `net_revenue_change_pct` compares to the previous month.

---

### GET /analytics/mrr-trend

Returns monthly MRR data points for charting.

**Headers:** `Authorization: Bearer <token>`

**Query Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `months` | int | 6 | Number of months to include |

**Response:**

```json
{
  "points": [
    {
      "date": "2025-01-01",
      "mrr_usd": 1100.0,
      "subscription_count": 42,
      "new": 6,
      "churned": 2
    },
    {
      "date": "2025-02-01",
      "mrr_usd": 1250.0,
      "subscription_count": 46,
      "new": 5,
      "churned": 1
    }
  ],
  "period_months": 6
}
```

---

## Payment Tracking

### GET /analytics/payments/{session_id}/track

Returns detailed tracking information for a specific payment session including an event timeline.

**Headers:** `Authorization: Bearer <token>`

**Response:**

```json
{
  "session_id": "ps_abc123",
  "status": "paid",
  "amount_fiat": 50.0,
  "fiat_currency": "USD",
  "token": "USDC",
  "chain": "stellar",
  "tx_hash": "abc123def456...",
  "block_number": 12345678,
  "confirmations": 6,
  "payer_email": "buyer@example.com",
  "payer_name": "John Doe",
  "created_at": "2025-01-15T10:00:00Z",
  "paid_at": "2025-01-15T10:05:32Z",
  "expires_at": "2025-01-15T10:30:00Z",
  "events": [
    {
      "type": "created",
      "timestamp": "2025-01-15T10:00:00Z",
      "data": {}
    },
    {
      "type": "payer_data_collected",
      "timestamp": "2025-01-15T10:02:15Z",
      "data": { "email": "buyer@example.com" }
    },
    {
      "type": "payment_detected",
      "timestamp": "2025-01-15T10:05:30Z",
      "data": { "tx_hash": "abc123..." }
    },
    {
      "type": "payment_confirmed",
      "timestamp": "2025-01-15T10:05:32Z",
      "data": { "confirmations": 6 }
    }
  ]
}
```

**Errors:**
- `404` — Session not found or does not belong to the merchant.

---

## Subscription Tracking

### GET /analytics/subscriptions/{subscription_id}/track

Returns detailed tracking information for a specific subscription.

**Headers:** `Authorization: Bearer <token>`

**Response:**

```json
{
  "id": "sub_xyz789",
  "plan_name": "Pro Monthly",
  "customer_email": "customer@example.com",
  "customer_name": "Jane Doe",
  "status": "active",
  "current_period_start": "2025-01-01T00:00:00Z",
  "current_period_end": "2025-02-01T00:00:00Z",
  "next_payment_at": "2025-02-01T00:00:00Z",
  "last_payment_at": "2025-01-01T10:32:00Z",
  "failed_payment_count": 0,
  "total_paid_usd": 299.0,
  "payment_count": 3,
  "events": [
    {
      "type": "subscription.created",
      "timestamp": "2024-11-01T00:00:00Z"
    },
    {
      "type": "payment.succeeded",
      "timestamp": "2025-01-01T10:32:00Z",
      "amount_usd": 99.0
    }
  ]
}
```

---

## Payer Data Collection

### POST /checkout/{session_id}/payer-data

Collects payer contact and billing information before showing the payment UI. Called from the checkout page.

> **No auth required** — this is called by the payer on the public checkout page.

**Request Body:**

```json
{
  "email": "buyer@example.com",
  "name": "John Doe",
  "phone": "+1234567890",
  "billing_address_line1": "123 Main St",
  "billing_address_line2": "Suite 4",
  "billing_city": "New York",
  "billing_state": "NY",
  "billing_postal_code": "10001",
  "billing_country": "US",
  "shipping_address_line1": "456 Oak Ave",
  "shipping_city": "Brooklyn",
  "shipping_state": "NY",
  "shipping_postal_code": "11201",
  "shipping_country": "US",
  "custom_fields": {
    "company": "Acme Inc",
    "order_notes": "Leave at door"
  }
}
```

All fields are **optional** but `email` and `name` are recommended.

**Response:**

```json
{
  "email": "buyer@example.com",
  "name": "John Doe",
  "phone": "+1234567890",
  "billing_address_line1": "123 Main St",
  "billing_city": "New York",
  "billing_state": "NY",
  "billing_postal_code": "10001",
  "billing_country": "US",
  "custom_fields": { "company": "Acme Inc" }
}
```

**Errors:**
- `404` — Session not found.
- `400` — Payment already completed.

---

## Payment Tokenization

### POST /checkout/{session_id}/tokenize

Tokenizes the checkout session. Returns an opaque token (`ptok_...`) that can be used instead of transmitting raw payment data. The frontend receives a signed reference.

> **No auth required** — called on the public checkout page.

**Request:** No body needed; the session ID in the URL is sufficient.

**Response:**

```json
{
  "payment_token": "ptok_a1b2c3d4e5f6...",
  "expires_in_seconds": 1800,
  "signature": "hmac_sha256_hex_digest..."
}
```

**Usage:** Store the `payment_token` in session/local storage. Use it when communicating with the backend instead of raw amounts/addresses.

---

### GET /checkout/{session_id}/resolve-token

Resolves a payment token back to the real checkout data.

**Query Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `token` | string | The `ptok_...` token to resolve |

**Response:**

```json
{
  "session_id": "ps_abc123",
  "amount_fiat": "50.00",
  "fiat_currency": "USD",
  "amount_token": "50.000000",
  "token": "USDC",
  "chain": "stellar",
  "merchant_id": "27dd5606-..."
}
```

**Errors:**
- `404` — Invalid or expired token.

---

## Caching & Performance

The backend now uses an in-process LRU cache with TTL per data region. Cached routes include:

| Route | Cache Region | TTL |
|-------|-------------|-----|
| `GET /wallets/` | wallets | 5 min |
| `GET /merchant/payments` | payments | 60s |
| `GET /analytics/overview` | analytics | 2 min |

Cache is automatically invalidated when data changes (e.g., adding a wallet clears the wallets cache).

### GET /analytics/cache/stats

Returns cache hit/miss statistics per region.

**Headers:** `Authorization: Bearer <token>`

**Response:**

```json
{
  "regions": {
    "analytics": { "size": 12, "max_size": 1024, "ttl": 120, "hits": 48, "misses": 15 },
    "wallets":   { "size": 3,  "max_size": 1024, "ttl": 300, "hits": 120, "misses": 8 },
    "payments":  { "size": 5,  "max_size": 1024, "ttl": 60,  "hits": 200, "misses": 35 }
  }
}
```

---

## Checkout Flow (Updated)

The hosted checkout page now supports a **two-step flow** when `collect_payer_data` is enabled on the payment session:

### Step 1 — Payer Data Collection

When a payment session is created with `collect_payer_data: true`, the checkout page displays a form overlay **before** showing the payment UI. The payer fills in their email, name, phone, and billing address.

### Step 2 — Payment UI

After the form is submitted (or if `collect_payer_data` is `false`), the standard multi-chain payment UI is shown with QR code, wallet links, and payment details.

### Step 3 — Tokenization (Optional)

After payer data is collected, the frontend can call `POST /checkout/{session_id}/tokenize` to get a secure payment token for use in subsequent API calls.

### Creating a Session with Payer Data Collection

```typescript
const session = await api.post('/payments/create', {
  amount_fiat: 100.00,
  fiat_currency: 'USD',
  success_url: 'https://yoursite.com/success',
  cancel_url: 'https://yoursite.com/cancel',
  collect_payer_data: true  // Enables the data collection step
});

// Redirect user to the checkout page
window.location.href = session.data.checkout_url;
```

### Flow Diagram

```
Customer visits checkout URL
        │
        ▼
  ┌─────────────┐
  │collect_payer │──── No ──→ Show Payment UI
  │    _data?    │
  └──────┬──────┘
         │ Yes
         ▼
  ┌─────────────┐
  │ Show Payer   │
  │ Data Form    │
  └──────┬──────┘
         │ Submit
         ▼
  POST /checkout/{id}/payer-data
         │
         ▼
  ┌─────────────┐
  │ Show Payment │
  │ UI (QR etc.) │
  └──────┬──────┘
         │ Optional
         ▼
  POST /checkout/{id}/tokenize
         │
         ▼
  Polling for payment confirmation
```

---

## TypeScript Types

Add these types to your frontend codebase:

```typescript
// ── MRR / ARR ──

interface LocalCurrencyAmount {
  amount: string;
  currency: string;
  rate: string;
}

interface MRRARRResponse {
  mrr_usd: string;
  arr_usd: string;
  mrr_local: LocalCurrencyAmount | null;
  arr_local: LocalCurrencyAmount | null;
  active_subscriptions: number;
  new_this_period: number;
  churned_this_period: number;
  net_revenue_change_pct: string | null;
  period: string;
}

interface MRRTrendPoint {
  date: string;       // ISO date string
  mrr_usd: number;
  subscription_count: number;
  new: number;
  churned: number;
}

interface MRRTrendResponse {
  points: MRRTrendPoint[];
  period_months: number;
}

// ── Payment Tracking ──

interface PaymentEvent {
  type: string;
  timestamp: string;
  data?: Record<string, unknown>;
}

interface PaymentTrackingResponse {
  session_id: string;
  status: string;
  amount_fiat: number;
  fiat_currency: string;
  token: string | null;
  chain: string | null;
  tx_hash: string | null;
  block_number: number | null;
  confirmations: number | null;
  payer_email: string | null;
  payer_name: string | null;
  created_at: string;
  paid_at: string | null;
  expires_at: string | null;
  events: PaymentEvent[];
}

// ── Subscription Tracking ──

interface SubscriptionTrackingResponse {
  id: string;
  plan_name: string;
  customer_email: string;
  customer_name: string | null;
  status: string;
  current_period_start: string;
  current_period_end: string;
  next_payment_at: string | null;
  last_payment_at: string | null;
  failed_payment_count: number;
  total_paid_usd: number;
  payment_count: number;
  events: Record<string, unknown>[];
}

// ── Payer Data ──

interface PayerDataCollect {
  email?: string;
  name?: string;
  phone?: string;
  billing_address_line1?: string;
  billing_address_line2?: string;
  billing_city?: string;
  billing_state?: string;
  billing_postal_code?: string;
  billing_country?: string;
  shipping_address_line1?: string;
  shipping_city?: string;
  shipping_state?: string;
  shipping_postal_code?: string;
  shipping_country?: string;
  custom_fields?: Record<string, unknown>;
}

interface PayerDataResponse {
  email: string | null;
  name: string | null;
  phone: string | null;
  billing_address_line1: string | null;
  billing_city: string | null;
  billing_state: string | null;
  billing_postal_code: string | null;
  billing_country: string | null;
  custom_fields: Record<string, unknown> | null;
}

// ── Payment Tokenization ──

interface TokenizeCheckoutResponse {
  payment_token: string;
  expires_in_seconds: number;
  signature: string;
}

interface ResolvedTokenData {
  session_id: string;
  amount_fiat: string;
  fiat_currency: string;
  amount_token: string;
  token: string;
  chain: string;
  merchant_id: string;
}

// ── Cache Stats ──

interface CacheRegionStats {
  size: number;
  max_size: number;
  ttl: number;
  hits: number;
  misses: number;
}

interface CacheStatsResponse {
  regions: Record<string, CacheRegionStats>;
}
```

---

## React Integration Examples

### MRR/ARR Dashboard Card

```tsx
import { useEffect, useState } from 'react';
import api from './api';

interface MRRDashboardProps {
  className?: string;
}

export function MRRDashboard({ className }: MRRDashboardProps) {
  const [data, setData] = useState<MRRARRResponse | null>(null);
  const [trend, setTrend] = useState<MRRTrendResponse | null>(null);

  useEffect(() => {
    api.get('/analytics/mrr-arr').then(r => setData(r.data));
    api.get('/analytics/mrr-trend?months=6').then(r => setTrend(r.data));
  }, []);

  if (!data) return <div>Loading...</div>;

  return (
    <div className={className}>
      <h3>Recurring Revenue</h3>
      <div className="stats-grid">
        <div>
          <span className="label">MRR</span>
          <span className="value">${Number(data.mrr_usd).toLocaleString()}</span>
          {data.mrr_local && (
            <span className="local">
              {data.mrr_local.currency} {Number(data.mrr_local.amount).toLocaleString()}
            </span>
          )}
        </div>
        <div>
          <span className="label">ARR</span>
          <span className="value">${Number(data.arr_usd).toLocaleString()}</span>
        </div>
        <div>
          <span className="label">Active Subs</span>
          <span className="value">{data.active_subscriptions}</span>
        </div>
        <div>
          <span className="label">Net Change</span>
          <span className="value">
            {data.net_revenue_change_pct
              ? `${Number(data.net_revenue_change_pct) > 0 ? '+' : ''}${data.net_revenue_change_pct}%`
              : 'N/A'}
          </span>
        </div>
      </div>

      {/* Chart: use trend.points with your charting library */}
      {trend && (
        <div className="chart-area">
          {/* Example with recharts, chart.js, etc. */}
          {/* data = trend.points.map(p => ({ x: p.date, y: p.mrr_usd })) */}
        </div>
      )}
    </div>
  );
}
```

---

### Payment Tracking Component

```tsx
import { useEffect, useState } from 'react';
import api from './api';

interface PaymentTrackerProps {
  sessionId: string;
}

export function PaymentTracker({ sessionId }: PaymentTrackerProps) {
  const [tracking, setTracking] = useState<PaymentTrackingResponse | null>(null);

  useEffect(() => {
    api.get(`/analytics/payments/${sessionId}/track`)
      .then(r => setTracking(r.data))
      .catch(() => setTracking(null));
  }, [sessionId]);

  if (!tracking) return <div>Loading payment details...</div>;

  return (
    <div className="payment-tracker">
      <div className="header">
        <span className={`status-badge ${tracking.status}`}>
          {tracking.status.toUpperCase()}
        </span>
        <span className="amount">
          {tracking.fiat_currency} {tracking.amount_fiat.toFixed(2)}
        </span>
      </div>

      <div className="details">
        {tracking.token && <div>Token: {tracking.token}</div>}
        {tracking.chain && <div>Chain: {tracking.chain}</div>}
        {tracking.tx_hash && (
          <div>TX: {tracking.tx_hash.slice(0, 16)}...</div>
        )}
        {tracking.payer_email && <div>Payer: {tracking.payer_email}</div>}
      </div>

      <div className="timeline">
        <h4>Events</h4>
        {tracking.events.map((event, i) => (
          <div key={i} className="event">
            <span className="event-type">{event.type}</span>
            <span className="event-time">
              {new Date(event.timestamp).toLocaleString()}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
```

---

### Payer Data Form (Custom Frontend)

If building a custom checkout instead of the hosted page:

```tsx
import { useState } from 'react';
import api from './api';

interface PayerFormProps {
  sessionId: string;
  onComplete: () => void;
}

export function PayerDataForm({ sessionId, onComplete }: PayerFormProps) {
  const [form, setForm] = useState<PayerDataCollect>({});
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      await api.post(`/checkout/${sessionId}/payer-data`, form);
      onComplete();
    } catch {
      alert('Failed to submit. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <input
        type="email"
        placeholder="Email"
        value={form.email || ''}
        onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
        required
      />
      <input
        type="text"
        placeholder="Full Name"
        value={form.name || ''}
        onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
        required
      />
      <input
        type="tel"
        placeholder="Phone (optional)"
        value={form.phone || ''}
        onChange={e => setForm(f => ({ ...f, phone: e.target.value }))}
      />
      {/* Add billing address fields as needed */}
      <button type="submit" disabled={loading}>
        {loading ? 'Submitting...' : 'Continue to Payment'}
      </button>
    </form>
  );
}
```

---

### Tokenized Checkout Flow

```tsx
import api from './api';

async function secureCheckoutFlow(sessionId: string) {
  // Step 1: Tokenize the session
  const { data } = await api.post(`/checkout/${sessionId}/tokenize`);
  const { payment_token, signature } = data;

  // Step 2: Store token (not raw payment data)
  sessionStorage.setItem('payment_token', payment_token);
  sessionStorage.setItem('payment_sig', signature);

  // Step 3: Use token for any subsequent API calls
  // The token resolves server-side — the frontend never handles raw amounts/addresses
  const resolved = await api.get(
    `/checkout/${sessionId}/resolve-token?token=${payment_token}`
  );

  return resolved.data;
}
```

---

## API Summary Table

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/analytics/mrr-arr` | Bearer | MRR & ARR with local currency |
| `GET` | `/analytics/mrr-trend?months=6` | Bearer | MRR trend for charting |
| `GET` | `/analytics/payments/{id}/track` | Bearer | Payment tracking + events |
| `GET` | `/analytics/subscriptions/{id}/track` | Bearer | Subscription tracking |
| `GET` | `/analytics/cache/stats` | Bearer | Cache statistics |
| `POST` | `/checkout/{id}/payer-data` | None | Collect payer info |
| `POST` | `/checkout/{id}/tokenize` | None | Tokenize checkout session |
| `GET` | `/checkout/{id}/resolve-token?token=ptok_...` | None | Resolve token to data |

---

## Migration Notes

1. **No breaking changes** — all existing endpoints continue to work as before.
2. **Caching is transparent** — the frontend doesn't need to change for cached routes; responses are just faster.
3. **Payer data collection** is opt-in via `collect_payer_data: true` on session creation.
4. **Tokenization** is optional; the existing raw-data flow still works but tokenization is recommended for security.
