# Local Currency & Balance Dashboard

All monetary values in ChainPe are stored internally in stablecoins (USDC, USDT, PYUSD ≈ 1 USD each). To make the dashboard friendly for merchants worldwide, every API response that contains a monetary amount **also returns the equivalent in the merchant's local currency** based on their country (set during onboarding).

---

## How It Works

```
┌──────────────┐      ┌──────────────────┐      ┌────────────────────┐
│  Merchant DB │─────▶│  Country → Code  │─────▶│  Exchange Rate API │
│  country: IN │      │  India → INR, ₹  │      │  1 USD = 83.12 INR │
└──────────────┘      └──────────────────┘      └────────────────────┘
                                                         │
                                                         ▼
                                               ┌────────────────────┐
                                               │  Dual-currency     │
                                               │  response returned │
                                               └────────────────────┘
```

1. **Country mapping** – `app/services/currency_service.py` maps 100+ countries to their currency code, symbol, and name.
2. **Exchange rates** – Uses the existing `PriceService` (`app/services/price_service.py`) which fetches live rates from [exchangerate-api.com](https://api.exchangerate-api.com) with a 60-second in-memory cache.
3. **Dual output** – Every monetary field gets a companion `*_local` field containing the `LocalCurrencyAmount` object.

---

## `LocalCurrencyAmount` Schema

Every `*_local` field in the API uses this structure:

```json
{
  "amount_usdc": 50.0,
  "amount_local": 4156.00,
  "local_currency": "INR",
  "local_symbol": "₹",
  "exchange_rate": 83.12,
  "display_local": "₹4,156.00"
}
```

| Field            | Type   | Description                                      |
|------------------|--------|--------------------------------------------------|
| `amount_usdc`    | float  | Original amount in USDC / USD                    |
| `amount_local`   | float  | Converted amount in local currency               |
| `local_currency` | string | ISO 4217 currency code (INR, NGN, EUR …)         |
| `local_symbol`   | string | Currency symbol (₹, ₦, € …)                     |
| `exchange_rate`  | float  | Rate used: 1 USDC ≈ X local                      |
| `display_local`  | string | Pre-formatted display string (e.g. `₹4,156.00`)  |

---

## Supported Countries

Over 100 countries are mapped. Some examples:

| Country         | Code | Symbol | Currency Name           |
|-----------------|------|--------|-------------------------|
| India           | INR  | ₹      | Indian Rupee            |
| United States   | USD  | $      | US Dollar               |
| United Kingdom  | GBP  | £      | British Pound           |
| Germany/France  | EUR  | €      | Euro                    |
| Nigeria         | NGN  | ₦      | Nigerian Naira          |
| Japan           | JPY  | ¥      | Japanese Yen            |
| Brazil          | BRL  | R$     | Brazilian Real          |
| UAE             | AED  | د.إ    | UAE Dirham              |
| South Africa    | ZAR  | R      | South African Rand      |
| Australia       | AUD  | A$     | Australian Dollar       |
| Canada          | CAD  | C$     | Canadian Dollar         |
| Turkey          | TRY  | ₺      | Turkish Lira            |
| South Korea     | KRW  | ₩      | South Korean Won        |

If a country is not found, it **falls back to USD**.

---

## API Endpoints with Local Currency

### 1. Balance Dashboard (NEW)

```
GET /merchant/wallets/dashboard
Authorization: Bearer <token> / X-API-Key
```

**The single endpoint to show the complete balance overview.**

Response:
```json
{
  "total_balance_usdc": 1250.50,
  "total_balance_local": {
    "amount_usdc": 1250.50,
    "amount_local": 103916.56,
    "local_currency": "INR",
    "local_symbol": "₹",
    "exchange_rate": 83.10,
    "display_local": "₹1,03,916.56"
  },
  "local_currency": "INR",
  "local_symbol": "₹",
  "exchange_rate": 83.10,
  "coins": [
    {
      "token": "USDC",
      "balance_usdc": 800.00,
      "balance_local": {
        "amount_usdc": 800.00,
        "amount_local": 66480.00,
        "local_currency": "INR",
        "local_symbol": "₹",
        "exchange_rate": 83.10,
        "display_local": "₹66,480.00"
      }
    },
    {
      "token": "USDT",
      "balance_usdc": 400.50,
      "balance_local": { "..." : "..." }
    },
    {
      "token": "PYUSD",
      "balance_usdc": 50.00,
      "balance_local": { "..." : "..." }
    }
  ],
  "wallets": [
    { "chain": "polygon", "wallet_address": "0xabc...def", "is_active": true },
    { "chain": "stellar", "wallet_address": "GABC...XYZ", "is_active": true },
    { "chain": "ethereum", "wallet_address": "0x123...456", "is_active": false }
  ],
  "pending_withdrawals_usdc": 50.00,
  "pending_withdrawals_local": {
    "amount_usdc": 50.00,
    "amount_local": 4155.00,
    "local_currency": "INR",
    "local_symbol": "₹",
    "exchange_rate": 83.10,
    "display_local": "₹4,155.00"
  },
  "net_available_usdc": 1200.50,
  "net_available_local": {
    "amount_usdc": 1200.50,
    "amount_local": 99761.55,
    "local_currency": "INR",
    "local_symbol": "₹",
    "exchange_rate": 83.10,
    "display_local": "₹99,761.55"
  }
}
```

---

### 2. Withdrawal Balance

```
GET /withdrawals/balance
```

Per-token available and net-available with local currency:

```json
{
  "balances": [
    {
      "token": "USDC",
      "available": 800.0,
      "pending_withdrawals": 50.0,
      "net_available": 750.0,
      "available_local": { "amount_usdc": 800.0, "amount_local": 66480.0, "..." : "..." },
      "net_available_local": { "amount_usdc": 750.0, "amount_local": 62325.0, "..." : "..." }
    }
  ],
  "total_available_usd": 1200.5,
  "total_available_local": { "..." : "..." },
  "local_currency": "INR",
  "local_symbol": "₹"
}
```

---

### 3. Withdrawal Details

```
GET /withdrawals
GET /withdrawals/{id}
POST /withdrawals
POST /withdrawals/{id}/cancel
```

Every withdrawal response now includes:
```json
{
  "amount": 50.0,
  "token": "USDC",
  "amount_local": {
    "amount_usdc": 50.0,
    "amount_local": 4155.0,
    "local_currency": "INR",
    "local_symbol": "₹",
    "exchange_rate": 83.10,
    "display_local": "₹4,155.00"
  },
  "fee_local": {
    "amount_usdc": 0.75,
    "amount_local": 62.33,
    "local_currency": "INR",
    "local_symbol": "₹",
    "exchange_rate": 83.10,
    "display_local": "₹62.33"
  }
}
```

---

### 4. Withdrawal Limits

```
GET /withdrawals/limits
```

```json
{
  "tier": "growth",
  "daily_limit": 5000.0,
  "daily_limit_local": { "amount_usdc": 5000.0, "amount_local": 415500.0, "display_local": "₹4,15,500.00", "..." : "..." },
  "daily_used": 200.0,
  "daily_used_local": { "..." : "..." },
  "daily_remaining": 4800.0,
  "daily_remaining_local": { "..." : "..." }
}
```

---

### 5. Subscription / Billing

```
GET /subscription/current   (or GET /billing/info)
GET /subscription/usage     (or GET /billing/usage)
```

```json
{
  "tier": "growth",
  "monthly_price": 29.0,
  "monthly_price_local": { "amount_usdc": 29.0, "amount_local": 2409.90, "display_local": "₹2,409.90", "..." : "..." },
  "current_volume": 12500.0,
  "current_volume_local": { "..." : "..." },
  "monthly_volume_limit": 50000.0,
  "volume_limit_local": { "..." : "..." }
}
```

---

## Frontend Integration

### React Example

```tsx
import { useEffect, useState } from 'react';

interface LocalAmount {
  amount_usdc: number;
  amount_local: number;
  local_currency: string;
  local_symbol: string;
  exchange_rate: number;
  display_local: string;
}

interface BalanceDashboard {
  total_balance_usdc: number;
  total_balance_local: LocalAmount;
  local_currency: string;
  local_symbol: string;
  exchange_rate: number;
  coins: { token: string; balance_usdc: number; balance_local: LocalAmount }[];
  wallets: { chain: string; wallet_address: string; is_active: boolean }[];
  pending_withdrawals_usdc: number;
  pending_withdrawals_local: LocalAmount;
  net_available_usdc: number;
  net_available_local: LocalAmount;
}

function BalanceCard() {
  const [dashboard, setDashboard] = useState<BalanceDashboard | null>(null);

  useEffect(() => {
    fetch('/merchant/wallets/dashboard', {
      headers: { 'X-API-Key': 'pk_live_...' },
    })
      .then(r => r.json())
      .then(setDashboard);
  }, []);

  if (!dashboard) return <div>Loading…</div>;

  return (
    <div>
      {/* Total balance in local currency (primary) */}
      <h1>{dashboard.total_balance_local.display_local}</h1>
      <p className="text-muted">
        ≈ ${dashboard.total_balance_usdc.toFixed(2)} USDC
      </p>

      {/* Per-coin breakdown */}
      <h3>Breakdown</h3>
      {dashboard.coins.map(coin => (
        <div key={coin.token}>
          <span>{coin.token}</span>
          <span>{coin.balance_local.display_local}</span>
          <span className="text-muted">(${coin.balance_usdc.toFixed(2)})</span>
        </div>
      ))}

      {/* Pending */}
      <p>
        Pending: {dashboard.pending_withdrawals_local.display_local}
        {' '}| Net: {dashboard.net_available_local.display_local}
      </p>

      {/* Wallets */}
      <h3>Wallets</h3>
      {dashboard.wallets.filter(w => w.is_active).map(w => (
        <div key={w.chain}>
          {w.chain}: {w.wallet_address.slice(0, 8)}…{w.wallet_address.slice(-6)}
        </div>
      ))}
    </div>
  );
}
```

---

## How Country Is Set

The merchant's country is saved during onboarding step 1 (`POST /onboarding/business-details`):

```json
{
  "business_name": "Acme Corp",
  "business_email": "admin@acme.in",
  "country": "India",
  "merchant_category": "startup"
}
```

The `country` string is stored in `merchants.country` and used by the currency service for the lifetime of the account. If the country is `null` or unrecognized, all local amounts default to USD.

---

## Exchange Rate Details

| Aspect              | Detail                                              |
|---------------------|-----------------------------------------------------|
| Source              | [exchangerate-api.com](https://api.exchangerate-api.com) (free tier) |
| Cache TTL           | 60 seconds in-memory                                |
| Fallback            | If API is unreachable, falls back to 1:1 (USD)      |
| Stablecoin assumption | USDC ≈ USDT ≈ PYUSD ≈ 1 USD                      |
| Precision           | 2 decimal places (0 for JPY, KRW)                   |

---

## Files

| File | Purpose |
|------|---------|
| `app/services/currency_service.py` | Country→currency mapping, conversion helpers |
| `app/services/price_service.py` | Exchange rate fetching + cache |
| `app/schemas/schemas.py` | `LocalCurrencyAmount`, `CoinBalance`, `WalletBalance`, `BalanceDashboardResponse` |
| `app/routes/wallets.py` | `GET /merchant/wallets/dashboard` |
| `app/routes/withdrawals.py` | All withdrawal endpoints with `*_local` fields |
| `app/routes/subscription_management.py` | Subscription endpoints with `*_local` fields |
| `app/routes/billing.py` | Billing aliases (inherits local currency from subscription routes) |
