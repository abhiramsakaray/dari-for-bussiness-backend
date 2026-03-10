# Frontend Changes V6 — Live On-Chain Wallet Balances

## What Changed

The `GET /merchant/wallets/dashboard` endpoint now returns **live on-chain balances** fetched directly from blockchain RPCs instead of database-stored values. This means balances always reflect the real funds sitting in the merchant's wallets — no sync lag, no stale data.

### Why

Previously balances were tracked in `merchants.balance_usdc / balance_usdt / balance_pyusd` DB columns that were only updated when the backend processed a payment. If a merchant received funds externally (direct transfer, airdrop, manual deposit), those balances never showed up. Now every dashboard load queries the actual chain.

---

## API Changes

### Endpoint (unchanged)

```
GET /merchant/wallets/dashboard
Authorization: Bearer <token> / X-API-Key
```

### New Fields

| Field | Type | Description |
|-------|------|-------------|
| `balance_source` | `"onchain" \| "database"` | Where balances came from. `"onchain"` = live RPC. `"database"` = fallback if all RPCs failed. |
| `coins[].chain_balances` | `ChainTokenBalance[] \| null` | Per-chain breakdown for each token. Only present when `balance_source` is `"onchain"`. |

### New Schema: `ChainTokenBalance`

```typescript
interface ChainTokenBalance {
  chain: string;           // "stellar", "ethereum", "polygon", "base", "tron"
  token: string;           // "USDC", "USDT", "PYUSD"
  balance: number;         // Raw token amount on that specific chain
  wallet_address: string;  // The wallet address holding this balance
}
```

### Full Updated Response

```json
{
  "total_balance_usdc": 1250.50,
  "total_balance_local": {
    "amount_usdc": 1250.50,
    "amount_local": 115359.00,
    "local_currency": "INR",
    "local_symbol": "₹",
    "exchange_rate": 92.25,
    "display_local": "₹1,15,359.00"
  },
  "local_currency": "INR",
  "local_symbol": "₹",
  "exchange_rate": 92.25,
  "coins": [
    {
      "token": "USDC",
      "balance_usdc": 1050.00,
      "balance_local": {
        "amount_usdc": 1050.00,
        "amount_local": 96862.50,
        "local_currency": "INR",
        "local_symbol": "₹",
        "exchange_rate": 92.25,
        "display_local": "₹96,862.50"
      },
      "chain_balances": [
        {
          "chain": "stellar",
          "token": "USDC",
          "balance": 500.00,
          "wallet_address": "GABC...XYZ"
        },
        {
          "chain": "polygon",
          "token": "USDC",
          "balance": 350.00,
          "wallet_address": "0xabc...def"
        },
        {
          "chain": "base",
          "token": "USDC",
          "balance": 200.00,
          "wallet_address": "0x123...789"
        }
      ]
    },
    {
      "token": "USDT",
      "balance_usdc": 200.50,
      "balance_local": { "...": "..." },
      "chain_balances": [
        {
          "chain": "ethereum",
          "token": "USDT",
          "balance": 200.50,
          "wallet_address": "0xeb6...bae"
        }
      ]
    },
    {
      "token": "PYUSD",
      "balance_usdc": 0.00,
      "balance_local": { "...": "..." },
      "chain_balances": []
    }
  ],
  "wallets": [
    { "chain": "stellar", "wallet_address": "GABC...XYZ", "is_active": true },
    { "chain": "polygon", "wallet_address": "0xabc...def", "is_active": true },
    { "chain": "ethereum", "wallet_address": "0xeb6...bae", "is_active": true },
    { "chain": "base", "wallet_address": "0x123...789", "is_active": true }
  ],
  "pending_withdrawals_usdc": 50.00,
  "pending_withdrawals_local": { "...": "..." },
  "net_available_usdc": 1200.50,
  "net_available_local": { "...": "..." },
  "balance_source": "onchain"
}
```

---

## Updated TypeScript Types

```typescript
interface LocalAmount {
  amount_usdc: number;
  amount_local: number;
  local_currency: string;
  local_symbol: string;
  exchange_rate: number;
  display_local: string;
}

interface ChainTokenBalance {
  chain: string;
  token: string;
  balance: number;
  wallet_address: string;
}

interface CoinBalance {
  token: string;
  balance_usdc: number;
  balance_local: LocalAmount | null;
  chain_balances: ChainTokenBalance[] | null;  // NEW
}

interface WalletInfo {
  chain: string;
  wallet_address: string;
  is_active: boolean;
}

interface BalanceDashboard {
  total_balance_usdc: number;
  total_balance_local: LocalAmount;
  local_currency: string;
  local_symbol: string;
  exchange_rate: number;
  coins: CoinBalance[];
  wallets: WalletInfo[];
  pending_withdrawals_usdc: number;
  pending_withdrawals_local: LocalAmount;
  net_available_usdc: number;
  net_available_local: LocalAmount;
  balance_source: "onchain" | "database";  // NEW
}
```

---

## Frontend Changes Required

### 1. Show Per-Chain Breakdown (New Feature)

Each coin now has an optional `chain_balances` array. Use it to show users exactly where their funds are:

```tsx
{dashboard.coins.map(coin => (
  <div key={coin.token} className="coin-card">
    <div className="coin-header">
      <span className="token-name">{coin.token}</span>
      <span className="token-total">{coin.balance_local?.display_local}</span>
      <span className="token-usdc">{coin.balance_usdc.toFixed(2)} {coin.token}</span>
    </div>

    {/* NEW: Per-chain breakdown */}
    {coin.chain_balances && coin.chain_balances.length > 0 && (
      <div className="chain-breakdown">
        {coin.chain_balances.map(cb => (
          <div key={`${cb.chain}-${cb.token}`} className="chain-row">
            <ChainIcon chain={cb.chain} />
            <span className="chain-name">{cb.chain}</span>
            <span className="chain-balance">
              {cb.balance.toFixed(2)} {cb.token}
            </span>
            <span className="chain-address" title={cb.wallet_address}>
              {cb.wallet_address.slice(0, 6)}…{cb.wallet_address.slice(-4)}
            </span>
          </div>
        ))}
      </div>
    )}
  </div>
))}
```

### 2. Show Balance Source Indicator

Let users know whether they're seeing live data or a fallback:

```tsx
<div className="balance-source">
  {dashboard.balance_source === 'onchain' ? (
    <span className="badge badge-green">🟢 Live</span>
  ) : (
    <span className="badge badge-yellow">⚠️ Cached</span>
  )}
</div>
```

### 3. Updated Assets Breakdown Section

Before (V5):
```
USDC
₹0.00
0 USDC
```

After (V6):
```
USDC                                    ₹96,862.50
  ⭐ Stellar     500.00 USDC   GABC...XYZ
  ⬡ Polygon     350.00 USDC   0xabc...def
  🔵 Base        200.00 USDC   0x123...789
─────────────────────────────────────
Total: 1,050.00 USDC

USDT                                    ₹18,496.13
  ⟠ Ethereum    200.50 USDT   0xeb6...bae
─────────────────────────────────────
Total: 200.50 USDT
```

---

## Full React Component Example

```tsx
import { useEffect, useState } from 'react';

const CHAIN_ICONS: Record<string, string> = {
  stellar: '⭐',
  ethereum: '⟠',
  polygon: '⬡',
  base: '🔵',
  tron: '🔷',
};

function WalletDashboard() {
  const [dashboard, setDashboard] = useState<BalanceDashboard | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchDashboard = async () => {
    setLoading(true);
    try {
      const res = await fetch('/merchant/wallets/dashboard', {
        headers: { 'X-API-Key': 'pk_live_...' },
      });
      const data = await res.json();
      setDashboard(data);
    } catch (err) {
      console.error('Failed to fetch dashboard', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchDashboard(); }, []);

  if (loading || !dashboard) return <div>Loading…</div>;

  return (
    <div className="wallet-dashboard">
      {/* Header */}
      <div className="dashboard-header">
        <h1>Wallets & Balances</h1>
        <p>Manage your funds and wallet addresses across all chains.</p>
        {dashboard.balance_source === 'onchain' 
          ? <span className="badge-live">🟢 Live</span>
          : <span className="badge-cached">⚠️ Cached</span>
        }
      </div>

      {/* Total Balance */}
      <div className="total-balance-card">
        <h2>Total Balance</h2>
        <div className="balance-primary">
          {dashboard.total_balance_local.display_local}
        </div>
        <div className="balance-secondary">
          ≈ ${dashboard.total_balance_usdc.toFixed(2)} USDC
        </div>
        <div className="exchange-rate">
          1 USD = {dashboard.exchange_rate.toFixed(2)} {dashboard.local_currency}
        </div>
      </div>

      {/* Available / Pending */}
      <div className="balance-summary">
        <div>
          <span>Available (Net)</span>
          <strong>{dashboard.net_available_local.display_local}</strong>
        </div>
        <div>
          <span>Pending Withdrawals</span>
          <strong>{dashboard.pending_withdrawals_local.display_local}</strong>
        </div>
      </div>

      {/* Assets Breakdown with Chain Detail */}
      <h3>Assets Breakdown</h3>
      {dashboard.coins.map(coin => (
        <div key={coin.token} className="asset-card">
          <div className="asset-header">
            <strong>{coin.token}</strong>
            <span>{coin.balance_local?.display_local ?? '₹0.00'}</span>
          </div>
          <div className="asset-usdc">
            {coin.balance_usdc.toFixed(2)} {coin.token}
          </div>

          {/* Per-chain rows (NEW in V6) */}
          {coin.chain_balances && coin.chain_balances.length > 0 && (
            <div className="chain-list">
              {coin.chain_balances
                .filter(cb => cb.balance > 0)
                .map(cb => (
                <div key={`${cb.chain}-${cb.token}`} className="chain-row">
                  <span className="chain-icon">
                    {CHAIN_ICONS[cb.chain] || '🔗'}
                  </span>
                  <span className="chain-name">
                    {cb.chain.charAt(0).toUpperCase() + cb.chain.slice(1)}
                  </span>
                  <span className="chain-bal">
                    {cb.balance.toFixed(2)} {cb.token}
                  </span>
                  <span className="chain-addr" title={cb.wallet_address}>
                    {cb.wallet_address.slice(0, 6)}…{cb.wallet_address.slice(-4)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      ))}

      {/* Deposit Addresses */}
      <h3>Deposit Addresses</h3>
      {dashboard.wallets.filter(w => w.is_active).map(w => (
        <div key={w.chain} className="wallet-card">
          <span>{CHAIN_ICONS[w.chain] || '🔗'}</span>
          <strong>{w.chain.charAt(0).toUpperCase() + w.chain.slice(1)}</strong>
          <code>{w.wallet_address}</code>
        </div>
      ))}

      <button onClick={fetchDashboard}>↻ Refresh Balances</button>
    </div>
  );
}

export default WalletDashboard;
```

---

## Migration Checklist

- [ ] Update `BalanceDashboard` TypeScript interface to add `balance_source` and `chain_balances`
- [ ] Render per-chain breakdown under each coin card (use `coin.chain_balances`)
- [ ] Add live/cached indicator using `dashboard.balance_source`
- [ ] Add a "Refresh Balances" button (re-calls the dashboard endpoint)
- [ ] Filter out zero-balance chains from the UI (`cb.balance > 0`)
- [ ] No other endpoints changed — withdrawals, payments, subscriptions are unaffected

---

## Backward Compatibility

| Field | Status |
|-------|--------|
| `total_balance_usdc` | No change |
| `total_balance_local` | No change |
| `coins[].token` | No change |
| `coins[].balance_usdc` | No change (now from chain instead of DB) |
| `coins[].balance_local` | No change |
| `coins[].chain_balances` | **NEW** — nullable, safe to ignore if not used |
| `wallets[]` | No change |
| `pending_withdrawals_*` | No change (still from DB) |
| `net_available_*` | No change |
| `balance_source` | **NEW** — defaults to `"onchain"` |

Existing frontend code will work without changes. The new fields (`chain_balances`, `balance_source`) are additive and optional to consume.

---

## Performance Notes

- On-chain RPC calls are made **in parallel** across all chains (typically completes in < 2 seconds)
- If all RPCs fail, the endpoint falls back to DB-stored balances and sets `balance_source: "database"`
- Consider adding a loading state / skeleton UI while the dashboard fetches, since RPC calls may take 1–2s vs the old instant DB read
- The endpoint does **not** cache results — each call hits the chain. Add client-side caching or polling interval (e.g. every 30s) to avoid excessive calls
