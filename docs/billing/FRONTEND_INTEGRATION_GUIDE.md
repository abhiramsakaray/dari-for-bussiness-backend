# Frontend Integration Guide - Billing Currency Fix

## Quick Summary

The backend now provides billing plan prices in the merchant's currency. Update your frontend to use these backend-provided prices instead of hardcoded USD values.

## What Changed

### Before (Broken)
```typescript
// ❌ Hardcoded USD prices
const prices = {
  free: 0,
  growth: 29,
  business: 99,
  enterprise: 'Custom'
};

// Shows ₹29 for Indian users (WRONG!)
<div>{currencySymbol}{prices.growth}</div>
```

### After (Fixed)
```typescript
// ✅ Use backend-provided prices
const getPlanPrice = (planId) => {
  return billingInfo?.available_plans?.[planId]?.price || 0;
};

// Shows ₹2,400 for Indian users (CORRECT!)
<div>{currencySymbol}{getPlanPrice('growth').toLocaleString()}</div>
```

## API Changes

### 1. GET /billing/info (or /subscription/current)

**New Fields Added:**
- `currency`: Currency code (e.g., "USD", "INR", "EUR")
- `available_plans`: Object with all plans in merchant's currency

**Example Response:**
```json
{
  "tier": "growth",
  "status": "active",
  "monthly_price": 2400,
  "currency": "INR",
  "transaction_fee_percent": 0.9,
  "current_period_start": "2026-03-05T00:00:00Z",
  "current_period_end": "2026-04-05T00:00:00Z",
  "available_plans": {
    "free": {
      "id": "free",
      "name": "Free",
      "price": 0,
      "currency": "INR",
      "billing_period": "month",
      "features": {
        "transaction_fee": "1.0-1.5%",
        "monthly_volume_limit": 1000,
        "payment_links": 2,
        "invoices": 5,
        "team_members": 1
      }
    },
    "growth": {
      "id": "growth",
      "name": "Growth",
      "price": 2400,
      "currency": "INR",
      "billing_period": "month",
      "features": {
        "transaction_fee": "0.8-1.0%",
        "monthly_volume_limit": 50000,
        "payment_links": null,
        "invoices": null,
        "team_members": 3
      }
    },
    "business": {
      "id": "business",
      "name": "Business",
      "price": 8200,
      "currency": "INR",
      "billing_period": "month",
      "features": {
        "transaction_fee": "0.5-0.8%",
        "monthly_volume_limit": 500000,
        "payment_links": null,
        "invoices": null,
        "team_members": 10
      }
    },
    "enterprise": {
      "id": "enterprise",
      "name": "Enterprise",
      "price": 24900,
      "currency": "INR",
      "billing_period": "month",
      "features": {
        "transaction_fee": "0.2-0.5%",
        "monthly_volume_limit": null,
        "payment_links": null,
        "invoices": null,
        "team_members": null
      }
    }
  }
}
```

### 2. GET /billing/plans (or /subscription/plans)

**New Field Added:**
- `currency`: Currency code for the price

**Example Response:**
```json
[
  {
    "tier": "free",
    "name": "Free",
    "monthly_price": 0,
    "currency": "INR",
    "transaction_fee_min": 1.0,
    "transaction_fee_max": 1.5,
    "monthly_volume_limit": 1000,
    "payment_link_limit": 2,
    "invoice_limit": 5,
    "team_member_limit": 1,
    "features": [...]
  },
  {
    "tier": "growth",
    "name": "Growth",
    "monthly_price": 2400,
    "currency": "INR",
    "transaction_fee_min": 0.8,
    "transaction_fee_max": 1.0,
    "monthly_volume_limit": 50000,
    "payment_link_limit": null,
    "invoice_limit": null,
    "team_member_limit": 3,
    "features": [...]
  }
]
```

## Frontend Implementation

### Step 1: Update TypeScript Interfaces

```typescript
// billing.types.ts

export interface PlanFeatures {
  transaction_fee: string;
  monthly_volume_limit: number | null;
  payment_links: number | null;
  invoices: number | null;
  team_members: number | null;
}

export interface PlanInfo {
  id: string;
  name: string;
  price: number;
  currency: string;
  billing_period: string;
  features: PlanFeatures;
}

export interface BillingInfo {
  tier: string;
  status: string;
  monthly_price: number;
  currency: string;  // NEW
  transaction_fee_percent: number;
  monthly_volume_limit: number | null;
  payment_link_limit: number | null;
  invoice_limit: number | null;
  team_member_limit: number;
  current_volume: number;
  current_payment_links: number;
  current_invoices: number;
  current_period_start: string;
  current_period_end: string;
  trial_ends_at: string | null;
  available_plans?: Record<string, PlanInfo>;  // NEW
}

export interface SubscriptionPlan {
  tier: string;
  name: string;
  monthly_price: number;
  currency: string;  // NEW
  transaction_fee_min: number;
  transaction_fee_max: number;
  monthly_volume_limit: number | null;
  payment_link_limit: number | null;
  invoice_limit: number | null;
  team_member_limit: number;
  features: string[];
}
```

### Step 2: Update Billing Component

```typescript
// Billing.tsx

import { useBilling } from './hooks/useBilling';

export function Billing() {
  const { billingInfo, isLoading, error } = useBilling();
  
  // Get currency symbol from currency code
  const getCurrencySymbol = (currencyCode: string): string => {
    const symbols: Record<string, string> = {
      'USD': '$',
      'INR': '₹',
      'EUR': '€',
      'GBP': '£',
      'JPY': '¥',
      'AUD': 'A$',
      'CAD': 'C$',
    };
    return symbols[currencyCode] || currencyCode;
  };
  
  // Get plan price from backend data
  const getPlanPrice = (planId: string): number | null => {
    if (billingInfo?.available_plans?.[planId]) {
      return billingInfo.available_plans[planId].price;
    }
    return null;
  };
  
  // Format price with currency
  const formatPrice = (price: number | null, currency: string): string => {
    if (price === null) return 'Custom';
    if (price === 0) return 'Free';
    
    const symbol = getCurrencySymbol(currency);
    const formatted = price.toLocaleString(undefined, {
      minimumFractionDigits: 0,
      maximumFractionDigits: 2,
    });
    
    return `${symbol}${formatted}`;
  };
  
  if (isLoading) return <div>Loading...</div>;
  if (error) return <div>Error loading billing info</div>;
  if (!billingInfo) return null;
  
  const currency = billingInfo.currency || 'USD';
  
  return (
    <div className="billing-page">
      <h1>Subscription Plans</h1>
      
      {/* Free Plan */}
      <div className="plan-card">
        <h2>Free</h2>
        <div className="price">
          {formatPrice(getPlanPrice('free'), currency)}
          <span className="period">/month</span>
        </div>
        <ul className="features">
          {billingInfo.available_plans?.free?.features && (
            <>
              <li>Transaction fee: {billingInfo.available_plans.free.features.transaction_fee}</li>
              <li>Volume limit: {billingInfo.available_plans.free.features.monthly_volume_limit}</li>
            </>
          )}
        </ul>
      </div>
      
      {/* Growth Plan */}
      <div className="plan-card">
        <h2>Growth</h2>
        <div className="price">
          {formatPrice(getPlanPrice('growth'), currency)}
          <span className="period">/month</span>
        </div>
        <ul className="features">
          {billingInfo.available_plans?.growth?.features && (
            <>
              <li>Transaction fee: {billingInfo.available_plans.growth.features.transaction_fee}</li>
              <li>Volume limit: {billingInfo.available_plans.growth.features.monthly_volume_limit || 'Unlimited'}</li>
            </>
          )}
        </ul>
      </div>
      
      {/* Business Plan */}
      <div className="plan-card">
        <h2>Business</h2>
        <div className="price">
          {formatPrice(getPlanPrice('business'), currency)}
          <span className="period">/month</span>
        </div>
        <ul className="features">
          {billingInfo.available_plans?.business?.features && (
            <>
              <li>Transaction fee: {billingInfo.available_plans.business.features.transaction_fee}</li>
              <li>Volume limit: {billingInfo.available_plans.business.features.monthly_volume_limit || 'Unlimited'}</li>
            </>
          )}
        </ul>
      </div>
      
      {/* Enterprise Plan */}
      <div className="plan-card">
        <h2>Enterprise</h2>
        <div className="price">
          {formatPrice(getPlanPrice('enterprise'), currency)}
          <span className="period">/month</span>
        </div>
        <button>Contact Sales</button>
      </div>
    </div>
  );
}
```

### Step 3: Update API Service (if needed)

```typescript
// billing.service.ts

export interface BillingService {
  getBillingInfo(): Promise<BillingInfo>;
  getPlans(): Promise<SubscriptionPlan[]>;
}

export const billingService: BillingService = {
  async getBillingInfo() {
    const response = await fetch('/api/billing/info', {
      headers: {
        'Authorization': `Bearer ${getAuthToken()}`,
      },
    });
    
    if (!response.ok) {
      throw new Error('Failed to fetch billing info');
    }
    
    return response.json();
  },
  
  async getPlans() {
    const response = await fetch('/api/billing/plans', {
      headers: {
        'Authorization': `Bearer ${getAuthToken()}`,
      },
    });
    
    if (!response.ok) {
      throw new Error('Failed to fetch plans');
    }
    
    return response.json();
  },
};
```

## Migration Checklist

- [ ] Update TypeScript interfaces to include `currency` field
- [ ] Add `available_plans` to `BillingInfo` interface
- [ ] Remove hardcoded price constants
- [ ] Update components to use `getPlanPrice()` helper
- [ ] Update currency symbol logic to use backend currency
- [ ] Test with USD user account
- [ ] Test with INR user account
- [ ] Test with EUR user account
- [ ] Verify price formatting is correct
- [ ] Update any price-related tests

## Testing

### Test Cases

1. **USD User**
   - Login as US-based merchant
   - Navigate to billing page
   - Verify prices show: $0, $29, $99
   - Verify currency symbol is $

2. **INR User**
   - Login as India-based merchant
   - Navigate to billing page
   - Verify prices show: ₹0, ₹2,400, ₹8,200
   - Verify currency symbol is ₹

3. **EUR User**
   - Login as Europe-based merchant
   - Navigate to billing page
   - Verify prices show: €0, €27, €91
   - Verify currency symbol is €

### Manual Testing

```bash
# Test API directly
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8000/billing/info

# Should return:
# - currency field
# - available_plans object
# - prices in merchant's currency
```

## Backward Compatibility

✅ **Fully backward compatible**
- New fields are optional
- Existing fields unchanged
- Old frontend code will continue to work (but show wrong prices)

## Support

If you encounter issues:
1. Check that backend is updated to latest version
2. Verify API response includes `currency` and `available_plans`
3. Check browser console for errors
4. Verify authentication token is valid

## Example Price Conversions

| Plan | USD | INR | EUR | GBP |
|------|-----|-----|-----|-----|
| Free | $0 | ₹0 | €0 | £0 |
| Growth | $29 | ₹2,400 | €27 | £23 |
| Business | $99 | ₹8,200 | €91 | £78 |
| Enterprise | $300 | ₹24,900 | €276 | £237 |

---

**Last Updated:** April 13, 2026  
**Backend Version:** v2.3.0+  
**Status:** Ready for Frontend Integration
