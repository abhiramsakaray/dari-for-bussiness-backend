# Frontend Fixes Summary

## Overview

This document provides a complete guide to fix all frontend issues identified in the application.

## Issues Identified

1. ✅ **Billing Currency Display** - FIXED (Backend)
2. ⚠️ **Team Permissions Management** - Needs Frontend Fix
3. ⚠️ **Analytics Dashboard** - Needs Frontend Fix

---

## 1. Billing Currency Fix ✅

**Status:** COMPLETE (Backend fixed, frontend working)

### What Was Fixed
- Backend now converts prices to merchant's currency
- `monthly_price` shows converted value (₹2,400 instead of ₹29)
- `available_plans` includes all plans with converted prices

### Frontend Action Required
**NONE** - Frontend is already correctly implemented and will automatically display correct prices once backend is restarted.

### Verification
1. Restart backend server
2. Refresh billing page
3. Verify prices show in merchant's currency

**Documentation:** `docs/billing/FINAL_FIX_COMPLETE.md`

---

## 2. Team Permissions Fix ⚠️

**Status:** NEEDS FRONTEND FIX

### Issue
Permissions tab shows "Permission Management Unavailable" error even for merchants (Owners) who should have full access.

### Root Cause
Frontend is incorrectly blocking merchants from accessing permission management with `if (isMerchant)` checks.

### Quick Fix

#### Step 1: Remove Merchant Blocking
**File:** `src/components/team/PermissionManager.tsx`

```typescript
// ❌ REMOVE THIS
if (isMerchant && error?.response?.status === 401) {
  return <ErrorMessage />;
}

// ✅ REPLACE WITH THIS
if (error?.response?.status === 403) {
  return <AccessDenied />;
}
```

#### Step 2: Fix API Hook
**File:** `src/hooks/usePermissions.ts`

```typescript
// ❌ REMOVE THIS
enabled: !isMerchant,

// ✅ REPLACE WITH THIS
enabled: true,
```

#### Step 3: Update API Endpoint
```typescript
// ✅ Use correct endpoint
api.get('/api/v1/team/roles/permissions')
```

### Files to Update
1. `src/components/team/PermissionManager.tsx`
2. `src/hooks/usePermissions.ts`
3. `src/hooks/useMemberPermissions.ts`

### Testing
1. Log in as merchant (Owner)
2. Navigate to Team → Permissions
3. Should see list of roles and permissions
4. Should NOT see error message

**Full Documentation:** `docs/frontend/TEAM_PERMISSIONS_FRONTEND_FIX.md`

---

## 3. Analytics Dashboard Fix ⚠️

**Status:** NEEDS FRONTEND FIX

### Issue
Analytics page may not be loading or showing incorrect data.

### Common Problems
1. Wrong API endpoints
2. Currency not displaying correctly
3. Charts not rendering
4. Missing date range functionality

### Quick Fix

#### Step 1: Create Analytics Hook
**File:** `src/hooks/useAnalytics.ts`

```typescript
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';

export function useAnalytics(period = 'month') {
  return useQuery({
    queryKey: ['analytics', 'overview', period],
    queryFn: async () => {
      const response = await api.get('/analytics/overview', {
        params: { period }
      });
      return response.data;
    },
    retry: 1,
  });
}
```

#### Step 2: Create Currency Hook
**File:** `src/hooks/useMerchantCurrency.ts`

```typescript
export function useMerchantCurrency() {
  const { data: merchant } = useQuery({
    queryKey: ['merchant', 'profile'],
    queryFn: async () => {
      const response = await api.get('/merchant/profile');
      return response.data;
    },
  });

  const currencyCode = merchant?.base_currency || 'USD';
  const currencySymbol = getCurrencySymbol(currencyCode);

  return { currencyCode, currencySymbol };
}

function getCurrencySymbol(code: string): string {
  const symbols = {
    'USD': '$', 'INR': '₹', 'EUR': '€', 'GBP': '£',
    'JPY': '¥', 'AUD': 'A$', 'CAD': 'C$'
  };
  return symbols[code] || code;
}
```

#### Step 3: Create Analytics Dashboard
**File:** `src/components/analytics/AnalyticsDashboard.tsx`

```typescript
export function AnalyticsDashboard() {
  const [period, setPeriod] = useState('month');
  const { data: analytics, isLoading, error } = useAnalytics(period);
  const { currencySymbol } = useMerchantCurrency();

  if (isLoading) return <LoadingState />;
  if (error) return <ErrorState />;
  if (!analytics) return <EmptyState />;

  return (
    <div className="analytics-dashboard">
      {/* Period Selector */}
      <PeriodSelector value={period} onChange={setPeriod} />
      
      {/* Metrics */}
      <div className="metrics-grid">
        <MetricCard
          title="Total Revenue"
          value={`${currencySymbol}${analytics.total_revenue.toLocaleString()}`}
        />
        <MetricCard
          title="Transactions"
          value={analytics.total_transactions.toLocaleString()}
        />
        <MetricCard
          title="Success Rate"
          value={`${analytics.success_rate}%`}
        />
      </div>
      
      {/* Charts */}
      <RevenueChart data={analytics.revenue_chart} currency={currencySymbol} />
    </div>
  );
}
```

### Files to Create
1. `src/hooks/useAnalytics.ts`
2. `src/hooks/useMerchantCurrency.ts`
3. `src/components/analytics/AnalyticsDashboard.tsx`
4. `src/components/analytics/DateRangePicker.tsx`
5. `src/components/analytics/MetricCard.tsx`
6. `src/components/analytics/RevenueChart.tsx`

### Testing
1. Navigate to Analytics page
2. Verify data loads
3. Check currency symbol is correct (₹ for INR)
4. Test period selector (day, week, month, year)
5. Verify charts render

**Full Documentation:** `docs/frontend/ANALYTICS_FRONTEND_FIX.md`

---

## Implementation Priority

### High Priority (Fix Immediately)
1. **Team Permissions** - Blocking merchants from managing team
2. **Analytics Dashboard** - Core feature not working

### Medium Priority (Already Working)
1. **Billing Currency** - Backend fixed, frontend working

---

## Quick Start Guide

### For Team Permissions Fix (15 minutes)

1. Open `src/components/team/PermissionManager.tsx`
2. Remove all `if (isMerchant)` blocks
3. Update API endpoint to `/api/v1/team/roles/permissions`
4. Remove `enabled: !isMerchant` from useQuery
5. Test with merchant account

### For Analytics Fix (1-2 hours)

1. Create `src/hooks/useAnalytics.ts`
2. Create `src/hooks/useMerchantCurrency.ts`
3. Create `src/components/analytics/AnalyticsDashboard.tsx`
4. Add charts library: `npm install recharts`
5. Test with merchant account

---

## API Endpoints Reference

### Team Permissions
```
GET /api/v1/team/roles/permissions
```

### Analytics
```
GET /analytics/overview?period=month
GET /analytics/transactions?start_date=2026-03-01&end_date=2026-04-01
GET /analytics/revenue?period=month
```

### Billing
```
GET /billing/info
GET /billing/plans
```

### Merchant Profile
```
GET /merchant/profile
```

---

## Common Patterns

### Currency Display
```typescript
const { currencySymbol, currencyCode } = useMerchantCurrency();

// Display amount
<div>{currencySymbol}{amount.toLocaleString()}</div>
```

### Error Handling
```typescript
if (error?.response?.status === 403) {
  return <AccessDenied />;
}

if (error?.response?.status === 401) {
  return <AuthRequired />;
}

return <GenericError />;
```

### Loading States
```typescript
if (isLoading) {
  return <LoadingSpinner />;
}

if (!data) {
  return <EmptyState />;
}

return <DataDisplay data={data} />;
```

---

## Testing Checklist

### Team Permissions
- [ ] Merchant can access Permissions tab
- [ ] Role list displays correctly
- [ ] No "Permission Management Unavailable" error
- [ ] Admin can access Permissions tab
- [ ] Viewer gets "Access Denied" (403)

### Analytics
- [ ] Analytics page loads
- [ ] Correct currency symbol (₹ for INR)
- [ ] Period selector works
- [ ] Charts render
- [ ] Metrics show correct values
- [ ] Empty state for no data
- [ ] Error state for failures

### Billing
- [ ] Current plan shows correct price (₹2,400 not ₹29)
- [ ] Available plans show converted prices
- [ ] Currency symbol matches merchant's currency
- [ ] Plan upgrade works

---

## Support

### Documentation
- **Billing:** `docs/billing/FINAL_FIX_COMPLETE.md`
- **Team Permissions:** `docs/frontend/TEAM_PERMISSIONS_FRONTEND_FIX.md`
- **Analytics:** `docs/frontend/ANALYTICS_FRONTEND_FIX.md`

### Need Help?
1. Check the specific documentation for detailed code examples
2. Review API endpoint responses in browser DevTools
3. Check console for error messages
4. Verify authentication token is valid

---

**Last Updated:** April 13, 2026  
**Status:** 1/3 Complete (Billing ✅, Permissions ⚠️, Analytics ⚠️)  
**Estimated Total Time:** 2-3 hours for all fixes
