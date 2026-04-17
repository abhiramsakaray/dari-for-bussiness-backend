# Analytics Frontend Fix

## Issue

The Analytics page may not be loading or showing data correctly for merchants.

## Common Analytics Issues

### Issue 1: Analytics Not Loading

**Symptoms:**
- Blank analytics page
- Loading spinner that never completes
- "No data available" message

**Possible Causes:**
1. Wrong API endpoint
2. Authentication issues
3. Missing date range parameters
4. CORS errors

### Issue 2: Wrong Data Displayed

**Symptoms:**
- Incorrect totals
- Missing charts
- Wrong currency displayed

**Possible Causes:**
1. Not using merchant's currency
2. Wrong date range calculation
3. Missing data aggregation

## Solutions

### 1. Fix Analytics API Endpoint

**File: `src/hooks/useAnalytics.ts` (or similar)**

```typescript
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';

export function useAnalytics(period: 'day' | 'week' | 'month' | 'year' = 'month') {
  return useQuery({
    queryKey: ['analytics', 'overview', period],
    queryFn: async () => {
      const response = await api.get('/analytics/overview', {
        params: { period }
      });
      return response.data;
    },
    retry: 1,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

export function useTransactionAnalytics(startDate?: string, endDate?: string) {
  return useQuery({
    queryKey: ['analytics', 'transactions', startDate, endDate],
    queryFn: async () => {
      const response = await api.get('/analytics/transactions', {
        params: { start_date: startDate, end_date: endDate }
      });
      return response.data;
    },
    enabled: !!startDate && !!endDate,
    retry: 1,
  });
}

export function useRevenueAnalytics(period: string = 'month') {
  return useQuery({
    queryKey: ['analytics', 'revenue', period],
    queryFn: async () => {
      const response = await api.get('/analytics/revenue', {
        params: { period }
      });
      return response.data;
    },
    retry: 1,
  });
}
```

### 2. Create Analytics Dashboard Component

**File: `src/components/analytics/AnalyticsDashboard.tsx`**

```typescript
import { useState } from 'react';
import { useAnalytics, useTransactionAnalytics } from '@/hooks/useAnalytics';
import { useMerchantCurrency } from '@/hooks/useMerchantCurrency';

export function AnalyticsDashboard() {
  const [period, setPeriod] = useState<'day' | 'week' | 'month' | 'year'>('month');
  const { data: analytics, isLoading, error } = useAnalytics(period);
  const { currencySymbol, currencyCode } = useMerchantCurrency();

  if (isLoading) {
    return (
      <div className="analytics-loading">
        <div className="spinner" />
        <p>Loading analytics...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="analytics-error">
        <h3>⚠️ Error Loading Analytics</h3>
        <p>Failed to load analytics data. Please try again.</p>
        <button onClick={() => window.location.reload()}>Retry</button>
      </div>
    );
  }

  if (!analytics) {
    return (
      <div className="analytics-empty">
        <h3>No Data Available</h3>
        <p>No analytics data available for the selected period.</p>
      </div>
    );
  }

  return (
    <div className="analytics-dashboard">
      {/* Period Selector */}
      <div className="period-selector">
        <button 
          onClick={() => setPeriod('day')}
          className={period === 'day' ? 'active' : ''}
        >
          Today
        </button>
        <button 
          onClick={() => setPeriod('week')}
          className={period === 'week' ? 'active' : ''}
        >
          This Week
        </button>
        <button 
          onClick={() => setPeriod('month')}
          className={period === 'month' ? 'active' : ''}
        >
          This Month
        </button>
        <button 
          onClick={() => setPeriod('year')}
          className={period === 'year' ? 'active' : ''}
        >
          This Year
        </button>
      </div>

      {/* Key Metrics */}
      <div className="metrics-grid">
        <MetricCard
          title="Total Revenue"
          value={`${currencySymbol}${analytics.total_revenue?.toLocaleString() || 0}`}
          change={analytics.revenue_change}
          currency={currencyCode}
        />
        <MetricCard
          title="Total Transactions"
          value={analytics.total_transactions?.toLocaleString() || 0}
          change={analytics.transaction_change}
        />
        <MetricCard
          title="Success Rate"
          value={`${analytics.success_rate || 0}%`}
          change={analytics.success_rate_change}
        />
        <MetricCard
          title="Average Transaction"
          value={`${currencySymbol}${analytics.average_transaction?.toLocaleString() || 0}`}
          currency={currencyCode}
        />
      </div>

      {/* Charts */}
      <div className="charts-section">
        <RevenueChart data={analytics.revenue_chart} currency={currencySymbol} />
        <TransactionChart data={analytics.transaction_chart} />
      </div>

      {/* Recent Transactions */}
      <div className="recent-transactions">
        <h3>Recent Transactions</h3>
        <TransactionList transactions={analytics.recent_transactions} />
      </div>
    </div>
  );
}

function MetricCard({ title, value, change, currency }) {
  const isPositive = change >= 0;
  
  return (
    <div className="metric-card">
      <h4>{title}</h4>
      <div className="metric-value">{value}</div>
      {change !== undefined && (
        <div className={`metric-change ${isPositive ? 'positive' : 'negative'}`}>
          <span>{isPositive ? '↑' : '↓'}</span>
          <span>{Math.abs(change)}%</span>
          <span className="period">vs last period</span>
        </div>
      )}
    </div>
  );
}
```

### 3. Fix Currency Display in Analytics

**File: `src/hooks/useMerchantCurrency.ts`**

```typescript
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';

export function useMerchantCurrency() {
  const { data: merchant } = useQuery({
    queryKey: ['merchant', 'profile'],
    queryFn: async () => {
      const response = await api.get('/merchant/profile');
      return response.data;
    },
    staleTime: 10 * 60 * 1000, // 10 minutes
  });

  const currencyCode = merchant?.base_currency || merchant?.currency_preference || 'USD';
  const currencySymbol = getCurrencySymbol(currencyCode);

  return {
    currencyCode,
    currencySymbol,
    currencyName: merchant?.currency_name || 'US Dollar',
  };
}

function getCurrencySymbol(code: string): string {
  const symbols: Record<string, string> = {
    'USD': '$',
    'INR': '₹',
    'EUR': '€',
    'GBP': '£',
    'JPY': '¥',
    'AUD': 'A$',
    'CAD': 'C$',
    'CNY': '¥',
    'SGD': 'S$',
    'AED': 'د.إ',
    'SAR': '﷼',
  };
  
  return symbols[code] || code;
}
```

### 4. Add Date Range Picker

**File: `src/components/analytics/DateRangePicker.tsx`**

```typescript
import { useState } from 'react';

export function DateRangePicker({ onRangeChange }) {
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');

  const handleApply = () => {
    if (startDate && endDate) {
      onRangeChange(startDate, endDate);
    }
  };

  const setPreset = (preset: 'today' | 'week' | 'month' | 'year') => {
    const end = new Date();
    const start = new Date();

    switch (preset) {
      case 'today':
        start.setHours(0, 0, 0, 0);
        break;
      case 'week':
        start.setDate(end.getDate() - 7);
        break;
      case 'month':
        start.setMonth(end.getMonth() - 1);
        break;
      case 'year':
        start.setFullYear(end.getFullYear() - 1);
        break;
    }

    setStartDate(start.toISOString().split('T')[0]);
    setEndDate(end.toISOString().split('T')[0]);
    onRangeChange(
      start.toISOString().split('T')[0],
      end.toISOString().split('T')[0]
    );
  };

  return (
    <div className="date-range-picker">
      <div className="presets">
        <button onClick={() => setPreset('today')}>Today</button>
        <button onClick={() => setPreset('week')}>Last 7 Days</button>
        <button onClick={() => setPreset('month')}>Last 30 Days</button>
        <button onClick={() => setPreset('year')}>Last Year</button>
      </div>

      <div className="custom-range">
        <input
          type="date"
          value={startDate}
          onChange={(e) => setStartDate(e.target.value)}
          placeholder="Start Date"
        />
        <span>to</span>
        <input
          type="date"
          value={endDate}
          onChange={(e) => setEndDate(e.target.value)}
          placeholder="End Date"
        />
        <button onClick={handleApply}>Apply</button>
      </div>
    </div>
  );
}
```

### 5. Handle Empty States

**File: `src/components/analytics/EmptyState.tsx`**

```typescript
export function AnalyticsEmptyState() {
  return (
    <div className="analytics-empty-state">
      <div className="empty-icon">📊</div>
      <h3>No Analytics Data Yet</h3>
      <p>Start accepting payments to see your analytics here.</p>
      <div className="empty-actions">
        <button onClick={() => window.location.href = '/payments/create'}>
          Create Payment Link
        </button>
        <button onClick={() => window.location.href = '/api-docs'}>
          View API Docs
        </button>
      </div>
    </div>
  );
}
```

## Backend API Endpoints

### Analytics Overview
```
GET /analytics/overview?period=month
```

**Response:**
```json
{
  "total_revenue": 125000,
  "total_transactions": 450,
  "success_rate": 98.5,
  "average_transaction": 277.78,
  "revenue_change": 15.5,
  "transaction_change": 12.3,
  "success_rate_change": 2.1,
  "currency": "INR",
  "period": "month",
  "revenue_chart": [...],
  "transaction_chart": [...],
  "recent_transactions": [...]
}
```

### Transaction Analytics
```
GET /analytics/transactions?start_date=2026-03-01&end_date=2026-04-01
```

### Revenue Analytics
```
GET /analytics/revenue?period=month
```

## Common Issues & Fixes

### Issue: Analytics showing $0 for INR users

**Problem:** Analytics not converting to merchant's currency

**Fix:**
```typescript
// Use merchant's currency from profile
const { currencySymbol, currencyCode } = useMerchantCurrency();

// Display with correct symbol
<div>{currencySymbol}{amount.toLocaleString()}</div>
```

### Issue: Charts not rendering

**Problem:** Missing chart library or wrong data format

**Fix:**
```bash
# Install chart library
npm install recharts
# or
npm install chart.js react-chartjs-2
```

```typescript
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip } from 'recharts';

function RevenueChart({ data, currency }) {
  return (
    <LineChart width={600} height={300} data={data}>
      <CartesianGrid strokeDasharray="3 3" />
      <XAxis dataKey="date" />
      <YAxis />
      <Tooltip formatter={(value) => `${currency}${value.toLocaleString()}`} />
      <Line type="monotone" dataKey="revenue" stroke="#8884d8" />
    </LineChart>
  );
}
```

### Issue: Date range not working

**Problem:** Wrong date format sent to backend

**Fix:**
```typescript
// Use ISO format: YYYY-MM-DD
const startDate = new Date().toISOString().split('T')[0];
const endDate = new Date().toISOString().split('T')[0];

// Send to API
api.get('/analytics/transactions', {
  params: {
    start_date: startDate,
    end_date: endDate
  }
});
```

## Testing Checklist

- [ ] Analytics page loads without errors
- [ ] Correct currency symbol displayed (₹ for INR, $ for USD)
- [ ] Period selector works (day, week, month, year)
- [ ] Date range picker works
- [ ] Charts render correctly
- [ ] Empty state shows when no data
- [ ] Error state shows on API failure
- [ ] Loading state shows while fetching
- [ ] Recent transactions list displays
- [ ] Metrics show correct values

## Files to Create/Update

1. **src/hooks/useAnalytics.ts** - Analytics data hooks
2. **src/hooks/useMerchantCurrency.ts** - Currency helper
3. **src/components/analytics/AnalyticsDashboard.tsx** - Main dashboard
4. **src/components/analytics/DateRangePicker.tsx** - Date selector
5. **src/components/analytics/EmptyState.tsx** - Empty state UI
6. **src/components/analytics/MetricCard.tsx** - Metric display
7. **src/components/analytics/RevenueChart.tsx** - Revenue chart
8. **src/components/analytics/TransactionChart.tsx** - Transaction chart

## Summary

To fix analytics:
1. Use correct API endpoints
2. Display merchant's currency correctly
3. Handle loading/error/empty states
4. Add date range selection
5. Render charts properly
6. Show recent transactions

---

**Status:** Ready to implement  
**Priority:** HIGH  
**Impact:** Analytics not working for merchants  
**Estimated Time:** 1-2 hours
