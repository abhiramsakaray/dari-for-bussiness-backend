# 🚨 URGENT: Frontend Billing Price Fix

## Current Issue

The billing page is showing **USD prices with INR symbol**:
- Shows: ₹29, ₹99
- Should show: ₹2,400, ₹8,200

## Root Cause

Frontend is using **hardcoded USD prices** instead of backend-provided converted prices.

## Quick Fix (5 minutes)

### Step 1: Check API Response

The backend now returns `available_plans` with converted prices:

```json
{
  "currency": "INR",
  "available_plans": {
    "free": { "price": 0, "currency": "INR" },
    "growth": { "price": 2400, "currency": "INR" },
    "business": { "price": 8200, "currency": "INR" }
  }
}
```

### Step 2: Update Frontend Code

**Find this code (WRONG):**
```typescript
// ❌ Hardcoded prices
const prices = {
  free: 0,
  growth: 29,
  business: 99,
  enterprise: 'Custom'
};

// Shows ₹29 (WRONG!)
<div>{currencySymbol}{prices.growth}</div>
```

**Replace with (CORRECT):**
```typescript
// ✅ Use backend prices
const getPlanPrice = (planId: string) => {
  return billingInfo?.available_plans?.[planId]?.price ?? null;
};

// Shows ₹2,400 (CORRECT!)
<div>
  {getPlanPrice('growth') !== null 
    ? `${currencySymbol}${getPlanPrice('growth').toLocaleString()}`
    : 'Custom'}
</div>
```

### Step 3: Update Current Plan Display

**Current Plan section:**
```typescript
// ❌ WRONG - using hardcoded price
<div>₹{prices[currentTier]}</div>

// ✅ CORRECT - use from API
<div>
  {billingInfo?.currency === 'INR' 
    ? `₹${billingInfo.monthly_price.toLocaleString()}`
    : `$${billingInfo.monthly_price}`}
</div>
```

## Files to Update

Look for these files in your frontend:
- `Billing.tsx` or `Billing.jsx`
- `BillingPage.tsx` or `BillingPage.jsx`
- `Plans.tsx` or `Plans.jsx`
- Any component showing subscription prices

## Search for These Patterns

Search your codebase for:
```
growth: 29
business: 99
monthly_price: 29
monthly_price: 99
```

Replace all hardcoded prices with API data.

## Testing

After the fix:

1. **USD User** should see: $0, $29, $99
2. **INR User** should see: ₹0, ₹2,400, ₹8,200
3. **EUR User** should see: €0, €27, €91

## Example Complete Fix

```typescript
// Billing.tsx
import { useBilling } from './hooks/useBilling';

export function Billing() {
  const { billingInfo, isLoading } = useBilling();
  
  if (isLoading) return <div>Loading...</div>;
  if (!billingInfo) return null;
  
  const currency = billingInfo.currency || 'USD';
  const currencySymbol = currency === 'INR' ? '₹' : 
                         currency === 'EUR' ? '€' : 
                         currency === 'GBP' ? '£' : '$';
  
  const formatPrice = (planId: string) => {
    const price = billingInfo.available_plans?.[planId]?.price;
    if (price === null || price === undefined) return 'Custom';
    if (price === 0) return 'Free';
    return `${currencySymbol}${price.toLocaleString()}`;
  };
  
  return (
    <div>
      {/* Current Plan */}
      <div className="current-plan">
        <h2>{billingInfo.tier}</h2>
        <div className="price">
          {currencySymbol}{billingInfo.monthly_price.toLocaleString()}
          <span>/month</span>
        </div>
      </div>
      
      {/* Available Plans */}
      <div className="plans">
        <div className="plan">
          <h3>Free</h3>
          <div className="price">{formatPrice('free')}</div>
        </div>
        
        <div className="plan">
          <h3>Growth</h3>
          <div className="price">{formatPrice('growth')}</div>
        </div>
        
        <div className="plan">
          <h3>Business</h3>
          <div className="price">{formatPrice('business')}</div>
        </div>
        
        <div className="plan">
          <h3>Enterprise</h3>
          <div className="price">{formatPrice('enterprise')}</div>
        </div>
      </div>
    </div>
  );
}
```

## Verification

After deploying the fix, verify:

```bash
# Check API returns correct data
curl -H "Authorization: Bearer TOKEN" http://localhost:8000/billing/info

# Should see:
# - currency: "INR"
# - available_plans.growth.price: 2400 (not 29!)
```

## Need Help?

See full guide: `docs/billing/FRONTEND_INTEGRATION_GUIDE.md`

---

**Priority:** 🔴 CRITICAL  
**Time to Fix:** 5-10 minutes  
**Impact:** All non-USD users seeing wrong prices
