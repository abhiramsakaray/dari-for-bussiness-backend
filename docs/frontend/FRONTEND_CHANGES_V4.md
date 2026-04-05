# Frontend Changes — V4 (Local Currency + Coupon Breakdown)

All merchant-facing API responses now include **local currency amounts** (based on the merchant's country) and **coupon breakdown fields**. This guide covers every change your frontend needs to handle.

---

## Summary of Changes

| Area | What Changed |
|------|-------------|
| Transaction List | New `coupon_code`, `discount_amount`, `amount_paid` fields |
| Transaction List | New `amount_fiat_local`, `discount_amount_local`, `amount_paid_local` objects |
| Payment Stats | New `total_coupon_discount`, `coupon_payment_count`, `total_local`, `total_coupon_discount_local` in revenue |
| Billing/Subscription | Already had `monthly_price_local`, `current_volume_local`, `volume_limit_local` — no changes |

---

## 1. New Type: `LocalCurrencyAmount`

Every `*_local` field uses this shape. Display `display_local` directly — it's pre-formatted with the currency symbol and commas.

```ts
interface LocalCurrencyAmount {
  amount_usdc: number;    // Original USD amount
  amount_local: number;   // Converted local amount (raw number)
  local_currency: string; // ISO code, e.g. "INR", "NGN", "BRL"
  local_symbol: string;   // Symbol, e.g. "₹", "₦", "R$"
  exchange_rate: number;  // 1 USD = X local
  display_local: string;  // Pre-formatted, e.g. "₹9,187.00"
}
```

**Important:** For merchants in USD countries, all `*_local` fields are `null`. Only show local currency when the field is present.

---

## 2. Updated Transaction List Item

**Endpoints affected:**
- `GET /merchant/payments`
- `GET /merchant/payments/recent`
- `GET /merchant/payments/payer-leads`

### New fields in each transaction item:

```ts
interface PaymentListItem {
  // ... existing fields ...
  id: string;
  merchant_id: string;
  merchant_name: string;
  amount_fiat: number;       // Original order amount (USD)
  fiat_currency: string;
  token: string | null;
  chain: string | null;
  status: string;            // "created" | "paid" | "expired"
  tx_hash: string | null;
  created_at: string;
  paid_at: string | null;
  expires_at: string | null;
  payer_email: string | null;
  payer_name: string | null;
  amount_usdc: string | null;

  // ── NEW: Coupon breakdown ──
  coupon_code: string | null;         // Coupon applied (null if none)
  discount_amount: number | null;     // Discount in USD
  amount_paid: number | null;         // amount_fiat - discount_amount

  // ── NEW: Local currency conversions ──
  amount_fiat_local: LocalCurrencyAmount | null;      // Order amount in local currency
  discount_amount_local: LocalCurrencyAmount | null;   // Discount in local currency
  amount_paid_local: LocalCurrencyAmount | null;       // Amount paid in local currency
}
```

### Example response — transaction WITH coupon (Indian merchant):

```json
{
  "id": "pay_abc123",
  "amount_fiat": 100.00,
  "fiat_currency": "USD",
  "status": "paid",
  "coupon_code": "SAVE50",
  "discount_amount": 50.00,
  "amount_paid": 50.00,
  "amount_fiat_local": {
    "amount_usdc": 100.0,
    "amount_local": 8475.0,
    "local_currency": "INR",
    "local_symbol": "₹",
    "exchange_rate": 84.75,
    "display_local": "₹8,475.00"
  },
  "discount_amount_local": {
    "amount_usdc": 50.0,
    "amount_local": 4237.5,
    "local_currency": "INR",
    "local_symbol": "₹",
    "exchange_rate": 84.75,
    "display_local": "₹4,237.50"
  },
  "amount_paid_local": {
    "amount_usdc": 50.0,
    "amount_local": 4237.5,
    "local_currency": "INR",
    "local_symbol": "₹",
    "exchange_rate": 84.75,
    "display_local": "₹4,237.50"
  }
}
```

### Example response — transaction WITHOUT coupon (Indian merchant):

```json
{
  "id": "pay_xyz456",
  "amount_fiat": 75.00,
  "fiat_currency": "USD",
  "status": "paid",
  "coupon_code": null,
  "discount_amount": null,
  "amount_paid": null,
  "amount_fiat_local": {
    "amount_usdc": 75.0,
    "amount_local": 6356.25,
    "local_currency": "INR",
    "local_symbol": "₹",
    "exchange_rate": 84.75,
    "display_local": "₹6,356.25"
  },
  "discount_amount_local": null,
  "amount_paid_local": null
}
```

### Example response — USD merchant (no local conversion):

```json
{
  "id": "pay_us001",
  "amount_fiat": 200.00,
  "fiat_currency": "USD",
  "coupon_code": "WELCOME10",
  "discount_amount": 20.00,
  "amount_paid": 180.00,
  "amount_fiat_local": null,
  "discount_amount_local": null,
  "amount_paid_local": null
}
```

---

## 3. Updated Payment Stats

**Endpoint:** `GET /merchant/payments/stats`

### New fields in `revenue` object:

```ts
interface PaymentStats {
  total_sessions: number;
  sessions_by_status: {
    paid: number;
    pending: number;
    expired: number;
  };
  revenue: {
    total_usdc: number;
    currency: "USDC";

    // ── NEW: Coupon stats ──
    total_coupon_discount: number;    // Total discount given via coupons (USD)
    coupon_payment_count: number;     // Number of payments that used a coupon

    // ── NEW: Local currency ──
    total_local: LocalCurrencyAmount | null;                 // Total revenue in local currency
    total_coupon_discount_local: LocalCurrencyAmount | null;  // Total discount in local currency
  };
  recent: {
    today: number;
    this_week: number;
  };
  success_rate: number;
}
```

### Example response (Indian merchant):

```json
{
  "total_sessions": 150,
  "sessions_by_status": { "paid": 120, "pending": 10, "expired": 20 },
  "revenue": {
    "total_usdc": 5000.00,
    "currency": "USDC",
    "total_coupon_discount": 350.00,
    "coupon_payment_count": 12,
    "total_local": {
      "amount_usdc": 5000.0,
      "amount_local": 423750.0,
      "local_currency": "INR",
      "local_symbol": "₹",
      "exchange_rate": 84.75,
      "display_local": "₹4,23,750.00"
    },
    "total_coupon_discount_local": {
      "amount_usdc": 350.0,
      "amount_local": 29662.5,
      "local_currency": "INR",
      "local_symbol": "₹",
      "exchange_rate": 84.75,
      "display_local": "₹29,662.50"
    }
  },
  "recent": { "today": 5, "this_week": 35 },
  "success_rate": 80.0
}
```

---

## 4. Frontend Display Logic

### 4.1 Showing amounts — prefer local currency

```tsx
function displayAmount(
  amountUsd: number,
  localAmount: LocalCurrencyAmount | null
): string {
  if (localAmount) {
    return localAmount.display_local;  // "₹8,475.00"
  }
  return `$${amountUsd.toFixed(2)}`;    // "$100.00" (USD merchants)
}
```

### 4.2 Transaction row with coupon breakdown

```tsx
function TransactionRow({ tx }: { tx: PaymentListItem }) {
  const hasDiscount = tx.coupon_code !== null;

  return (
    <tr>
      <td>{tx.id}</td>
      <td>{tx.status}</td>
      <td>
        {/* Main amount */}
        {displayAmount(tx.amount_fiat, tx.amount_fiat_local)}

        {/* Coupon breakdown */}
        {hasDiscount && (
          <div className="text-sm text-gray-500">
            <span className="text-green-600">
              -{displayAmount(tx.discount_amount!, tx.discount_amount_local)}
            </span>
            {' '}({tx.coupon_code})
            <br />
            Paid: {displayAmount(tx.amount_paid!, tx.amount_paid_local)}
          </div>
        )}
      </td>
      <td>{new Date(tx.created_at).toLocaleDateString()}</td>
    </tr>
  );
}
```

### 4.3 Stats dashboard with local revenue

```tsx
function RevenueSummary({ stats }: { stats: PaymentStats }) {
  const { revenue } = stats;

  // Show local currency if available, else USD
  const totalDisplay = revenue.total_local
    ? revenue.total_local.display_local
    : `$${revenue.total_usdc.toFixed(2)}`;

  const discountDisplay = revenue.total_coupon_discount_local
    ? revenue.total_coupon_discount_local.display_local
    : `$${revenue.total_coupon_discount.toFixed(2)}`;

  return (
    <div className="stats-grid">
      <div className="stat-card">
        <div className="stat-label">Total Revenue</div>
        <div className="stat-value">{totalDisplay}</div>
        {revenue.total_local && (
          <div className="stat-sub">${revenue.total_usdc.toFixed(2)} USDC</div>
        )}
      </div>

      {revenue.coupon_payment_count > 0 && (
        <div className="stat-card">
          <div className="stat-label">Coupon Discounts</div>
          <div className="stat-value">{discountDisplay}</div>
          <div className="stat-sub">{revenue.coupon_payment_count} payments</div>
        </div>
      )}
    </div>
  );
}
```

### 4.4 Showing both currencies (dual display)

If you want to show both the local and USD amounts:

```tsx
function DualAmount({
  usd,
  local,
}: {
  usd: number;
  local: LocalCurrencyAmount | null;
}) {
  if (!local) return <span>${usd.toFixed(2)}</span>;

  return (
    <div>
      <span className="text-lg font-semibold">{local.display_local}</span>
      <span className="text-sm text-gray-400 ml-2">(${usd.toFixed(2)})</span>
    </div>
  );
}
```

---

## 5. Billing & Subscription (No Changes)

These endpoints already return local currency. No frontend changes needed if you're already using them:

- `GET /billing/info` → `SubscriptionResponse` has `monthly_price_local`, `current_volume_local`, `volume_limit_local`
- `GET /billing/usage` → `SubscriptionUsageResponse` has `current_volume_local`, `volume_limit_local`

---

## 6. Updated TypeScript Types

Add these types to your project:

```ts
// ── LocalCurrencyAmount ──

interface LocalCurrencyAmount {
  amount_usdc: number;
  amount_local: number;
  local_currency: string;
  local_symbol: string;
  exchange_rate: number;
  display_local: string;
}

// ── Updated PaymentListItem ──

interface PaymentListItem {
  id: string;
  merchant_id: string;
  merchant_name: string;
  amount_fiat: number;
  fiat_currency: string;
  token: string | null;
  chain: string | null;
  status: 'created' | 'paid' | 'expired';
  tx_hash: string | null;
  created_at: string;
  paid_at: string | null;
  expires_at: string | null;
  payer_email: string | null;
  payer_name: string | null;
  amount_usdc: string | null;

  // Coupon
  coupon_code: string | null;
  discount_amount: number | null;
  amount_paid: number | null;

  // Local currency
  amount_fiat_local: LocalCurrencyAmount | null;
  discount_amount_local: LocalCurrencyAmount | null;
  amount_paid_local: LocalCurrencyAmount | null;
}

// ── Updated PaymentStats ──

interface PaymentStats {
  total_sessions: number;
  sessions_by_status: {
    paid: number;
    pending: number;
    expired: number;
  };
  revenue: {
    total_usdc: number;
    currency: 'USDC';
    total_coupon_discount: number;
    coupon_payment_count: number;
    total_local: LocalCurrencyAmount | null;
    total_coupon_discount_local: LocalCurrencyAmount | null;
  };
  recent: {
    today: number;
    this_week: number;
  };
  success_rate: number;
}
```

---

## 7. Migration Checklist

- [ ] Add `LocalCurrencyAmount` type to your types file
- [ ] Update `PaymentListItem` type with coupon + local currency fields
- [ ] Update `PaymentStats` type with new revenue fields
- [ ] Update transaction list table/cards to show local amounts using `display_local`
- [ ] Add coupon breakdown display (discount line + coupon code badge)
- [ ] Update stats dashboard to show revenue in local currency
- [ ] Show USD as secondary when local currency is present
- [ ] Handle `null` local fields gracefully (USD merchants get `null`)
- [ ] No changes needed for billing/subscription pages (already local-aware)
