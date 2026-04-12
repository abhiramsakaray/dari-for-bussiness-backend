# Frontend Currency API Changes Guide

## Overview

The backend now provides **standardized currency handling** with pre-formatted strings, consistent exchange rates, and complete currency metadata. This eliminates the need for frontend currency formatting and conversions.

---

## What Changed

### Before (Old API Response)
```json
{
  "id": "pay_123",
  "amount_fiat": 10.00,
  "fiat_currency": "USD",
  "amount_usdc": "10.00",
  "status": "paid"
}
```

### After (New API Response)
```json
{
  "id": "pay_123",
  "amount": {
    "amount": 828.50,
    "currency": "INR",
    "symbol": "₹",
    "formatted": "₹828.50",
    "amount_usd": 10.00,
    "formatted_usd": "$10.00",
    "amount_crypto": 10.00,
    "crypto_token": "USDC",
    "crypto_chain": "polygon"
  },
  "status": "paid",
  "merchant_currency": {
    "currency": "INR",
    "symbol": "₹",
    "locale": "en_IN"
  }
}
```

---

## Key Benefits

✅ **No more frontend formatting** - Backend provides pre-formatted strings  
✅ **Consistent exchange rates** - All endpoints use same rates within 1-hour cache  
✅ **Merchant currency preference** - Amounts shown in merchant's preferred currency  
✅ **Complete metadata** - Currency code, symbol, and formatted display included  
✅ **USD reference** - Optional USD equivalent for cross-currency comparison  
✅ **Crypto tracking** - Original token amount preserved for blockchain payments  

---

## Frontend Changes Required

### 1. Update Type Definitions

**File:** `src/types/api.types.ts`

```typescript
// New standardized types
export interface MonetaryAmount {
  amount: number;
  currency: string;
  symbol: string;
  formatted: string;
  amount_usd?: number;
  formatted_usd?: string;
  amount_crypto?: number;
  crypto_token?: string;
  crypto_chain?: string;
}

export interface MerchantCurrency {
  currency: string;
  symbol: string;
  locale: string;
  decimal_places?: number;
}

// Updated API response types
export interface PaymentSession {
  id: string;
  amount: MonetaryAmount;  // ✅ Changed from amount_fiat
  status: string;
  created_at: string;
  paid_at?: string;
  merchant_currency?: MerchantCurrency;
  
  // Deprecated fields (still present for backward compatibility)
  amount_fiat?: number;  // ⚠️ Deprecated - use amount.amount_usd
  fiat_currency?: string;  // ⚠️ Deprecated - use amount.currency
  amount_usdc?: string;  // ⚠️ Deprecated - use amount.amount_crypto
}

export interface AnalyticsOverview {
  payments: {
    total_volume: MonetaryAmount;  // ✅ Changed from number
    total_payments: number;
    avg_payment: MonetaryAmount;  // ✅ Changed from number
  };
  volume_change_pct: number;
  merchant_currency: MerchantCurrency;
}

export interface Invoice {
  id: string;
  subtotal: MonetaryAmount;  // ✅ Changed from number
  discount: MonetaryAmount;  // ✅ Changed from number
  total: MonetaryAmount;  // ✅ Changed from number
  status: string;
  merchant_currency: MerchantCurrency;
}

export interface WalletBalance {
  total_balance: MonetaryAmount;  // ✅ Changed from number
  wallets: Array<{
    chain: string;
    address: string;
    balance: MonetaryAmount;  // ✅ Changed from number
  }>;
  merchant_currency: MerchantCurrency;
}

export interface Withdrawal {
  id: string;
  amount: MonetaryAmount;  // ✅ Changed from number
  fee: MonetaryAmount;  // ✅ Changed from number
  total_deducted: MonetaryAmount;  // ✅ Changed from number
  status: string;
  merchant_currency: MerchantCurrency;
}
```

---

### 2. Remove Frontend Formatting Functions

**Delete or deprecate these functions:**

```typescript
// ❌ DELETE - Backend now provides formatted strings
function formatCurrency(amount: number, currency: string): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: currency
  }).format(amount);
}

// ❌ DELETE - Use amount.formatted from API
function displayAmount(amount: number, currency: string): string {
  const symbol = getCurrencySymbol(currency);
  return `${symbol}${amount.toFixed(2)}`;
}

// ❌ DELETE - Use amount.symbol from API
function getCurrencySymbol(currency: string): string {
  const symbols = { USD: '$', EUR: '€', GBP: '£', INR: '₹' };
  return symbols[currency] || currency;
}

// ❌ DELETE - Backend handles conversions
function convertCurrency(amount: number, fromCurrency: string, toCurrency: string): number {
  // Frontend conversion logic - no longer needed
}
```

---

### 3. Update Components to Use Formatted Strings

#### Before (Old Code)
```tsx
// ❌ OLD - Frontend formatting
import { formatCurrency } from '@/utils/currency';

function PaymentCard({ payment }: { payment: PaymentSession }) {
  return (
    <div>
      <h3>Payment Amount</h3>
      <p>{formatCurrency(payment.amount_fiat, payment.fiat_currency)}</p>
    </div>
  );
}
```

#### After (New Code)
```tsx
// ✅ NEW - Use pre-formatted string from backend
function PaymentCard({ payment }: { payment: PaymentSession }) {
  return (
    <div>
      <h3>Payment Amount</h3>
      <p>{payment.amount.formatted}</p>
      
      {/* Optional: Show USD reference */}
      {payment.amount.formatted_usd && (
        <p className="text-sm text-muted-foreground">
          {payment.amount.formatted_usd}
        </p>
      )}
    </div>
  );
}
```

---

### 4. Update Analytics Dashboard

#### Before (Old Code)
```tsx
// ❌ OLD - Manual formatting
function AnalyticsDashboard({ data }: { data: AnalyticsOverview }) {
  const totalVolume = formatCurrency(data.payments.total_volume, 'USD');
  const avgPayment = formatCurrency(data.payments.avg_payment, 'USD');
  
  return (
    <div>
      <div>Total Volume: {totalVolume}</div>
      <div>Avg Payment: {avgPayment}</div>
    </div>
  );
}
```

#### After (New Code)
```tsx
// ✅ NEW - Use formatted strings
function AnalyticsDashboard({ data }: { data: AnalyticsOverview }) {
  return (
    <div>
      <div>
        <span>Total Volume: </span>
        <span className="text-2xl font-bold">
          {data.payments.total_volume.formatted}
        </span>
        {data.payments.total_volume.formatted_usd && (
          <span className="text-sm text-muted-foreground ml-2">
            ({data.payments.total_volume.formatted_usd})
          </span>
        )}
      </div>
      
      <div>
        <span>Avg Payment: </span>
        <span className="text-xl">
          {data.payments.avg_payment.formatted}
        </span>
      </div>
      
      {/* Show merchant's currency preference */}
      <div className="text-xs text-muted-foreground">
        Currency: {data.merchant_currency.currency}
      </div>
    </div>
  );
}
```

---

### 5. Update Invoice Display

#### Before (Old Code)
```tsx
// ❌ OLD - Manual calculations and formatting
function InvoiceDetail({ invoice }: { invoice: Invoice }) {
  const subtotal = formatCurrency(invoice.subtotal, invoice.currency);
  const discount = formatCurrency(invoice.discount, invoice.currency);
  const total = formatCurrency(invoice.total, invoice.currency);
  
  return (
    <div>
      <div>Subtotal: {subtotal}</div>
      <div>Discount: -{discount}</div>
      <div>Total: {total}</div>
    </div>
  );
}
```

#### After (New Code)
```tsx
// ✅ NEW - Use pre-formatted amounts
function InvoiceDetail({ invoice }: { invoice: Invoice }) {
  return (
    <div>
      <div className="flex justify-between">
        <span>Subtotal:</span>
        <span>{invoice.subtotal.formatted}</span>
      </div>
      
      {invoice.discount.amount > 0 && (
        <div className="flex justify-between text-green-600">
          <span>Discount:</span>
          <span>-{invoice.discount.formatted}</span>
        </div>
      )}
      
      <div className="flex justify-between font-bold text-lg border-t pt-2">
        <span>Total:</span>
        <span>{invoice.total.formatted}</span>
      </div>
      
      {/* Show USD equivalent if different currency */}
      {invoice.total.formatted_usd && (
        <div className="text-sm text-muted-foreground text-right">
          ≈ {invoice.total.formatted_usd}
        </div>
      )}
    </div>
  );
}
```

---

### 6. Update Wallet Balance Display

#### Before (Old Code)
```tsx
// ❌ OLD - Manual formatting
function WalletDashboard({ balance }: { balance: WalletBalance }) {
  const totalUSDC = balance.total_balance_usdc;
  const formatted = `$${totalUSDC.toFixed(2)}`;
  
  return (
    <div>
      <h2>Total Balance</h2>
      <p className="text-3xl">{formatted}</p>
    </div>
  );
}
```

#### After (New Code)
```tsx
// ✅ NEW - Use formatted balance
function WalletDashboard({ balance }: { balance: WalletBalance }) {
  return (
    <div>
      <h2>Total Balance</h2>
      <p className="text-3xl font-bold">
        {balance.total_balance.formatted}
      </p>
      
      {/* Show USD equivalent */}
      {balance.total_balance.formatted_usd && (
        <p className="text-lg text-muted-foreground">
          {balance.total_balance.formatted_usd}
        </p>
      )}
      
      {/* Per-wallet breakdown */}
      <div className="mt-4 space-y-2">
        {balance.wallets.map(wallet => (
          <div key={wallet.address} className="flex justify-between">
            <span>{wallet.chain}</span>
            <span>{wallet.balance.formatted}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
```

---

### 7. Update Charts and Graphs

#### Before (Old Code)
```tsx
// ❌ OLD - Manual formatting for chart tooltips
function RevenueChart({ data }: { data: RevenueTimeSeries[] }) {
  const chartData = data.map(point => ({
    date: point.date,
    revenue: point.volume_usd,
    formatted: formatCurrency(point.volume_usd, 'USD')
  }));
  
  return (
    <LineChart data={chartData}>
      <Tooltip formatter={(value) => formatCurrency(value, 'USD')} />
    </LineChart>
  );
}
```

#### After (New Code)
```tsx
// ✅ NEW - Use pre-formatted values
function RevenueChart({ data }: { data: RevenueTimeSeries[] }) {
  const chartData = data.map(point => ({
    date: point.date,
    revenue: point.revenue.amount,
    formatted: point.revenue.formatted  // ✅ Already formatted by backend
  }));
  
  return (
    <LineChart data={chartData}>
      <Tooltip 
        formatter={(value, name, props) => props.payload.formatted} 
      />
    </LineChart>
  );
}
```

---

### 8. Handle Backward Compatibility

For gradual migration, handle both old and new formats:

```typescript
// Utility function for backward compatibility
function getAmount(payment: PaymentSession): string {
  // Try new format first
  if (payment.amount?.formatted) {
    return payment.amount.formatted;
  }
  
  // Fallback to old format
  if (payment.amount_fiat && payment.fiat_currency) {
    return formatCurrency(payment.amount_fiat, payment.fiat_currency);
  }
  
  return 'N/A';
}

// Usage
function PaymentCard({ payment }: { payment: PaymentSession }) {
  return <div>{getAmount(payment)}</div>;
}
```

---

## Migration Checklist

### Phase 1: Update Types
- [ ] Add `MonetaryAmount` and `MerchantCurrency` interfaces
- [ ] Update all API response types to use `MonetaryAmount`
- [ ] Mark old fields as deprecated with JSDoc comments

### Phase 2: Update Components
- [ ] Replace `formatCurrency()` calls with `amount.formatted`
- [ ] Replace `getCurrencySymbol()` calls with `amount.symbol`
- [ ] Update analytics dashboard components
- [ ] Update payment list components
- [ ] Update invoice components
- [ ] Update wallet balance components
- [ ] Update withdrawal components
- [ ] Update subscription components

### Phase 3: Update Charts
- [ ] Update chart tooltip formatters
- [ ] Update chart axis formatters
- [ ] Update chart data transformations

### Phase 4: Remove Old Code
- [ ] Delete `formatCurrency()` function
- [ ] Delete `getCurrencySymbol()` function
- [ ] Delete `convertCurrency()` function
- [ ] Delete `displayAmount()` function
- [ ] Remove currency formatting utilities

### Phase 5: Testing
- [ ] Test all pages display amounts correctly
- [ ] Test USD reference shows when available
- [ ] Test charts display formatted values
- [ ] Test exports use correct currency
- [ ] Test receipts use correct currency
- [ ] Test with different merchant currencies (USD, EUR, INR, etc.)

---

## API Endpoints Updated

All endpoints now return `MonetaryAmount` objects:

### Analytics
- `GET /analytics/overview` - Returns `MonetaryAmount` for all volume fields
- `GET /analytics/revenue` - Returns `MonetaryAmount` for time series data
- `GET /analytics/mrr-arr` - Returns `MonetaryAmount` for MRR/ARR values

### Payments
- `GET /payments/sessions` - Returns `MonetaryAmount` for payment amounts
- `GET /payments/sessions/{id}` - Returns `MonetaryAmount` with dual currency

### Wallets
- `GET /wallets/dashboard` - Returns `MonetaryAmount` for all balances

### Invoices
- `GET /invoices` - Returns `MonetaryAmount` for subtotal, discount, total
- `GET /invoices/{id}` - Returns `MonetaryAmount` for all amounts

### Subscriptions
- `GET /subscriptions/plans` - Returns `MonetaryAmount` for pricing
- `GET /subscriptions/usage` - Returns `MonetaryAmount` for usage data

### Withdrawals
- `GET /withdrawals` - Returns `MonetaryAmount` for amounts and fees

---

## Example: Complete Component Migration

### Before (Old Implementation)
```tsx
import { formatCurrency, getCurrencySymbol } from '@/utils/currency';

interface OldPayment {
  id: string;
  amount_fiat: number;
  fiat_currency: string;
  amount_usdc: string;
  status: string;
}

function PaymentList({ payments }: { payments: OldPayment[] }) {
  return (
    <table>
      <thead>
        <tr>
          <th>ID</th>
          <th>Amount</th>
          <th>Token</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>
        {payments.map(payment => (
          <tr key={payment.id}>
            <td>{payment.id}</td>
            <td>{formatCurrency(payment.amount_fiat, payment.fiat_currency)}</td>
            <td>{payment.amount_usdc} USDC</td>
            <td>{payment.status}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

### After (New Implementation)
```tsx
import { MonetaryAmount, MerchantCurrency } from '@/types/api.types';

interface NewPayment {
  id: string;
  amount: MonetaryAmount;
  status: string;
  merchant_currency: MerchantCurrency;
}

function PaymentList({ payments }: { payments: NewPayment[] }) {
  return (
    <table>
      <thead>
        <tr>
          <th>ID</th>
          <th>Amount</th>
          <th>USD Equivalent</th>
          <th>Token</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>
        {payments.map(payment => (
          <tr key={payment.id}>
            <td>{payment.id}</td>
            <td className="font-semibold">
              {payment.amount.formatted}
            </td>
            <td className="text-sm text-muted-foreground">
              {payment.amount.formatted_usd || '-'}
            </td>
            <td>
              {payment.amount.amount_crypto && payment.amount.crypto_token && (
                <span>
                  {payment.amount.amount_crypto} {payment.amount.crypto_token}
                  <span className="text-xs text-muted-foreground ml-1">
                    ({payment.amount.crypto_chain})
                  </span>
                </span>
              )}
            </td>
            <td>
              <span className={`badge badge-${payment.status}`}>
                {payment.status}
              </span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

---

## Benefits Summary

### For Developers
- ✅ Less code to maintain (no formatting logic)
- ✅ Consistent display across all pages
- ✅ No currency conversion bugs
- ✅ Easier to add new currencies

### For Users
- ✅ Amounts shown in their preferred currency
- ✅ Consistent formatting with proper locale
- ✅ USD reference for cross-currency comparison
- ✅ Accurate exchange rates across all pages

### For Business
- ✅ Professional currency handling
- ✅ Support for 100+ currencies
- ✅ Scalable architecture
- ✅ Better user experience

---

## Support

If you encounter issues during migration:

1. Check that backend API is updated to v2.2+
2. Verify `MonetaryAmount` objects are present in API responses
3. Check browser console for type errors
4. Test with different merchant currencies
5. Verify backward compatibility with old API responses

---

## Timeline

**Recommended Migration Schedule:**

- **Week 1**: Update type definitions and add backward compatibility
- **Week 2**: Update main dashboard and analytics pages
- **Week 3**: Update payment, invoice, and wallet pages
- **Week 4**: Update charts, exports, and remaining pages
- **Week 5**: Remove old formatting functions and test thoroughly

---

## Questions?

Contact the backend team if you need:
- Additional currency metadata
- Custom formatting options
- New currency support
- Migration assistance
