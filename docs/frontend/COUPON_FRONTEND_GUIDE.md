# Coupon / Promo Code — Frontend Integration Guide

## Overview

The Dari for Business Coupon System provides two sets of APIs:

1. **Merchant Dashboard APIs** — For merchants to create, manage, and track promo codes
2. **Checkout API** — For customers to apply coupons during payment

---

## Authentication

All merchant dashboard APIs require a **JWT Bearer token** in the `Authorization` header:

```
Authorization: Bearer <jwt_token>
```

The checkout coupon API (`apply-coupon`) is **public** (no auth required) but is **rate-limited** to 10 attempts per minute per IP.

---

## 1. Merchant Dashboard — Coupon Management

### 1.1 Create a Coupon

```
POST /api/business/promo/create
```

**Request Body:**

```json
{
  "code": "WELCOME10",
  "type": "percentage",
  "discount_value": 10,
  "max_discount_amount": 50,
  "min_order_amount": 100,
  "usage_limit_total": 1000,
  "usage_limit_per_user": 1,
  "start_date": "2026-03-01T00:00:00",
  "expiry_date": "2026-04-01T00:00:00"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `code` | string (2-50 chars) | ✅ | Unique coupon code (auto-uppercased) |
| `type` | `"percentage"` or `"fixed"` | ✅ | Discount type |
| `discount_value` | number (> 0) | ✅ | Discount value (% or fixed amount) |
| `max_discount_amount` | number | ❌ | Cap on percentage discount |
| `min_order_amount` | number | ❌ | Minimum order to apply (default: 0) |
| `usage_limit_total` | integer | ❌ | Max total uses (null = unlimited) |
| `usage_limit_per_user` | integer | ❌ | Max uses per customer (null = unlimited) |
| `start_date` | ISO datetime | ✅ | When coupon becomes valid |
| `expiry_date` | ISO datetime | ✅ | When coupon expires |

**Response (201):**

```json
{
  "id": "a1b2c3d4-...",
  "code": "WELCOME10",
  "type": "percentage",
  "discount_value": 10,
  "max_discount_amount": 50,
  "min_order_amount": 100,
  "usage_limit_total": 1000,
  "usage_limit_per_user": 1,
  "used_count": 0,
  "start_date": "2026-03-01T00:00:00",
  "expiry_date": "2026-04-01T00:00:00",
  "status": "active",
  "created_at": "2026-03-08T12:00:00",
  "updated_at": null
}
```

**Error Responses:**

| Code | Message |
|------|---------|
| 409 | Coupon code already exists |
| 400 | Expiry date must be after start date |
| 422 | Validation error (missing fields, invalid values) |

**React Example:**

```tsx
const createCoupon = async (couponData: CreateCouponPayload) => {
  const res = await fetch('/api/business/promo/create', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify(couponData),
  });

  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || 'Failed to create coupon');
  }

  return res.json();
};
```

---

### 1.2 List All Coupons

```
GET /api/business/promo/list?page=1&page_size=20&status=active
```

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `page` | integer | 1 | Page number |
| `page_size` | integer | 20 | Items per page (max 100) |
| `status` | string | — | Filter: `active` or `inactive` |

**Response:**

```json
{
  "promo_codes": [
    {
      "id": "a1b2c3d4-...",
      "code": "WELCOME10",
      "type": "percentage",
      "discount_value": 10,
      "max_discount_amount": 50,
      "min_order_amount": 100,
      "usage_limit_total": 1000,
      "usage_limit_per_user": 1,
      "used_count": 42,
      "start_date": "2026-03-01T00:00:00",
      "expiry_date": "2026-04-01T00:00:00",
      "status": "active",
      "created_at": "2026-03-08T12:00:00",
      "updated_at": "2026-03-08T15:00:00"
    }
  ],
  "total": 1
}
```

**React Example:**

```tsx
const fetchCoupons = async (page = 1, status?: string) => {
  const params = new URLSearchParams({ page: String(page), page_size: '20' });
  if (status) params.set('status', status);

  const res = await fetch(`/api/business/promo/list?${params}`, {
    headers: { 'Authorization': `Bearer ${token}` },
  });

  return res.json(); // { promo_codes: [...], total: number }
};
```

---

### 1.3 Edit a Coupon

```
PUT /api/business/promo/{coupon_id}
```

All fields are optional — only send what you want to change.

**Request Body:**

```json
{
  "discount_value": 15,
  "max_discount_amount": 75,
  "min_order_amount": 50,
  "usage_limit_total": 2000,
  "usage_limit_per_user": 2,
  "expiry_date": "2026-05-01T00:00:00",
  "status": "active"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `discount_value` | number | New discount value |
| `max_discount_amount` | number | New max discount cap |
| `min_order_amount` | number | New minimum order |
| `usage_limit_total` | integer | New total usage limit |
| `usage_limit_per_user` | integer | New per-user limit |
| `expiry_date` | ISO datetime | New expiry date |
| `status` | `"active"` or `"inactive"` | New status |

**Response:** Updated coupon object (same shape as create response).

**React Example:**

```tsx
const updateCoupon = async (couponId: string, updates: Partial<CouponData>) => {
  const res = await fetch(`/api/business/promo/${couponId}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify(updates),
  });

  if (!res.ok) throw new Error('Failed to update coupon');
  return res.json();
};
```

---

### 1.4 Delete a Coupon (Soft Delete)

```
DELETE /api/business/promo/{coupon_id}
```

**Response:**

```json
{
  "message": "Coupon deleted successfully"
}
```

The coupon is not removed from the database — it is marked as `"deleted"` and hidden from list results.

**React Example:**

```tsx
const deleteCoupon = async (couponId: string) => {
  const res = await fetch(`/api/business/promo/${couponId}`, {
    method: 'DELETE',
    headers: { 'Authorization': `Bearer ${token}` },
  });

  if (!res.ok) throw new Error('Failed to delete coupon');
  return res.json();
};
```

---

### 1.5 Enable / Disable a Coupon

```
PATCH /api/business/promo/{coupon_id}/status
```

**Request Body:**

```json
{
  "status": "inactive"
}
```

| Value | Description |
|-------|-------------|
| `"active"` | Coupon is live and usable |
| `"inactive"` | Coupon is paused (cannot be used) |

**Response:** Updated coupon object.

**React Example:**

```tsx
const toggleCouponStatus = async (couponId: string, active: boolean) => {
  const res = await fetch(`/api/business/promo/${couponId}/status`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify({ status: active ? 'active' : 'inactive' }),
  });

  return res.json();
};
```

---

### 1.6 Coupon Analytics

```
GET /api/business/promo/{coupon_id}/analytics
```

**Response:**

```json
{
  "promo_code_id": "a1b2c3d4-...",
  "code": "WELCOME10",
  "total_used": 42,
  "total_discount_given": 840.00,
  "revenue_generated": 7560.00,
  "conversion_rate": 95.24
}
```

| Field | Description |
|-------|-------------|
| `total_used` | Number of times the coupon was used |
| `total_discount_given` | Sum of all discounts applied (USD) |
| `revenue_generated` | Sum of paid payment amounts where this coupon was used |
| `conversion_rate` | % of coupon uses that resulted in a paid payment |

**React Example:**

```tsx
const fetchCouponAnalytics = async (couponId: string) => {
  const res = await fetch(`/api/business/promo/${couponId}/analytics`, {
    headers: { 'Authorization': `Bearer ${token}` },
  });

  return res.json();
};
```

---

## 2. Checkout Page — Apply Coupon

This API is called from the **customer-facing payment page** to validate and apply a coupon.

### 2.1 Apply Coupon

```
POST /api/payment/apply-coupon
```

**No authentication required** — rate limited to 10 attempts/minute per IP.

**Request Body:**

```json
{
  "merchant_id": "merchant-uuid-here",
  "payment_link_id": "link_abc123",
  "coupon_code": "WELCOME10",
  "order_amount": 200,
  "customer_id": "customer@email.com"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `merchant_id` | string | ✅ | Merchant UUID |
| `payment_link_id` | string | ❌ | Payment link ID (if applicable) |
| `coupon_code` | string | ✅ | Coupon code to validate |
| `order_amount` | number | ✅ | Original order amount |
| `customer_id` | string | ❌ | Customer email or ID (for per-user limits) |

**Success Response:**

```json
{
  "coupon_valid": true,
  "discount_amount": 20.00,
  "final_amount": 180.00,
  "coupon_code": "WELCOME10",
  "discount_type": "percentage",
  "message": "Coupon applied successfully"
}
```

**Failure Response:**

```json
{
  "coupon_valid": false,
  "discount_amount": 0,
  "final_amount": 200.00,
  "coupon_code": null,
  "discount_type": null,
  "message": "Coupon expired"
}
```

**Possible Error Messages:**

| Message | Meaning |
|---------|---------|
| `Invalid coupon code` | Code doesn't exist for this merchant |
| `Coupon is not active` | Merchant disabled this coupon |
| `Coupon is not yet valid` | Current date is before start_date |
| `Coupon expired` | Current date is past expiry_date |
| `Minimum order amount is X` | Order total is below min_order_amount |
| `Coupon usage limit reached` | Total global usage exhausted |
| `Coupon already used` | Per-user usage limit exceeded |

**Rate Limit Response (429):**

```json
{
  "detail": "Too many coupon attempts. Please try again later."
}
```

---

## 3. Frontend Implementation Examples

### 3.1 React — Coupon Input Component (Checkout Page)

```tsx
import { useState } from 'react';

interface CouponResult {
  coupon_valid: boolean;
  discount_amount: number;
  final_amount: number;
  coupon_code: string | null;
  discount_type: string | null;
  message: string;
}

interface CouponInputProps {
  merchantId: string;
  orderAmount: number;
  customerEmail?: string;
  onApplied: (result: CouponResult) => void;
}

export function CouponInput({ merchantId, orderAmount, customerEmail, onApplied }: CouponInputProps) {
  const [code, setCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<CouponResult | null>(null);

  const applyCoupon = async () => {
    if (!code.trim()) return;
    setLoading(true);

    try {
      const res = await fetch('/api/payment/apply-coupon', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          merchant_id: merchantId,
          coupon_code: code.trim(),
          order_amount: orderAmount,
          customer_id: customerEmail || undefined,
        }),
      });

      if (res.status === 429) {
        setResult({
          coupon_valid: false,
          discount_amount: 0,
          final_amount: orderAmount,
          coupon_code: null,
          discount_type: null,
          message: 'Too many attempts. Please wait a moment.',
        });
        return;
      }

      const data: CouponResult = await res.json();
      setResult(data);

      if (data.coupon_valid) {
        onApplied(data);
      }
    } catch {
      setResult({
        coupon_valid: false,
        discount_amount: 0,
        final_amount: orderAmount,
        coupon_code: null,
        discount_type: null,
        message: 'Network error. Please try again.',
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="coupon-section">
      <div className="coupon-input-row">
        <input
          type="text"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && applyCoupon()}
          placeholder="Enter promo code"
          maxLength={50}
          disabled={result?.coupon_valid || loading}
        />
        <button
          onClick={applyCoupon}
          disabled={!code.trim() || result?.coupon_valid || loading}
        >
          {loading ? '...' : result?.coupon_valid ? '✓ Applied' : 'Apply'}
        </button>
      </div>

      {result && (
        <div className={`coupon-message ${result.coupon_valid ? 'success' : 'error'}`}>
          {result.message}
        </div>
      )}

      {result?.coupon_valid && (
        <div className="discount-summary">
          <div className="discount-row">
            <span>Order Amount</span>
            <span>${orderAmount.toFixed(2)}</span>
          </div>
          <div className="discount-row highlight">
            <span>Discount ({result.coupon_code})</span>
            <span>-${result.discount_amount.toFixed(2)}</span>
          </div>
          <div className="discount-row total">
            <span>Total</span>
            <span>${result.final_amount.toFixed(2)}</span>
          </div>
        </div>
      )}
    </div>
  );
}
```

**Usage:**

```tsx
<CouponInput
  merchantId="your-merchant-uuid"
  orderAmount={200}
  customerEmail="customer@example.com"
  onApplied={(result) => {
    setFinalAmount(result.final_amount);
    setAppliedCoupon(result.coupon_code);
  }}
/>
```

---

### 3.2 React — Merchant Coupon Management Page

```tsx
import { useState, useEffect } from 'react';

interface PromoCode {
  id: string;
  code: string;
  type: 'percentage' | 'fixed';
  discount_value: number;
  max_discount_amount: number | null;
  min_order_amount: number;
  usage_limit_total: number | null;
  usage_limit_per_user: number | null;
  used_count: number;
  start_date: string;
  expiry_date: string;
  status: 'active' | 'inactive';
  created_at: string;
}

export function CouponManagement() {
  const [coupons, setCoupons] = useState<PromoCode[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [filter, setFilter] = useState<string>('');
  const [showCreate, setShowCreate] = useState(false);
  const token = localStorage.getItem('auth_token');

  const headers = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`,
  };

  // Fetch coupons
  const loadCoupons = async () => {
    const params = new URLSearchParams({ page: String(page), page_size: '20' });
    if (filter) params.set('status', filter);

    const res = await fetch(`/api/business/promo/list?${params}`, { headers });
    const data = await res.json();
    setCoupons(data.promo_codes);
    setTotal(data.total);
  };

  useEffect(() => { loadCoupons(); }, [page, filter]);

  // Toggle status
  const toggleStatus = async (id: string, currentStatus: string) => {
    const newStatus = currentStatus === 'active' ? 'inactive' : 'active';
    await fetch(`/api/business/promo/${id}/status`, {
      method: 'PATCH',
      headers,
      body: JSON.stringify({ status: newStatus }),
    });
    loadCoupons();
  };

  // Delete
  const deleteCoupon = async (id: string) => {
    if (!confirm('Delete this coupon?')) return;
    await fetch(`/api/business/promo/${id}`, { method: 'DELETE', headers });
    loadCoupons();
  };

  return (
    <div>
      <h1>Promo Codes</h1>

      <div className="toolbar">
        <button onClick={() => setShowCreate(true)}>+ Create Coupon</button>
        <select value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="">All</option>
          <option value="active">Active</option>
          <option value="inactive">Inactive</option>
        </select>
      </div>

      <table>
        <thead>
          <tr>
            <th>Code</th>
            <th>Type</th>
            <th>Discount</th>
            <th>Min Order</th>
            <th>Used</th>
            <th>Limit</th>
            <th>Expiry</th>
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {coupons.map((c) => (
            <tr key={c.id}>
              <td><code>{c.code}</code></td>
              <td>{c.type}</td>
              <td>
                {c.type === 'percentage'
                  ? `${c.discount_value}%${c.max_discount_amount ? ` (max $${c.max_discount_amount})` : ''}`
                  : `$${c.discount_value}`}
              </td>
              <td>${c.min_order_amount}</td>
              <td>{c.used_count}</td>
              <td>{c.usage_limit_total ?? '∞'}</td>
              <td>{new Date(c.expiry_date).toLocaleDateString()}</td>
              <td>
                <span className={`badge ${c.status}`}>{c.status}</span>
              </td>
              <td>
                <button onClick={() => toggleStatus(c.id, c.status)}>
                  {c.status === 'active' ? 'Disable' : 'Enable'}
                </button>
                <button onClick={() => deleteCoupon(c.id)}>Delete</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="pagination">
        <span>Total: {total}</span>
        <button disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button>
        <span>Page {page}</span>
        <button disabled={coupons.length < 20} onClick={() => setPage(page + 1)}>Next</button>
      </div>

      {showCreate && (
        <CreateCouponModal
          onClose={() => setShowCreate(false)}
          onCreated={() => { setShowCreate(false); loadCoupons(); }}
        />
      )}
    </div>
  );
}
```

---

### 3.3 React — Create Coupon Modal

```tsx
import { useState } from 'react';

interface CreateCouponModalProps {
  onClose: () => void;
  onCreated: () => void;
}

export function CreateCouponModal({ onClose, onCreated }: CreateCouponModalProps) {
  const token = localStorage.getItem('auth_token');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [form, setForm] = useState({
    code: '',
    type: 'percentage' as 'percentage' | 'fixed',
    discount_value: '',
    max_discount_amount: '',
    min_order_amount: '0',
    usage_limit_total: '',
    usage_limit_per_user: '',
    start_date: new Date().toISOString().slice(0, 16),
    expiry_date: '',
  });

  const updateField = (key: string, value: string) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    const body: Record<string, unknown> = {
      code: form.code,
      type: form.type,
      discount_value: parseFloat(form.discount_value),
      min_order_amount: parseFloat(form.min_order_amount) || 0,
      start_date: new Date(form.start_date).toISOString(),
      expiry_date: new Date(form.expiry_date).toISOString(),
    };

    if (form.max_discount_amount) body.max_discount_amount = parseFloat(form.max_discount_amount);
    if (form.usage_limit_total) body.usage_limit_total = parseInt(form.usage_limit_total);
    if (form.usage_limit_per_user) body.usage_limit_per_user = parseInt(form.usage_limit_per_user);

    try {
      const res = await fetch('/api/business/promo/create', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Failed to create coupon');
      }

      onCreated();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-overlay">
      <div className="modal-content">
        <h2>Create Coupon</h2>

        <form onSubmit={handleSubmit}>
          <label>
            Coupon Code
            <input
              type="text"
              value={form.code}
              onChange={(e) => updateField('code', e.target.value.toUpperCase())}
              placeholder="e.g. WELCOME10"
              maxLength={50}
              required
            />
          </label>

          <label>
            Discount Type
            <select value={form.type} onChange={(e) => updateField('type', e.target.value)}>
              <option value="percentage">Percentage (%)</option>
              <option value="fixed">Fixed Amount ($)</option>
            </select>
          </label>

          <label>
            Discount Value {form.type === 'percentage' ? '(%)' : '($)'}
            <input
              type="number"
              value={form.discount_value}
              onChange={(e) => updateField('discount_value', e.target.value)}
              min="0.01"
              max={form.type === 'percentage' ? '100' : undefined}
              step="0.01"
              required
            />
          </label>

          {form.type === 'percentage' && (
            <label>
              Max Discount Amount ($) — optional
              <input
                type="number"
                value={form.max_discount_amount}
                onChange={(e) => updateField('max_discount_amount', e.target.value)}
                min="0"
                step="0.01"
                placeholder="No cap"
              />
            </label>
          )}

          <label>
            Minimum Order Amount ($)
            <input
              type="number"
              value={form.min_order_amount}
              onChange={(e) => updateField('min_order_amount', e.target.value)}
              min="0"
              step="0.01"
            />
          </label>

          <label>
            Total Usage Limit — optional
            <input
              type="number"
              value={form.usage_limit_total}
              onChange={(e) => updateField('usage_limit_total', e.target.value)}
              min="1"
              placeholder="Unlimited"
            />
          </label>

          <label>
            Per-User Limit — optional
            <input
              type="number"
              value={form.usage_limit_per_user}
              onChange={(e) => updateField('usage_limit_per_user', e.target.value)}
              min="1"
              placeholder="Unlimited"
            />
          </label>

          <label>
            Start Date
            <input
              type="datetime-local"
              value={form.start_date}
              onChange={(e) => updateField('start_date', e.target.value)}
              required
            />
          </label>

          <label>
            Expiry Date
            <input
              type="datetime-local"
              value={form.expiry_date}
              onChange={(e) => updateField('expiry_date', e.target.value)}
              required
            />
          </label>

          {error && <div className="form-error">{error}</div>}

          <div className="modal-actions">
            <button type="button" onClick={onClose}>Cancel</button>
            <button type="submit" disabled={loading}>
              {loading ? 'Creating...' : 'Create Coupon'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
```

---

### 3.4 React — Coupon Analytics Card

```tsx
import { useState, useEffect } from 'react';

interface Analytics {
  code: string;
  total_used: number;
  total_discount_given: number;
  revenue_generated: number;
  conversion_rate: number | null;
}

export function CouponAnalyticsCard({ couponId }: { couponId: string }) {
  const [data, setData] = useState<Analytics | null>(null);
  const token = localStorage.getItem('auth_token');

  useEffect(() => {
    fetch(`/api/business/promo/${couponId}/analytics`, {
      headers: { 'Authorization': `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then(setData);
  }, [couponId]);

  if (!data) return <div>Loading...</div>;

  return (
    <div className="analytics-card">
      <h3>{data.code} — Analytics</h3>
      <div className="stats-grid">
        <div className="stat">
          <div className="stat-value">{data.total_used}</div>
          <div className="stat-label">Times Used</div>
        </div>
        <div className="stat">
          <div className="stat-value">${data.total_discount_given.toFixed(2)}</div>
          <div className="stat-label">Total Discount Given</div>
        </div>
        <div className="stat">
          <div className="stat-value">${data.revenue_generated.toFixed(2)}</div>
          <div className="stat-label">Revenue Generated</div>
        </div>
        <div className="stat">
          <div className="stat-value">
            {data.conversion_rate !== null ? `${data.conversion_rate}%` : 'N/A'}
          </div>
          <div className="stat-label">Conversion Rate</div>
        </div>
      </div>
    </div>
  );
}
```

---

## 4. TypeScript Types

```ts
// ── Request Types ──

interface CreateCouponPayload {
  code: string;
  type: 'percentage' | 'fixed';
  discount_value: number;
  max_discount_amount?: number;
  min_order_amount?: number;
  usage_limit_total?: number;
  usage_limit_per_user?: number;
  start_date: string; // ISO datetime
  expiry_date: string; // ISO datetime
}

interface UpdateCouponPayload {
  discount_value?: number;
  max_discount_amount?: number;
  min_order_amount?: number;
  usage_limit_total?: number;
  usage_limit_per_user?: number;
  expiry_date?: string;
  status?: 'active' | 'inactive';
}

interface ApplyCouponPayload {
  merchant_id: string;
  payment_link_id?: string;
  coupon_code: string;
  order_amount: number;
  customer_id?: string;
}

// ── Response Types ──

interface PromoCode {
  id: string;
  code: string;
  type: 'percentage' | 'fixed';
  discount_value: number;
  max_discount_amount: number | null;
  min_order_amount: number;
  usage_limit_total: number | null;
  usage_limit_per_user: number | null;
  used_count: number;
  start_date: string;
  expiry_date: string;
  status: 'active' | 'inactive';
  created_at: string;
  updated_at: string | null;
}

interface PromoCodeList {
  promo_codes: PromoCode[];
  total: number;
}

interface ApplyCouponResult {
  coupon_valid: boolean;
  discount_amount: number;
  final_amount: number;
  coupon_code: string | null;
  discount_type: 'percentage' | 'fixed' | null;
  message: string;
}

interface PromoCodeAnalytics {
  promo_code_id: string;
  code: string;
  total_used: number;
  total_discount_given: number;
  revenue_generated: number;
  conversion_rate: number | null;
}
```

---

## 5. API Service Helper (api.ts)

```ts
const API_BASE = ''; // Same origin

async function apiCall<T>(path: string, options?: RequestInit): Promise<T> {
  const token = localStorage.getItem('auth_token');
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
      ...options?.headers,
    },
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }

  return res.json();
}

// ── Merchant Coupon APIs ──

export const promoApi = {
  create: (data: CreateCouponPayload) =>
    apiCall<PromoCode>('/api/business/promo/create', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  list: (page = 1, pageSize = 20, status?: string) => {
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (status) params.set('status', status);
    return apiCall<PromoCodeList>(`/api/business/promo/list?${params}`);
  },

  update: (id: string, data: UpdateCouponPayload) =>
    apiCall<PromoCode>(`/api/business/promo/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  delete: (id: string) =>
    apiCall<{ message: string }>(`/api/business/promo/${id}`, { method: 'DELETE' }),

  toggleStatus: (id: string, status: 'active' | 'inactive') =>
    apiCall<PromoCode>(`/api/business/promo/${id}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    }),

  analytics: (id: string) =>
    apiCall<PromoCodeAnalytics>(`/api/business/promo/${id}/analytics`),
};

// ── Checkout Coupon API (no auth) ──

export const couponApi = {
  apply: (data: ApplyCouponPayload) =>
    apiCall<ApplyCouponResult>('/api/payment/apply-coupon', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
};
```

---

## 6. Hosted Checkout (Built-in)

The hosted checkout pages (`checkout.html` and `checkout_multichain.html`) already have a built-in coupon input field. When a customer loads the checkout page:

1. A **"Have a promo code?"** toggle appears below the price summary
2. Clicking it expands a code input + Apply button
3. On apply, it calls `POST /api/payment/apply-coupon` with the `merchant_id` from the session
4. On success, the displayed price updates to show the discount
5. The input locks to prevent re-entry
6. **If the coupon gives a 100% discount** (final amount = $0), the payment is automatically completed via `POST /api/payment/complete-coupon-payment` — no blockchain payment needed. The session is marked as `paid` with `tx_hash` set to `coupon:<CODE>`.

No frontend changes needed if you use Dari's hosted checkout.

---

## 7. 100% Discount (Auto-Complete) API

When a coupon covers the full order amount (final_amount = 0), call this endpoint to complete the payment without requiring a blockchain transaction.

### 7.1 Complete Coupon Payment

```
POST /api/payment/complete-coupon-payment
```

**No authentication required** — rate limited same as apply-coupon.

**Request Body:**

```json
{
  "session_id": "pay_abc123",
  "coupon_code": "FREE100"
}
```

**Success Response:**

```json
{
  "status": "paid",
  "message": "Payment completed with coupon (100% discount)",
  "session_id": "pay_abc123",
  "coupon_code": "FREE100"
}
```

**Error Responses:**

| Code | Message |
|------|---------|
| 400 | `session_id and coupon_code are required` |
| 400 | `Payment session expired` |
| 400 | `Coupon does not cover full amount. Blockchain payment still required.` |
| 400 | Any coupon validation error (expired, inactive, etc.) |
| 404 | `Payment session not found` |

**React Example:**

```tsx
const completeCouponPayment = async (sessionId: string, couponCode: string) => {
  const res = await fetch('/api/payment/complete-coupon-payment', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, coupon_code: couponCode }),
  });

  const data = await res.json();
  if (data.status === 'paid') {
    // Payment completed! Redirect to success page
    window.location.href = successUrl;
  }
};
```

---

## 8. Coupon Tracking in Transactions

When a coupon is applied to a payment session, the following fields are stored on the `payment_sessions` table:

| Field | Type | Description |
|-------|------|-------------|
| `coupon_code` | string | The coupon code that was applied |
| `discount_amount` | number | The discount amount in fiat currency |

These fields are available in:
- `GET /public/session/{session_id}/verify` response (includes `coupon_code` and `discount_amount`)
- The `tx_hash` for 100% coupon payments is set to `coupon:<CODE>` (e.g., `coupon:FREE100`)

### Transaction List Coupon Breakdown

All transaction listing endpoints (`GET /merchant/payments`, `/merchant/payments/recent`, `/merchant/payments/payer-leads`, and admin `/admin/payments`) now include coupon breakdown fields:

| Field | Type | Description |
|-------|------|-------------|
| `coupon_code` | string \| null | Coupon code applied (null if none) |
| `discount_amount` | number \| null | Discount amount from the coupon |
| `amount_paid` | number \| null | Actual amount paid by customer (`amount_fiat - discount_amount`) |

**Example response (transaction with coupon):**

```json
{
  "id": "pay_abc123",
  "amount_fiat": 100.00,
  "fiat_currency": "USD",
  "coupon_code": "SAVE50",
  "discount_amount": 50.00,
  "amount_paid": 50.00,
  "status": "paid",
  ...
}
```

**Example response (transaction without coupon):**

```json
{
  "id": "pay_xyz456",
  "amount_fiat": 75.00,
  "fiat_currency": "USD",
  "coupon_code": null,
  "discount_amount": null,
  "amount_paid": null,
  "status": "paid",
  ...
}
```

### Payment Stats Coupon Summary

`GET /merchant/payments/stats` response now includes coupon metrics in the `revenue` object:

```json
{
  "revenue": {
    "total_usdc": 5000.00,
    "currency": "USDC",
    "total_coupon_discount": 350.00,
    "coupon_payment_count": 12
  }
}
```

### Billing Volume Tracking

Coupon discounts are **counted toward transaction volume**. The **full original order amount** (before any coupon discount) counts toward the merchant's monthly volume limit. For example:

- Order: $100, Coupon: $30 off → **$100** counts toward volume
- Order: $50, Coupon: 100% off → **$50** counts toward volume

This ensures merchants cannot circumvent volume limits with coupons.

### DB Migration

Run [migrations/coupon_tracking.sql](../migrations/coupon_tracking.sql) after `promo_codes.sql`:

```sql
ALTER TABLE payment_sessions
    ADD COLUMN IF NOT EXISTS coupon_code VARCHAR(50),
    ADD COLUMN IF NOT EXISTS discount_amount NUMERIC(14, 2);
```

---

## 9. Notes

- Coupon codes are **case-insensitive** — `welcome10` and `WELCOME10` are the same code
- Coupon codes are **merchant-scoped** — Merchant A's coupon cannot be used on Merchant B's checkout
- The `customer_id` field is used for per-user limit enforcement. Pass the customer's email for best results
- After a successful payment, coupon usage is recorded and `used_count` is incremented server-side
- Deleted coupons are soft-deleted and cannot be reused or seen in the list
