# Complete API Endpoints Reference for Frontend

This document lists ALL backend API endpoints with their exact URL patterns for frontend integration.

---

## Base URL
```
http://localhost:8000
```

---

## 1. Authentication (`/auth`)

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| POST | `/auth/register` | Register new merchant | No |
| POST | `/auth/login` | Login merchant | No |
| POST | `/auth/google` | Google OAuth login | No |
| GET | `/auth/google/callback` | Google OAuth callback | No |
| POST | `/auth/refresh` | Refresh access token | Yes |
| GET | `/auth/me` | Get current user | Yes |

---

## 2. Merchant Profile (`/merchant`)

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/merchant/profile` | Get merchant profile | Yes |
| PUT | `/merchant/profile` | Update merchant profile | Yes |
| GET | `/merchant/api-key` | Get API key | Yes |
| POST | `/merchant/api-key/regenerate` | Regenerate API key | Yes |

---

## 3. Merchant Wallets (`/merchant/wallets`)

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/merchant/wallets` | List all wallets | Yes |
| GET | `/merchant/wallets/dashboard` | Get balance dashboard | Yes |
| POST | `/merchant/wallets` | Add new wallet | Yes |
| GET | `/merchant/wallets/{chain}` | Get wallet by chain | Yes |
| DELETE | `/merchant/wallets/{chain}` | Delete wallet | Yes |

**Frontend Fix:**
```javascript
// ❌ Wrong
GET /merchant/wallets/dashboard

// ✅ Correct
GET /merchant/wallets/dashboard
// This endpoint exists! Check authentication headers
```

---

## 4. Payment Sessions (`/v1/payment_sessions`)

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| POST | `/v1/payment_sessions` | Create payment session | API Key |
| GET | `/v1/payment_sessions/{session_id}` | Get session status | API Key |

---

## 5. Merchant Payments (`/merchant/payments`)

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/merchant/payments` | List all payments | Yes |
| GET | `/merchant/payments/{session_id}` | Get payment details | Yes |
| GET | `/merchant/payments/stats` | Get payment statistics | Yes |

---

## 6. Payment Links (`/payment-links`)

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/payment-links` | List payment links | Yes |
| POST | `/payment-links` | Create payment link | Yes |
| GET | `/payment-links/{link_id}` | Get payment link | Yes |
| PUT | `/payment-links/{link_id}` | Update payment link | Yes |
| DELETE | `/payment-links/{link_id}` | Delete payment link | Yes |
| PATCH | `/payment-links/{link_id}/toggle` | Toggle active status | Yes |

**Frontend Fix:**
```javascript
// ❌ Wrong
GET /payment-links?page=1&page_size=20

// ✅ Correct - Add Authorization header
GET /payment-links?page=1&page_size=20
Headers: {
  'Authorization': 'Bearer YOUR_JWT_TOKEN'
}
```

---

## 7. Invoices (`/invoices`)

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/invoices` | List invoices | Yes |
| POST | `/invoices` | Create invoice | Yes |
| GET | `/invoices/{invoice_id}` | Get invoice | Yes |
| PUT | `/invoices/{invoice_id}` | Update invoice | Yes |
| DELETE | `/invoices/{invoice_id}` | Delete invoice | Yes |
| POST | `/invoices/{invoice_id}/send` | Send invoice | Yes |
| POST | `/invoices/{invoice_id}/mark-paid` | Mark as paid | Yes |

---

## 8. Subscriptions (Traditional) (`/subscriptions`)

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/subscriptions` | List subscriptions | Yes |
| POST | `/subscriptions` | Create subscription | Yes |
| GET | `/subscriptions/{sub_id}` | Get subscription | Yes |
| PUT | `/subscriptions/{sub_id}` | Update subscription | Yes |
| DELETE | `/subscriptions/{sub_id}` | Cancel subscription | Yes |
| GET | `/subscriptions/plans` | List subscription plans | Yes |
| POST | `/subscriptions/plans` | Create plan | Yes |
| GET | `/subscriptions/plans/{plan_id}` | Get plan | Yes |
| PUT | `/subscriptions/plans/{plan_id}` | Update plan | Yes |
| DELETE | `/subscriptions/plans/{plan_id}` | Delete plan | Yes |

**Frontend Fix:**
```javascript
// ❌ Wrong
GET /subscriptions?page=1&page_size=20
GET /subscriptions/plans?page=1&page_size=20

// ✅ Correct - Add Authorization header
GET /subscriptions?page=1&page_size=20
GET /subscriptions/plans?page=1&page_size=20
Headers: {
  'Authorization': 'Bearer YOUR_JWT_TOKEN'
}
```

---

## 9. Web3 Subscriptions (`/web3-subscriptions`)

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| POST | `/web3-subscriptions/mandate/signing-data` | Get EIP-712 signing data | No |
| POST | `/web3-subscriptions/authorize` | Create Web3 subscription | No |
| GET | `/web3-subscriptions` | List merchant subscriptions | Yes |
| GET | `/web3-subscriptions/analytics` | Get analytics | Yes |
| GET | `/web3-subscriptions/{sub_id}` | Get subscription | Yes |
| POST | `/web3-subscriptions/{sub_id}/cancel` | Cancel subscription | Yes |
| GET | `/web3-subscriptions/{sub_id}/payments` | List payments | Yes |
| GET | `/web3-subscriptions/user/{address}` | Get user subscriptions | No |
| POST | `/web3-subscriptions/user/cancel` | User cancel subscription | No |
| GET | `/web3-subscriptions/admin/relayer-status` | Get relayer status | Yes |
| GET | `/web3-subscriptions/admin/scheduler-status` | Get scheduler status | Yes |
| GET | `/web3-subscriptions/admin/health/{sub_id}` | Health check | Yes |

---

## 10. Promo Codes / Coupons (`/api/business/promo`)

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| POST | `/api/business/promo/create` | Create coupon | Yes |
| GET | `/api/business/promo/list` | List coupons | Yes |
| PUT | `/api/business/promo/{coupon_id}` | Update coupon | Yes |
| DELETE | `/api/business/promo/{coupon_id}` | Delete coupon | Yes |
| PATCH | `/api/business/promo/{coupon_id}/status` | Toggle status | Yes |
| GET | `/api/business/promo/{coupon_id}/analytics` | Get analytics | Yes |

**Frontend Fix:**
```javascript
// ❌ Wrong
GET /api/business/promo/list?page=1&page_size=20

// ✅ Correct - Add Authorization header
GET /api/business/promo/list?page=1&page_size=20
Headers: {
  'Authorization': 'Bearer YOUR_JWT_TOKEN'
}
```

---

## 11. Refunds (`/refunds`)

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/refunds` | List refunds | Yes |
| POST | `/refunds` | Create refund | Yes |
| GET | `/refunds/{refund_id}` | Get refund | Yes |
| POST | `/refunds/{refund_id}/approve` | Approve refund | Yes |
| POST | `/refunds/{refund_id}/reject` | Reject refund | Yes |

---

## 12. Withdrawals (`/withdrawals`)

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/withdrawals/balance` | Get withdrawal balance | Yes |
| GET | `/withdrawals/limits` | Get withdrawal limits | Yes |
| POST | `/withdrawals` | Create withdrawal | Yes |
| GET | `/withdrawals` | List withdrawals | Yes |
| GET | `/withdrawals/{withdrawal_id}` | Get withdrawal | Yes |
| POST | `/withdrawals/{withdrawal_id}/cancel` | Cancel withdrawal | Yes |

---

## 13. Analytics (`/analytics`)

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/analytics/overview` | Get overview | Yes |
| GET | `/analytics/revenue` | Get revenue data | Yes |
| GET | `/analytics/payments` | Get payment stats | Yes |
| GET | `/analytics/subscriptions` | Get subscription stats | Yes |
| GET | `/analytics/export` | Export data | Yes |

---

## 14. Team Management (`/team`)

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| POST | `/team/invite` | Invite team member | Yes |
| GET | `/team` | List team members | Yes |
| GET | `/team/{member_id}` | Get team member | Yes |
| PATCH | `/team/{member_id}` | Update team member | Yes |
| DELETE | `/team/{member_id}` | Remove team member | Yes |
| POST | `/team/{member_id}/resend-invite` | Resend invite | Yes |
| GET | `/team/roles/permissions` | List role permissions | Yes |
| POST | `/team/accept-invite` | Accept invite | No |

---

## 15. Merchant Subscription Management (`/subscription`)

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/subscription/plans` | Get subscription plans | No |
| GET | `/subscription/current` | Get current subscription | Yes |
| GET | `/subscription/usage` | Get usage stats | Yes |
| POST | `/subscription/upgrade` | Upgrade subscription | Yes |
| POST | `/subscription/cancel` | Cancel subscription | Yes |
| POST | `/subscription/reactivate` | Reactivate subscription | Yes |

---

## 16. Onboarding (`/onboarding`)

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| POST | `/onboarding/start` | Start onboarding | Yes |
| POST | `/onboarding/business-details` | Submit business details | Yes |
| POST | `/onboarding/wallets` | Add wallets | Yes |
| POST | `/onboarding/complete` | Complete onboarding | Yes |
| GET | `/onboarding/status` | Get onboarding status | Yes |

---

## 17. Tax Reports (`/tax-reports`)

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/tax-reports/summary` | Get tax summary | Yes |
| GET | `/tax-reports/transactions` | Get transaction report | Yes |
| GET | `/tax-reports/subscription-revenue` | Get subscription revenue | Yes |

---

## 18. Admin (`/admin`)

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/admin/merchants` | List merchants | Admin |
| GET | `/admin/merchants/{merchant_id}` | Get merchant | Admin |
| POST | `/admin/merchants/{merchant_id}/disable` | Disable merchant | Admin |
| GET | `/admin/payments` | List all payments | Admin |
| GET | `/admin/stats` | Get platform stats | Admin |

---

## Common Issues & Fixes

### Issue 1: 404 Not Found

**Cause:** Missing Authorization header

**Fix:**
```javascript
// Add JWT token to all authenticated requests
const headers = {
  'Authorization': `Bearer ${localStorage.getItem('token')}`,
  'Content-Type': 'application/json'
};

fetch('http://localhost:8000/subscriptions', { headers })
```

---

### Issue 2: CORS Errors

**Cause:** Frontend origin not in CORS_ORIGINS

**Fix in .env:**
```bash
CORS_ORIGINS=http://localhost:3000,http://localhost:8000,https://yourdomain.com
```

---

### Issue 3: Endpoint Not Found

**Cause:** Wrong URL pattern

**Common Mistakes:**
```javascript
// ❌ Wrong
GET /api/subscriptions          // Missing /subscriptions prefix
GET /merchant-wallets/dashboard // Wrong prefix
GET /promo/list                 // Missing /api/business prefix

// ✅ Correct
GET /subscriptions
GET /merchant/wallets/dashboard
GET /api/business/promo/list
```

---

## Authentication Flow

### 1. Login
```javascript
POST /auth/login
Body: {
  "email": "merchant@example.com",
  "password": "password123"
}

Response: {
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "token_type": "bearer",
  "merchant": { ... }
}
```

### 2. Store Token
```javascript
localStorage.setItem('token', response.access_token);
```

### 3. Use Token in Requests
```javascript
const token = localStorage.getItem('token');
const headers = {
  'Authorization': `Bearer ${token}`,
  'Content-Type': 'application/json'
};

fetch('http://localhost:8000/merchant/profile', { headers })
```

---

## API Client Example (JavaScript)

```javascript
class DariAPI {
  constructor(baseURL = 'http://localhost:8000') {
    this.baseURL = baseURL;
  }

  getHeaders() {
    const token = localStorage.getItem('token');
    return {
      'Content-Type': 'application/json',
      ...(token && { 'Authorization': `Bearer ${token}` })
    };
  }

  async request(endpoint, options = {}) {
    const url = `${this.baseURL}${endpoint}`;
    const config = {
      ...options,
      headers: {
        ...this.getHeaders(),
        ...options.headers
      }
    };

    const response = await fetch(url, config);
    
    if (!response.ok) {
      throw new Error(`API Error: ${response.status}`);
    }

    return response.json();
  }

  // Auth
  async login(email, password) {
    return this.request('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password })
    });
  }

  // Subscriptions
  async getSubscriptions(page = 1, pageSize = 20) {
    return this.request(`/subscriptions?page=${page}&page_size=${pageSize}`);
  }

  async getSubscriptionPlans(page = 1, pageSize = 20) {
    return this.request(`/subscriptions/plans?page=${page}&page_size=${pageSize}`);
  }

  // Payment Links
  async getPaymentLinks(page = 1, pageSize = 20) {
    return this.request(`/payment-links?page=${page}&page_size=${pageSize}`);
  }

  // Promo Codes
  async getPromoCodes(page = 1, pageSize = 20) {
    return this.request(`/api/business/promo/list?page=${page}&page_size=${pageSize}`);
  }

  // Wallets
  async getWalletDashboard() {
    return this.request('/merchant/wallets/dashboard');
  }

  // Web3 Subscriptions
  async getWeb3Subscriptions(status = null) {
    const query = status ? `?status=${status}` : '';
    return this.request(`/web3-subscriptions${query}`);
  }

  async getSchedulerStatus() {
    return this.request('/web3-subscriptions/admin/scheduler-status');
  }
}

// Usage
const api = new DariAPI();

// Login
const { access_token } = await api.login('merchant@example.com', 'password');
localStorage.setItem('token', access_token);

// Get data
const subscriptions = await api.getSubscriptions();
const plans = await api.getSubscriptionPlans();
const promos = await api.getPromoCodes();
const dashboard = await api.getWalletDashboard();
```

---

## Testing Endpoints

### Using cURL (PowerShell)

```powershell
# Login
$response = curl -X POST http://localhost:8000/auth/login `
  -H "Content-Type: application/json" `
  -d '{"email":"merchant@example.com","password":"password"}' | ConvertFrom-Json

$token = $response.access_token

# Get subscriptions
curl http://localhost:8000/subscriptions `
  -H "Authorization: Bearer $token"

# Get payment links
curl http://localhost:8000/payment-links `
  -H "Authorization: Bearer $token"

# Get promo codes
curl http://localhost:8000/api/business/promo/list `
  -H "Authorization: Bearer $token"

# Get wallet dashboard
curl http://localhost:8000/merchant/wallets/dashboard `
  -H "Authorization: Bearer $token"
```

---

## Environment Variables for Frontend

```javascript
// .env.local (React/Next.js)
REACT_APP_API_URL=http://localhost:8000
REACT_APP_API_TIMEOUT=30000

// .env (Vue/Nuxt)
VUE_APP_API_URL=http://localhost:8000
VUE_APP_API_TIMEOUT=30000

// .env (Angular)
NG_APP_API_URL=http://localhost:8000
NG_APP_API_TIMEOUT=30000
```

---

## Quick Reference: Most Common Endpoints

```
Authentication:
  POST /auth/login
  POST /auth/register
  GET  /auth/me

Merchant:
  GET  /merchant/profile
  GET  /merchant/wallets/dashboard

Subscriptions:
  GET  /subscriptions
  GET  /subscriptions/plans
  POST /subscriptions

Web3 Subscriptions:
  GET  /web3-subscriptions
  GET  /web3-subscriptions/admin/scheduler-status

Payment Links:
  GET  /payment-links
  POST /payment-links

Promo Codes:
  GET  /api/business/promo/list
  POST /api/business/promo/create

Analytics:
  GET  /analytics/overview
```

---

## Support

For issues:
1. Check Authorization header is included
2. Verify token is valid (not expired)
3. Check endpoint URL matches exactly
4. Verify request body format
5. Check CORS settings in backend .env

---

**Last Updated:** 2026-03-29  
**Backend Version:** 2.2.0  
**API Documentation:** http://localhost:8000/docs
