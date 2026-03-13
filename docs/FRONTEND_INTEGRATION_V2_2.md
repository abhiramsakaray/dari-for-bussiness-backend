# Dari for Business v2.2.0 — Frontend Integration Guide

Complete reference for integrating all v2.2.0 features into your React/Next.js/Vue frontend.

## Table of Contents

1. [Authentication](#1-authentication)
2. [Merchant Onboarding Flow](#2-merchant-onboarding-flow)
3. [Payment Sessions (Core Flow)](#3-payment-sessions)
4. [Payment State Machine & Status Polling](#4-payment-state-machine--status-polling)
5. [Idempotent Requests](#5-idempotent-requests)
6. [Replay Protection (Nonce + Timestamp)](#6-replay-protection)
7. [Webhook HMAC Verification](#7-webhook-hmac-verification)
8. [Payment Links](#8-payment-links)
9. [Invoices](#9-invoices)
10. [Subscriptions & Recurring Payments](#10-subscriptions--recurring-payments)
11. [Refunds](#11-refunds)
12. [Analytics Dashboard](#12-analytics-dashboard)
13. [Wallet Management](#13-wallet-management)
14. [Coupons & Promo Codes](#14-coupons--promo-codes)
15. [Withdrawals](#15-withdrawals)
16. [Dual Currency Display](#16-dual-currency-display)
17. [Risk Score & Fraud Indicators](#17-risk-score--fraud-indicators)
18. [React SDK Helper](#18-react-sdk-helper)
19. [Error Handling Reference](#19-error-handling-reference)
20. [TypeScript Type Definitions](#20-typescript-type-definitions)

---

## 1. Authentication

### Register

```typescript
const register = async (name: string, email: string, password: string) => {
  const res = await fetch('/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name,
      email,
      password,
      merchant_category: 'startup', // individual | startup | small_business | enterprise | ngo
    }),
  });
  const data = await res.json();
  // { access_token, token_type, api_key, onboarding_completed, onboarding_step }
  localStorage.setItem('token', data.access_token);
  localStorage.setItem('api_key', data.api_key);
  return data;
};
```

### Login

```typescript
const login = async (email: string, password: string) => {
  const res = await fetch('/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  const data = await res.json();
  // { access_token, token_type, api_key, onboarding_completed, onboarding_step }
  localStorage.setItem('token', data.access_token);
  localStorage.setItem('api_key', data.api_key);
  return data;
};
```

### Google OAuth

```typescript
const googleAuth = async (googleIdToken: string) => {
  const res = await fetch('/auth/google', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token: googleIdToken }),
  });
  const data = await res.json();
  // { access_token, token_type, api_key, is_new_user, onboarding_completed, onboarding_step }

  if (data.is_new_user || !data.onboarding_completed) {
    // Redirect to onboarding
    router.push('/onboarding');
  }
  return data;
};
```

### Auth Header Helper

```typescript
// Use for all authenticated requests
const authHeaders = () => ({
  Authorization: `Bearer ${localStorage.getItem('token')}`,
  'Content-Type': 'application/json',
});

// Use for payment session creation (API key auth)
const apiKeyHeaders = () => ({
  'X-API-Key': localStorage.getItem('api_key')!,
  'Content-Type': 'application/json',
});
```

---

## 2. Merchant Onboarding Flow

Three-step guided onboarding. Check status first to resume where the merchant left off.

### Check Onboarding Status

```typescript
const getOnboardingStatus = async () => {
  const res = await fetch('/onboarding/status', { headers: authHeaders() });
  return await res.json();
  // {
  //   step: 0,               // 0=signup, 1=business_details, 2=wallets, 3=complete
  //   onboarding_completed: false,
  //   merchant_id, name, email,
  //   merchant_category, business_name, country,
  //   base_currency: "USD", currency_symbol: "$", currency_name: "US Dollar",
  //   has_wallets: false, wallet_count: 0
  // }
};
```

### Step 1: Business Details

```typescript
const submitBusinessDetails = async (details: {
  business_name: string;
  business_email?: string;
  country: string;
  merchant_category: 'individual' | 'startup' | 'small_business' | 'enterprise' | 'ngo';
}) => {
  const res = await fetch('/onboarding/business-details', {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(details),
  });
  return await res.json();
  // Currency auto-detected from country (e.g., India → INR ₹)
};
```

### Step 2: Wallet Setup

```typescript
const setupWallets = async () => {
  const res = await fetch('/onboarding/wallet-setup', {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({
      chains: ['polygon', 'stellar', 'ethereum'],  // Which chains to accept
      tokens: ['USDC', 'USDT'],                    // Which tokens
      auto_generate: true,                          // Auto-generate wallets
    }),
  });
  return await res.json();
};
```

### Step 3: Complete Onboarding

```typescript
const completeOnboarding = async () => {
  const res = await fetch('/onboarding/complete', {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({
      plan: 'growth', // free | growth | business | enterprise
    }),
  });
  const data = await res.json();
  // { message, merchant_id, api_key, onboarding_completed: true, wallets: [...] }

  // Store newly generated API key
  localStorage.setItem('api_key', data.api_key);
  return data;
};
```

---

## 3. Payment Sessions

The core payment flow. Create → Redirect → Poll → Complete.

### Create Payment Session

```typescript
const createPaymentSession = async (params: {
  amount: number;
  currency?: string;        // Default: merchant's base currency
  order_id?: string;
  payer_country?: string;   // For cross-border detection & AML
  payer_currency?: string;  // Payer's local currency
  success_url: string;
  cancel_url: string;
  accepted_tokens?: string[];   // Default: ['USDC', 'USDT', 'PYUSD']
  accepted_chains?: string[];   // Default: ['polygon', 'ethereum', 'stellar', 'tron']
  collect_payer_data?: boolean; // Default: true
  metadata?: Record<string, any>;
}) => {
  const res = await fetch('/api/sessions/create', {
    method: 'POST',
    headers: {
      ...apiKeyHeaders(),
      'Idempotency-Key': `order-${params.order_id}-${Date.now()}`,
      'X-Request-Nonce': crypto.randomUUID(),
      'X-Request-Timestamp': Math.floor(Date.now() / 1000).toString(),
    },
    body: JSON.stringify(params),
  });

  const session = await res.json();
  // {
  //   session_id: "pay_abc123",
  //   checkout_url: "/checkout/pay_abc123",
  //   amount: 99.99,
  //   currency: "USD",
  //   accepted_tokens: ["USDC", "USDT", "PYUSD"],
  //   accepted_chains: ["polygon", "stellar"],
  //   status: "created",
  //   expires_at: "2026-03-12T23:30:00Z",
  //   payment_token: "ptok_xxxxx",     // Tokenized reference
  //   is_tokenized: true,
  //
  //   // Dual currency (if payer_country/payer_currency was provided)
  //   payer_currency: "EUR",
  //   payer_amount_local: 92.50,
  //   merchant_currency: "INR",
  //   merchant_amount_local: 8350.00,
  //   is_cross_border: true,
  // }
  return session;
};
```

### Redirect to Checkout

```typescript
// Option 1: Redirect to hosted checkout page
window.location.href = session.checkout_url;

// Option 2: Open in iframe/modal
<iframe src={session.checkout_url} width="500" height="700" />

// Option 3: Build custom checkout with API data
const checkoutData = await fetch(`/checkout/api/${session.session_id}`);
```

### Get Payment Options (Custom Checkout)

```typescript
const getPaymentOptions = async (sessionId: string) => {
  const res = await fetch(`/api/sessions/${sessionId}/options`);
  return await res.json();
  // {
  //   session_id: "pay_abc123",
  //   payment_options: [
  //     {
  //       token: "USDC", chain: "polygon",
  //       chain_display: "Polygon",
  //       wallet_address: "0x1234...",
  //       amount: "99.990000",
  //       label: "USDC on Polygon",
  //       memo: null
  //     },
  //     {
  //       token: "USDC", chain: "stellar",
  //       chain_display: "Stellar",
  //       wallet_address: "GABCD...",
  //       amount: "99.990000",
  //       label: "USDC on Stellar",
  //       memo: "pay_abc123"
  //     },
  //   ]
  // }
};
```

### Select Payment Method

```typescript
const selectPaymentMethod = async (sessionId: string, token: string, chain: string) => {
  const res = await fetch(`/api/sessions/${sessionId}/select`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token, chain }),
  });
  return await res.json();
  // Returns QR code data and wallet address for selected chain
};
```

---

## 4. Payment State Machine & Status Polling

v2.2.0 introduces `processing` and `confirmed` states. Handle all states:

```
created → pending → processing → confirmed → paid
                                    ↓
                              refunded / partially_refunded
```

### Poll Payment Status

```typescript
type PaymentStatus =
  | 'created'
  | 'pending'
  | 'processing'
  | 'confirmed'
  | 'paid'
  | 'expired'
  | 'failed'
  | 'refunded'
  | 'partially_refunded';

interface PaymentStatusResponse {
  session_id: string;
  status: PaymentStatus;
  amount: string;
  currency: string;
  token?: string;
  chain?: string;
  tx_hash?: string;
  block_number?: number;
  confirmations?: number;
  order_id?: string;
  created_at: string;
  paid_at?: string;
  expires_at?: string;

  // Dual currency
  payer_currency?: string;
  payer_currency_symbol?: string;
  payer_amount_local?: number;
  payer_exchange_rate?: number;
  merchant_currency?: string;
  merchant_currency_symbol?: string;
  merchant_amount_local?: number;
  merchant_exchange_rate?: number;
  is_cross_border: boolean;

  // Security
  risk_score?: number;
  is_tokenized: boolean;
}

const pollPaymentStatus = async (sessionId: string): Promise<void> => {
  const res = await fetch(`/api/sessions/${sessionId}/status`);
  const data: PaymentStatusResponse = await res.json();

  switch (data.status) {
    case 'created':
      // Awaiting customer action — show checkout
      showCheckout(data);
      setTimeout(() => pollPaymentStatus(sessionId), 5000);
      break;

    case 'pending':
      // Payment detected on-chain, awaiting confirmations
      showPending(data);
      setTimeout(() => pollPaymentStatus(sessionId), 3000);
      break;

    case 'processing':
      // Transaction is being confirmed on-chain
      showProcessing({
        ...data,
        message: `Processing on ${data.chain}... ${data.confirmations ?? 0} confirmations`,
      });
      setTimeout(() => pollPaymentStatus(sessionId), 2000);
      break;

    case 'confirmed':
    case 'paid':
      // Payment successful
      showSuccess({
        amount: data.amount,
        currency: data.currency,
        txHash: data.tx_hash,
        chain: data.chain,
        paidAt: data.paid_at,
        // Show local currency amounts
        merchantAmount: data.merchant_amount_local
          ? `${data.merchant_currency_symbol}${data.merchant_amount_local.toLocaleString()}`
          : undefined,
        payerAmount: data.payer_amount_local
          ? `${data.payer_currency_symbol}${data.payer_amount_local.toLocaleString()}`
          : undefined,
      });
      break;

    case 'expired':
      // Session expired — offer retry
      showExpired({ sessionId, onRetry: () => window.location.reload() });
      break;

    case 'failed':
      // Transaction failed
      showError({ message: 'Payment failed. Please try again.' });
      break;

    case 'refunded':
      showRefunded(data);
      break;

    case 'partially_refunded':
      showPartialRefund(data);
      break;
  }
};
```

### React Hook: usePaymentStatus

```tsx
import { useState, useEffect, useCallback, useRef } from 'react';

function usePaymentStatus(sessionId: string) {
  const [status, setStatus] = useState<PaymentStatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<NodeJS.Timeout>();

  const poll = useCallback(async () => {
    try {
      const res = await fetch(`/api/sessions/${sessionId}/status`);
      if (!res.ok) throw new Error('Failed to fetch status');
      const data: PaymentStatusResponse = await res.json();
      setStatus(data);

      // Continue polling for non-terminal states
      const terminal = ['confirmed', 'paid', 'expired', 'failed', 'refunded'];
      if (!terminal.includes(data.status)) {
        const interval = data.status === 'processing' ? 2000 : 5000;
        timerRef.current = setTimeout(poll, interval);
      }
    } catch (err: any) {
      setError(err.message);
    }
  }, [sessionId]);

  useEffect(() => {
    poll();
    return () => clearTimeout(timerRef.current);
  }, [poll]);

  return { status, error, refetch: poll };
}
```

### Status Badge Component

```tsx
const StatusBadge = ({ status }: { status: PaymentStatus }) => {
  const config: Record<PaymentStatus, { color: string; label: string }> = {
    created:              { color: 'gray',   label: 'Awaiting Payment' },
    pending:              { color: 'yellow', label: 'Payment Detected' },
    processing:           { color: 'blue',   label: 'Processing' },
    confirmed:            { color: 'green',  label: 'Confirmed' },
    paid:                 { color: 'green',  label: 'Paid' },
    expired:              { color: 'red',    label: 'Expired' },
    failed:               { color: 'red',    label: 'Failed' },
    refunded:             { color: 'orange', label: 'Refunded' },
    partially_refunded:   { color: 'orange', label: 'Partial Refund' },
  };

  const { color, label } = config[status] ?? { color: 'gray', label: status };
  return <span className={`badge badge-${color}`}>{label}</span>;
};
```

---

## 5. Idempotent Requests

Prevent duplicate payments, invoices, and refunds by sending an `Idempotency-Key` header.

```typescript
// Helper: generate deterministic idempotency key
const idempotencyKey = (resourceType: string, uniqueId: string, attempt = 1) =>
  `${resourceType}-${uniqueId}-${attempt}`;

// Usage in payment creation
const createPayment = async (orderId: string, amount: number) => {
  const res = await fetch('/api/sessions/create', {
    method: 'POST',
    headers: {
      ...apiKeyHeaders(),
      'Idempotency-Key': idempotencyKey('payment', orderId),
    },
    body: JSON.stringify({ amount, order_id: orderId, currency: 'USD',
      success_url: '/success', cancel_url: '/cancel' }),
  });

  if (res.status === 409) {
    // Request is already being processed — don't retry immediately
    console.warn('Duplicate request detected');
  }

  return await res.json();
};
```

**Rules:**
- Same idempotency key + same body ➝ returns cached response (200)
- Same idempotency key + processing ➝ returns 409 Conflict
- Keys expire after **24 hours**
- Use unique keys per operation (e.g., `payment-ORDER123-1`)

---

## 6. Replay Protection

v2.2.0 rejects replayed requests. Send nonce + timestamp on sensitive endpoints:

```typescript
const secureHeaders = () => ({
  ...authHeaders(),
  'X-Request-Nonce': crypto.randomUUID(),
  'X-Request-Timestamp': Math.floor(Date.now() / 1000).toString(),
});

// Example: create refund with replay protection
const createRefund = async (sessionId: string, amount?: number) => {
  const res = await fetch('/refunds', {
    method: 'POST',
    headers: secureHeaders(),
    body: JSON.stringify({
      payment_session_id: sessionId,
      amount, // omit for full refund
      reason: 'Customer requested',
    }),
  });
  return await res.json();
};
```

**How it works:**
- `X-Request-Nonce`: Must be unique UUID per request
- `X-Request-Timestamp`: Unix timestamp, must be within 5 minutes of server time
- Server rejects duplicate nonces within the 5-minute window

---

## 7. Webhook HMAC Verification

v2.2.0 signs all webhook payloads with HMAC-SHA256. Verify on your backend:

### Node.js / Express

```typescript
import crypto from 'crypto';
import express from 'express';

const WEBHOOK_SECRET = process.env.DARI_WEBHOOK_SECRET!;

// Must use raw body for signature verification
app.post('/webhooks/dari', express.raw({ type: 'application/json' }), (req, res) => {
  const signature = req.headers['x-payment-signature'] as string;

  if (!verifySignature(req.body, signature, WEBHOOK_SECRET)) {
    return res.status(400).json({ error: 'Invalid signature' });
  }

  const event = JSON.parse(req.body.toString());

  switch (event.event) {
    case 'payment.succeeded':
      handlePaymentSuccess(event);
      break;
    case 'payment.failed':
      handlePaymentFailed(event);
      break;
    case 'payment.expired':
      handlePaymentExpired(event);
      break;
  }

  res.json({ received: true });
});

function verifySignature(body: Buffer, signature: string, secret: string): boolean {
  if (!signature) return false;

  const parts = Object.fromEntries(
    signature.split(',').map((p) => {
      const idx = p.indexOf('=');
      return [p.slice(0, idx), p.slice(idx + 1)];
    })
  );

  const timestamp = parts['t'];
  const expectedSig = parts['v1'];

  // Reject if older than 5 minutes (replay protection)
  if (Math.abs(Date.now() / 1000 - parseInt(timestamp)) > 300) {
    return false;
  }

  const signedPayload = `${timestamp}.${body.toString()}`;
  const computed = crypto
    .createHmac('sha256', secret)
    .update(signedPayload)
    .digest('hex');

  return crypto.timingSafeEqual(Buffer.from(computed), Buffer.from(expectedSig));
}
```

### Webhook Payload Shape

```typescript
interface DariWebhookPayload {
  event: 'payment.succeeded' | 'payment.failed' | 'payment.expired';
  session_id: string;
  amount: string;
  currency: string;
  token?: string;
  chain?: string;
  tx_hash?: string;
  block_number?: number;
  confirmations?: number;
  status: string;
  timestamp: string;

  // Dual currency
  payer_currency?: string;
  payer_amount_local?: number;
  merchant_currency?: string;
  merchant_amount_local?: number;
  is_cross_border: boolean;
}
```

---

## 8. Payment Links

Reusable, shareable payment links for products or services.

### Create Payment Link

```typescript
const createPaymentLink = async (params: {
  name: string;
  description?: string;
  amount_fiat?: number;         // Omit for variable/customer-entered amount
  fiat_currency?: string;
  is_amount_fixed?: boolean;    // false = customer enters amount
  min_amount?: number;
  max_amount?: number;
  success_url?: string;
  cancel_url?: string;
  single_use?: boolean;
  expires_at?: string;          // ISO datetime
  collect_payer_data?: boolean;
}) => {
  const res = await fetch('/payment-links', {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(params),
  });
  return await res.json();
  // { id, short_code, url: "/pay/{short_code}", ... }
};
```

### List Payment Links

```typescript
const listPaymentLinks = async (page = 1, limit = 20) => {
  const res = await fetch(`/payment-links?skip=${(page - 1) * limit}&limit=${limit}`, {
    headers: authHeaders(),
  });
  return await res.json();
};
```

### Get Payment Link Analytics

```typescript
const getLinkAnalytics = async (linkId: string) => {
  const res = await fetch(`/payment-links/${linkId}/analytics`, {
    headers: authHeaders(),
  });
  return await res.json();
  // { total_views, total_sessions, total_paid, total_revenue, conversion_rate }
};
```

---

## 9. Invoices

Full invoice lifecycle: create → send → track → get paid.

### Create Invoice

```typescript
const createInvoice = async (params: {
  customer_name: string;
  customer_email: string;
  amount: number;
  currency?: string;
  due_date?: string;         // ISO date
  items?: Array<{
    description: string;
    quantity: number;
    unit_price: number;
  }>;
  notes?: string;
  tax_percent?: number;
  discount_percent?: number;
}) => {
  const res = await fetch('/invoices', {
    method: 'POST',
    headers: {
      ...authHeaders(),
      'Idempotency-Key': `invoice-${params.customer_email}-${Date.now()}`,
    },
    body: JSON.stringify(params),
  });
  return await res.json();
};
```

### Send Invoice

```typescript
const sendInvoice = async (invoiceId: string) => {
  const res = await fetch(`/invoices/${invoiceId}/send`, {
    method: 'POST',
    headers: authHeaders(),
  });
  return await res.json();
};
```

### Invoice Status Flow

```
draft → sent → paid
         ↓
       overdue → cancelled
```

### List Invoices with Filters

```typescript
const listInvoices = async (status?: string, page = 1) => {
  const params = new URLSearchParams({ skip: String((page - 1) * 20), limit: '20' });
  if (status) params.append('status', status);

  const res = await fetch(`/invoices?${params}`, { headers: authHeaders() });
  return await res.json();
};
```

---

## 10. Subscriptions & Recurring Payments

### Create a Plan

```typescript
const createPlan = async (params: {
  name: string;
  description?: string;
  amount: number;
  currency?: string;
  interval: 'daily' | 'weekly' | 'monthly' | 'quarterly' | 'yearly';
  trial_days?: number;
  trial_type?: 'free' | 'reduced_price' | 'paid';
  trial_price?: number;
  setup_fee?: number;
  max_billing_cycles?: number;
}) => {
  const res = await fetch('/subscriptions/plans', {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(params),
  });
  return await res.json();
};
```

### Create a Subscription

```typescript
const createSubscription = async (planId: string, customerEmail: string) => {
  const res = await fetch('/subscriptions', {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({
      plan_id: planId,
      customer_email: customerEmail,
    }),
  });
  return await res.json();
  // { id, plan_id, status: "trialing" | "active", next_payment_date, ... }
};
```

### Manage Subscription

```typescript
// Cancel
await fetch(`/subscriptions/${subId}/cancel`, { method: 'POST', headers: authHeaders() });

// Pause
await fetch(`/subscriptions/${subId}/pause`, { method: 'POST', headers: authHeaders() });

// Resume
await fetch(`/subscriptions/${subId}/resume`, { method: 'POST', headers: authHeaders() });

// Extend trial
await fetch(`/subscriptions/${subId}/extend-trial`, {
  method: 'POST',
  headers: authHeaders(),
  body: JSON.stringify({ additional_days: 7 }),
});

// End trial early → start billing
await fetch(`/subscriptions/${subId}/end-trial`, {
  method: 'POST',
  headers: authHeaders(),
});
```

### Subscription Status Flow

```
trialing → active → paused → active → cancelled
                  ↘ past_due → cancelled
```

---

## 11. Refunds

### Check Refund Eligibility

```typescript
const checkRefundEligibility = async (sessionId: string) => {
  const res = await fetch(`/refunds/eligibility/${sessionId}`, {
    headers: authHeaders(),
  });
  return await res.json();
  // {
  //   eligible: true,
  //   max_refund_amount: "99.99",
  //   token: "USDC",
  //   chain: "polygon",
  //   settlement_status: "platform_wallet",
  //   already_refunded: "0",
  //   remaining_refundable: "99.99"
  // }
};
```

### Create Refund

```typescript
const createRefund = async (params: {
  payment_session_id: string;
  amount?: number;      // Omit for full refund
  reason?: string;
  refund_address?: string;  // Customer's wallet (auto-detected if omitted)
}) => {
  const res = await fetch('/refunds', {
    method: 'POST',
    headers: {
      ...secureHeaders(),
      'Idempotency-Key': `refund-${params.payment_session_id}-${Date.now()}`,
    },
    body: JSON.stringify(params),
  });
  return await res.json();
};
```

### List Refunds

```typescript
const listRefunds = async (status?: string) => {
  const params = new URLSearchParams();
  if (status) params.append('status', status); // pending, completed, failed, queued, cancelled

  const res = await fetch(`/refunds?${params}`, { headers: authHeaders() });
  return await res.json();
};
```

---

## 12. Analytics Dashboard

### Overview

```typescript
const getAnalytics = async (period: 'day' | 'week' | 'month' | 'year' = 'month') => {
  const res = await fetch(`/analytics/overview?period=${period}`, {
    headers: authHeaders(),
  });
  return await res.json();
  // {
  //   period_start, period_end, period,
  //   payments: {
  //     total_payments, successful_payments, failed_payments,
  //     total_volume, avg_payment, conversion_rate
  //   },
  //   volume_by_token: [{ token: "USDC", volume, count, percentage }],
  //   volume_by_chain: [{ chain: "polygon", volume, count, percentage }],
  //   invoices_sent, invoices_paid, invoice_volume,
  //   active_subscriptions, new_subscriptions, churned_subscriptions,
  //   subscription_mrr,
  //   payments_change_pct, volume_change_pct,
  //   currency: "INR", currency_symbol: "₹"
  // }
};
```

### Revenue Time Series (Charts)

```typescript
const getRevenueTimeSeries = async (period: 'day' | 'week' | 'month' | 'year') => {
  const res = await fetch(`/analytics/revenue?period=${period}`, {
    headers: authHeaders(),
  });
  return await res.json();
  // Array of { date, revenue, count } — for line charts
};
```

### MRR / ARR

```typescript
const getMRR = async () => {
  const res = await fetch('/analytics/mrr', { headers: authHeaders() });
  return await res.json();
  // { mrr, arr, active_subscriptions, avg_revenue_per_sub, ... }
};
```

### Payment Tracking

```typescript
const trackPayments = async (
  page = 1,
  status?: string,
  chain?: string,
  startDate?: string,
  endDate?: string,
) => {
  const params = new URLSearchParams({
    skip: String((page - 1) * 20),
    limit: '20',
  });
  if (status) params.append('status', status);
  if (chain) params.append('chain', chain);
  if (startDate) params.append('start_date', startDate);
  if (endDate) params.append('end_date', endDate);

  const res = await fetch(`/analytics/payments?${params}`, {
    headers: authHeaders(),
  });
  return await res.json();
};
```

---

## 13. Wallet Management

### List All Wallets

```typescript
const listWallets = async () => {
  const res = await fetch('/merchant/wallets', { headers: authHeaders() });
  return await res.json();
  // { wallets: [{ id, chain, wallet_address, is_active, created_at }] }
};
```

### Wallet Dashboard (Live On-Chain Balances)

```typescript
const getWalletDashboard = async () => {
  const res = await fetch('/merchant/wallets/dashboard', { headers: authHeaders() });
  return await res.json();
  // {
  //   wallets: [{
  //     chain: "polygon",
  //     address: "0x...",
  //     balances: { USDC: "1234.56", USDT: "500.00" },
  //     balances_local: {
  //       USDC: { amount_usdc: 1234.56, amount_local: 103245.00,
  //               local_currency: "INR", local_symbol: "₹",
  //               display_local: "₹1,03,245.00" }
  //     }
  //   }],
  //   total_balance_usdc: 1734.56,
  //   total_balance_local: { ... },
  //   pending_withdrawals: 0,
  //   net_available: 1734.56
  // }
};
```

### Add Wallet

```typescript
const addWallet = async (chain: string, walletAddress: string) => {
  const res = await fetch('/merchant/wallets', {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ chain, wallet_address: walletAddress }),
  });
  return await res.json();
};
```

---

## 14. Coupons & Promo Codes

### Create Coupon (Merchant)

```typescript
const createCoupon = async (params: {
  code: string;                     // e.g., "WELCOME20"
  discount_type: 'percentage' | 'fixed';
  discount_value: number;           // 20 for 20% or 5.00 for $5
  max_discount?: number;            // Cap for percentage discounts
  min_order_amount?: number;
  max_uses?: number;                // Total redemptions allowed
  max_uses_per_user?: number;
  expires_at?: string;              // ISO datetime
}) => {
  const res = await fetch('/api/business/promo/create', {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(params),
  });
  return await res.json();
};
```

### Apply Coupon (Customer Checkout)

```typescript
const applyCoupon = async (sessionId: string, couponCode: string) => {
  const res = await fetch('/api/payment/apply-coupon', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: sessionId,
      coupon_code: couponCode,
    }),
  });

  if (!res.ok) {
    const error = await res.json();
    // error.detail: "Coupon not found" | "Coupon expired" | "Coupon usage limit reached" ...
    return { valid: false, message: error.detail };
  }

  const data = await res.json();
  // {
  //   valid: true,
  //   discount_amount: 20.00,
  //   original_amount: 100.00,
  //   final_amount: 80.00,
  //   discount_label: "20% off"
  // }
  return data;
};
```

### Complete 100% Discounted Payment

```typescript
// When coupon covers full amount
const completeFreePayment = async (sessionId: string, couponCode: string) => {
  const res = await fetch('/api/payment/complete-coupon-payment', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: sessionId,
      coupon_code: couponCode,
    }),
  });
  return await res.json();
};
```

### Coupon Analytics (Merchant)

```typescript
const getCouponAnalytics = async (couponId: string) => {
  const res = await fetch(`/api/business/promo/${couponId}/analytics`, {
    headers: authHeaders(),
  });
  return await res.json();
  // { total_uses, total_discount_given, unique_users, revenue_generated }
};
```

---

## 15. Withdrawals

```typescript
// List withdrawals
const listWithdrawals = async () => {
  const res = await fetch('/withdrawals', { headers: authHeaders() });
  return await res.json();
};

// Create withdrawal request
const createWithdrawal = async (params: {
  amount: number;
  token: string;            // USDC, USDT
  chain: string;            // polygon, ethereum, stellar
  destination_address: string;
}) => {
  const res = await fetch('/withdrawals', {
    method: 'POST',
    headers: secureHeaders(),
    body: JSON.stringify(params),
  });
  return await res.json();
};
```

---

## 16. Dual Currency Display

v2.2.0 provides amounts in both USDC and the merchant/payer's local currency.

### React Component

```tsx
interface DualCurrencyProps {
  amountUsdc: number;
  amountLocal?: number;
  localCurrency?: string;
  localSymbol?: string;
  displayLocal?: string;
}

const DualCurrency = ({
  amountUsdc,
  amountLocal,
  localCurrency,
  localSymbol,
  displayLocal,
}: DualCurrencyProps) => (
  <div className="dual-currency">
    <span className="primary">${amountUsdc.toLocaleString()} USDC</span>
    {amountLocal && localCurrency !== 'USD' && (
      <span className="local">
        ≈ {displayLocal || `${localSymbol}${amountLocal.toLocaleString()}`}
      </span>
    )}
  </div>
);
```

### Cross-Border Indicator

```tsx
const CrossBorderBadge = ({ isCrossBorder, payerCurrency, merchantCurrency }: {
  isCrossBorder: boolean;
  payerCurrency?: string;
  merchantCurrency?: string;
}) => {
  if (!isCrossBorder) return null;
  return (
    <span className="badge badge-purple" title={`${payerCurrency} → ${merchantCurrency}`}>
      🌐 Cross-Border
    </span>
  );
};
```

---

## 17. Risk Score & Fraud Indicators

Payment sessions include a `risk_score` (0-100). Display appropriately:

```tsx
const RiskIndicator = ({ score }: { score?: number }) => {
  if (score == null) return null;

  const level =
    score <= 25 ? 'low' :
    score <= 50 ? 'medium' :
    score <= 75 ? 'high' : 'critical';

  const colors = {
    low:      { bg: '#dcfce7', text: '#166534', label: 'Low Risk' },
    medium:   { bg: '#fef9c3', text: '#854d0e', label: 'Medium Risk' },
    high:     { bg: '#fed7aa', text: '#9a3412', label: 'High Risk' },
    critical: { bg: '#fecaca', text: '#991b1b', label: 'Critical Risk' },
  };

  const config = colors[level];

  return (
    <div style={{ background: config.bg, color: config.text, padding: '4px 12px', borderRadius: 6 }}>
      {config.label} ({score})
    </div>
  );
};
```

### Risk Factors Tooltip

```tsx
// On the merchant dashboard, show why a payment was flagged
const RiskDetails = ({ session }: { session: PaymentStatusResponse }) => (
  <div className="risk-details">
    <RiskIndicator score={session.risk_score} />
    {session.is_cross_border && <span>⚠️ Cross-border transaction</span>}
    {session.risk_score && session.risk_score > 50 && (
      <span>🔍 Enhanced verification recommended</span>
    )}
  </div>
);
```

---

## 18. React SDK Helper

A complete API client for use across your React app:

```typescript
// lib/dari-client.ts

const BASE_URL = process.env.NEXT_PUBLIC_DARI_API_URL || '';

class DariClient {
  private token: string | null = null;
  private apiKey: string | null = null;

  setAuth(token: string, apiKey: string) {
    this.token = token;
    this.apiKey = apiKey;
  }

  private headers(): HeadersInit {
    return {
      Authorization: `Bearer ${this.token}`,
      'Content-Type': 'application/json',
    };
  }

  private secureHeaders(): HeadersInit {
    return {
      ...this.headers(),
      'X-Request-Nonce': crypto.randomUUID(),
      'X-Request-Timestamp': Math.floor(Date.now() / 1000).toString(),
    };
  }

  // --- Auth ---
  async login(email: string, password: string) {
    const res = await fetch(`${BASE_URL}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    const data = await res.json();
    if (res.ok) this.setAuth(data.access_token, data.api_key);
    return data;
  }

  // --- Payments ---
  async createPayment(params: {
    amount: number;
    currency?: string;
    order_id?: string;
    payer_country?: string;
    payer_currency?: string;
    success_url: string;
    cancel_url: string;
    metadata?: Record<string, any>;
  }) {
    return this.post('/api/sessions/create', params, {
      'X-API-Key': this.apiKey!,
      'Idempotency-Key': `pay-${params.order_id || Date.now()}`,
      'X-Request-Nonce': crypto.randomUUID(),
      'X-Request-Timestamp': Math.floor(Date.now() / 1000).toString(),
    });
  }

  async getPaymentStatus(sessionId: string) {
    return this.get(`/api/sessions/${sessionId}/status`);
  }

  // --- Payment Links ---
  async createPaymentLink(params: any) {
    return this.post('/payment-links', params);
  }

  async listPaymentLinks(skip = 0, limit = 20) {
    return this.get(`/payment-links?skip=${skip}&limit=${limit}`);
  }

  // --- Invoices ---
  async createInvoice(params: any) {
    return this.post('/invoices', params, {
      'Idempotency-Key': `inv-${Date.now()}`,
    });
  }

  async sendInvoice(invoiceId: string) {
    return this.post(`/invoices/${invoiceId}/send`, {});
  }

  // --- Subscriptions ---
  async createPlan(params: any) {
    return this.post('/subscriptions/plans', params);
  }

  async createSubscription(planId: string, email: string) {
    return this.post('/subscriptions', { plan_id: planId, customer_email: email });
  }

  // --- Refunds ---
  async checkRefundEligibility(sessionId: string) {
    return this.get(`/refunds/eligibility/${sessionId}`);
  }

  async createRefund(sessionId: string, amount?: number, reason?: string) {
    return this.post('/refunds', {
      payment_session_id: sessionId,
      amount,
      reason,
    }, {
      'Idempotency-Key': `refund-${sessionId}-${Date.now()}`,
    });
  }

  // --- Analytics ---
  async getOverview(period = 'month') {
    return this.get(`/analytics/overview?period=${period}`);
  }

  // --- Wallets ---
  async getWalletDashboard() {
    return this.get('/merchant/wallets/dashboard');
  }

  // --- Coupons ---
  async createCoupon(params: any) {
    return this.post('/api/business/promo/create', params);
  }

  // --- Internal helpers ---
  private async get(path: string) {
    const res = await fetch(`${BASE_URL}${path}`, { headers: this.headers() });
    if (!res.ok) throw new DariApiError(res.status, await res.json());
    return res.json();
  }

  private async post(path: string, body: any, extraHeaders: HeadersInit = {}) {
    const res = await fetch(`${BASE_URL}${path}`, {
      method: 'POST',
      headers: { ...this.headers(), ...extraHeaders },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new DariApiError(res.status, await res.json());
    return res.json();
  }
}

class DariApiError extends Error {
  constructor(public status: number, public body: any) {
    super(body?.detail || `API error ${status}`);
  }
}

export const dari = new DariClient();
```

---

## 19. Error Handling Reference

### HTTP Status Codes

| Code | Meaning | Handle |
|------|---------|--------|
| `200` | Success | Process response |
| `201` | Created | Resource created |
| `400` | Bad Request | Show validation errors |
| `401` | Unauthorized | Redirect to login |
| `403` | Forbidden | Show "account disabled" |
| `404` | Not Found | Show "not found" |
| `409` | Conflict | Idempotency duplicate — don't retry |
| `422` | Validation Error | Show field-level errors |
| `429` | Rate Limited | Back off, retry after delay |
| `500` | Server Error | Show generic error, retry |

### Error Response Shape

```typescript
interface DariError {
  detail: string | ValidationError[];
}

interface ValidationError {
  loc: (string | number)[];
  msg: string;
  type: string;
}
```

### React Error Handler

```typescript
const handleApiError = (error: DariApiError) => {
  switch (error.status) {
    case 401:
      localStorage.removeItem('token');
      window.location.href = '/login';
      break;
    case 409:
      // Duplicate request — safe to ignore
      console.warn('Duplicate request, using cached response');
      break;
    case 429:
      toast.error('Too many requests. Please wait a moment.');
      break;
    case 422:
      // Validation errors — display per-field
      const errors = Array.isArray(error.body.detail) ? error.body.detail : [];
      errors.forEach((e) => toast.error(`${e.loc.join('.')}: ${e.msg}`));
      break;
    default:
      toast.error(error.body?.detail || 'Something went wrong');
  }
};
```

---

## 20. TypeScript Type Definitions

```typescript
// types/dari.ts

// === Enums ===
type Chain = 'stellar' | 'ethereum' | 'polygon' | 'base' | 'tron' | 'solana';
type Token = 'USDC' | 'USDT' | 'PYUSD';
type PaymentStatus = 'created' | 'pending' | 'processing' | 'confirmed' | 'paid'
  | 'expired' | 'failed' | 'refunded' | 'partially_refunded';
type InvoiceStatus = 'draft' | 'sent' | 'paid' | 'overdue' | 'cancelled';
type SubscriptionStatus = 'trialing' | 'active' | 'paused' | 'past_due' | 'cancelled';
type RefundStatus = 'pending' | 'completed' | 'failed' | 'queued' | 'cancelled';

// === Auth ===
interface AuthResponse {
  access_token: string;
  token_type: string;
  api_key: string;
  onboarding_completed: boolean;
  onboarding_step: number;
}

// === Payment Session ===
interface CreatePaymentRequest {
  amount: number;
  currency?: string;
  accepted_tokens?: Token[];
  accepted_chains?: Chain[];
  order_id?: string;
  success_url?: string;
  cancel_url?: string;
  metadata?: Record<string, any>;
  collect_payer_data?: boolean;
  payer_currency?: string;
  payer_country?: string;
}

interface PaymentSessionResponse {
  session_id: string;
  checkout_url: string;
  amount: number;
  currency: string;
  accepted_tokens: Token[];
  accepted_chains: Chain[];
  order_id?: string;
  expires_at: string;
  status: PaymentStatus;
  payment_token?: string;
  is_tokenized: boolean;
  payer_currency?: string;
  payer_amount_local?: number;
  merchant_currency?: string;
  merchant_amount_local?: number;
  is_cross_border: boolean;
}

interface PaymentOption {
  token: Token;
  chain: Chain;
  chain_display: string;
  wallet_address: string;
  amount: string;
  label: string;
  icon_url?: string;
  memo?: string;
}

// === Payment Link ===
interface PaymentLink {
  id: string;
  short_code: string;
  name: string;
  description?: string;
  amount_fiat?: number;
  fiat_currency: string;
  is_amount_fixed: boolean;
  url: string;
  is_active: boolean;
  single_use: boolean;
  created_at: string;
  expires_at?: string;
}

// === Invoice ===
interface Invoice {
  id: string;
  customer_name: string;
  customer_email: string;
  amount: number;
  currency: string;
  status: InvoiceStatus;
  due_date?: string;
  items: InvoiceItem[];
  created_at: string;
  paid_at?: string;
}

interface InvoiceItem {
  description: string;
  quantity: number;
  unit_price: number;
  total: number;
}

// === Subscription ===
interface SubscriptionPlan {
  id: string;
  name: string;
  description?: string;
  amount: number;
  currency: string;
  interval: 'daily' | 'weekly' | 'monthly' | 'quarterly' | 'yearly';
  trial_days?: number;
  is_active: boolean;
}

interface Subscription {
  id: string;
  plan_id: string;
  customer_email: string;
  status: SubscriptionStatus;
  current_period_start: string;
  current_period_end: string;
  next_payment_date?: string;
  trial_ends_at?: string;
}

// === Refund ===
interface Refund {
  id: string;
  payment_session_id: string;
  amount: number;
  token: string;
  chain: string;
  status: RefundStatus;
  reason?: string;
  created_at: string;
  completed_at?: string;
}

// === Wallet ===
interface MerchantWallet {
  id: string;
  chain: Chain;
  wallet_address: string;
  is_active: boolean;
  created_at: string;
}

interface WalletBalance {
  chain: Chain;
  address: string;
  balances: Record<Token, string>;
  balances_local?: Record<Token, LocalCurrencyAmount>;
}

interface LocalCurrencyAmount {
  amount_usdc: number;
  amount_local: number;
  local_currency: string;
  local_symbol: string;
  exchange_rate: number;
  display_local: string;
}

// === Analytics ===
interface AnalyticsOverview {
  period_start: string;
  period_end: string;
  period: string;
  payments: {
    total_payments: number;
    successful_payments: number;
    failed_payments: number;
    total_volume: number;
    avg_payment: number;
    conversion_rate: number;
  };
  volume_by_token: Array<{ token: Token; volume: number; count: number; percentage: number }>;
  volume_by_chain: Array<{ chain: Chain; volume: number; count: number; percentage: number }>;
  invoices_sent: number;
  invoices_paid: number;
  active_subscriptions: number;
  subscription_mrr: number;
  payments_change_pct: number;
  volume_change_pct: number;
  currency: string;
  currency_symbol: string;
}

// === Webhook ===
interface WebhookEvent {
  event: 'payment.succeeded' | 'payment.failed' | 'payment.expired';
  session_id: string;
  amount: string;
  currency: string;
  token?: string;
  chain?: string;
  tx_hash?: string;
  block_number?: number;
  confirmations?: number;
  status: string;
  timestamp: string;
  payer_currency?: string;
  payer_amount_local?: number;
  merchant_currency?: string;
  merchant_amount_local?: number;
  is_cross_border: boolean;
}

// === Coupon ===
interface Coupon {
  id: string;
  code: string;
  discount_type: 'percentage' | 'fixed';
  discount_value: number;
  max_discount?: number;
  min_order_amount?: number;
  max_uses?: number;
  max_uses_per_user?: number;
  is_active: boolean;
  expires_at?: string;
  total_uses: number;
}

interface CouponApplyResult {
  valid: boolean;
  discount_amount: number;
  original_amount: number;
  final_amount: number;
  discount_label: string;
}
```

---

## Quick Reference: Required Headers by Endpoint

| Endpoint | Auth Header | Idempotency-Key | Nonce + Timestamp |
|----------|:-----------:|:---------------:|:-----------------:|
| `POST /auth/register` | — | — | — |
| `POST /auth/login` | — | — | — |
| `POST /api/sessions/create` | `X-API-Key` | ✅ Recommended | ✅ Recommended |
| `GET /api/sessions/{id}/status` | — | — | — |
| `POST /payment-links` | `Bearer` | Optional | Optional |
| `POST /invoices` | `Bearer` | ✅ Recommended | Optional |
| `POST /subscriptions` | `Bearer` | ✅ Recommended | Optional |
| `POST /refunds` | `Bearer` | ✅ Recommended | ✅ Recommended |
| `POST /withdrawals` | `Bearer` | ✅ Recommended | ✅ Recommended |
| `GET /analytics/*` | `Bearer` | — | — |
| `GET /merchant/wallets/dashboard` | `Bearer` | — | — |

---

## Rate Limits

| Scope | Limit | Window |
|-------|-------|--------|
| Global (per IP) | 120 requests | 1 minute |
| Coupon apply endpoint | 10 requests | 1 minute |

When rate limited, you'll receive a `429 Too Many Requests` response. Back off and retry after the window resets.
