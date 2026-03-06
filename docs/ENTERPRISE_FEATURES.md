# Dari for Business - Enterprise Features Documentation

**Version 2.0.0** | Last Updated: March 4, 2026

This document provides comprehensive documentation for all enterprise features added to Dari for Business, bringing the platform to feature parity with Stripe, Coinbase Commerce, and other leading payment processors.

---

## Table of Contents

1. [Overview](#overview)
2. [Payment Links](#payment-links)
3. [Invoice System](#invoice-system)
4. [Subscriptions & Recurring Payments](#subscriptions--recurring-payments)
5. [Refund Processing](#refund-processing)
6. [Merchant Analytics](#merchant-analytics)
7. [Team Management](#team-management)
8. [Idempotency Keys](#idempotency-keys)
9. [Event Queue & Webhooks](#event-queue--webhooks)
10. [Database Schema](#database-schema)
11. [Migration Guide](#migration-guide)
12. [Integration Examples](#integration-examples)

---

## Overview

The enterprise feature set adds 46 new API endpoints, 14 new database models, and comprehensive business logic to support:

- **Reusable payment links** for social media, email, and website sharing
- **Professional invoicing** with line items, due dates, and automated reminders
- **Subscription billing** with plans, trials, and flexible billing cycles
- **Refund management** for full and partial refunds
- **Analytics dashboard** with real-time metrics and reports
- **Multi-user teams** with role-based permissions
- **API reliability** through idempotency keys and event queuing

### Key Benefits

✅ **Stripe-level UX** - Match the developer experience of leading payment platforms  
✅ **Multi-chain** - All features work across Stellar, Ethereum, Polygon, Base, Tron  
✅ **Production-ready** - Full error handling, retry logic, and webhook delivery  
✅ **Scalable** - Async event processing and optimized database queries  

---

## Payment Links

Payment Links allow merchants to create reusable, shareable URLs for accepting payments. Perfect for social media, email campaigns, or embedding on websites.

### Features

- **Fixed or variable amounts** - Set specific prices or let customers enter amounts
- **Multi-token support** - Accept multiple cryptocurrencies per link
- **Single-use links** - Optionally deactivate after first payment
- **Expiration dates** - Time-limited payment links
- **Analytics tracking** - View counts, conversion rates, total collected
- **Custom URLs** - Success/cancel redirect URLs

### API Endpoints

#### Create Payment Link
```http
POST /payment-links
Authorization: Bearer {jwt_token}
X-API-Key: {api_key}

{
  "name": "Monthly Subscription",
  "description": "Premium membership access",
  "amount_fiat": 29.99,
  "fiat_currency": "USD",
  "is_amount_fixed": true,
  "accepted_tokens": ["USDC", "USDT"],
  "accepted_chains": ["polygon", "stellar"],
  "success_url": "https://yoursite.com/success",
  "cancel_url": "https://yoursite.com/cancel",
  "is_single_use": false,
  "expires_at": "2026-12-31T23:59:59Z"
}
```

**Response:**
```json
{
  "id": "link_abc123xyz",
  "checkout_url": "https://api.dariforbusiness.com/pay/link_abc123xyz",
  "name": "Monthly Subscription",
  "amount_fiat": 29.99,
  "fiat_currency": "USD",
  "is_active": true,
  "view_count": 0,
  "payment_count": 0,
  "total_collected_usd": 0,
  "created_at": "2026-03-04T19:30:00Z"
}
```

#### List Payment Links
```http
GET /payment-links?page=1&page_size=20&is_active=true
```

#### Get Payment Link
```http
GET /payment-links/{link_id}
```

#### Update Payment Link
```http
PATCH /payment-links/{link_id}

{
  "name": "Updated Name",
  "is_active": false
}
```

#### Deactivate Payment Link
```http
DELETE /payment-links/{link_id}
```

#### Get Link Analytics
```http
GET /payment-links/{link_id}/analytics
```

**Response:**
```json
{
  "link_id": "link_abc123xyz",
  "views": 1247,
  "payments": 89,
  "conversion_rate": 7.14,
  "total_collected_usd": 2663.11,
  "recent_payments": [...]
}
```

### Use Cases

1. **Social Media Sales** - Share payment link in Instagram bio or Twitter
2. **Email Campaigns** - Include in newsletters for easy checkout
3. **Donation Buttons** - Variable amount links for fundraising
4. **Quick Sales** - One-click payment for digital products

### Code Example

```javascript
// Create a payment link
const response = await fetch('https://api.dariforbusiness.com/payment-links', {
  method: 'POST',
  headers: {
    'X-API-Key': 'your_api_key',
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    name: 'Digital Course',
    description: 'Complete Web3 Development Course',
    amount_fiat: 99.00,
    fiat_currency: 'USD',
    accepted_tokens: ['USDC'],
    accepted_chains: ['polygon']
  })
});

const link = await response.json();
console.log('Share this link:', link.checkout_url);
```

---

## Invoice System

Professional invoice management with line items, due dates, automated reminders, and payment tracking.

### Features

- **Line items** - Detailed itemization with quantities and unit prices
- **Tax & discounts** - Automatic total calculation
- **Draft mode** - Save invoices before sending
- **Email delivery** - Send invoices directly to customers
- **Payment reminders** - Automated overdue notifications
- **Status tracking** - DRAFT → SENT → VIEWED → PAID → OVERDUE
- **Payment links** - Each invoice generates a unique payment URL
- **Multi-format export** - PDF, JSON (future: CSV)

### Invoice Lifecycle

```
DRAFT → SENT → VIEWED → PAID
         ↓
      OVERDUE → PAID
         ↓
     CANCELLED
```

### API Endpoints

#### Create Invoice
```http
POST /invoices

{
  "customer_email": "customer@example.com",
  "customer_name": "John Smith",
  "customer_address": "123 Main St, City, State 12345",
  "description": "Professional Services - February 2026",
  "line_items": [
    {
      "description": "Web Development - 40 hours",
      "quantity": 40,
      "unit_price": 100.00
    },
    {
      "description": "Design Services - 10 hours",
      "quantity": 10,
      "unit_price": 80.00
    }
  ],
  "tax": 450.00,
  "discount": 0,
  "due_date": "2026-04-01T00:00:00Z",
  "accepted_tokens": ["USDC", "USDT"],
  "accepted_chains": ["polygon", "ethereum"],
  "notes": "Payment due within 30 days",
  "terms": "Net 30",
  "send_immediately": true
}
```

**Response:**
```json
{
  "id": "inv_xyz789",
  "invoice_number": "INV-0001",
  "customer_email": "customer@example.com",
  "line_items": [...],
  "subtotal": 4800.00,
  "tax": 450.00,
  "discount": 0,
  "total": 5250.00,
  "fiat_currency": "USD",
  "status": "sent",
  "issue_date": "2026-03-04T19:30:00Z",
  "due_date": "2026-04-01T00:00:00Z",
  "payment_url": "https://api.dariforbusiness.com/invoice/inv_xyz789/pay",
  "created_at": "2026-03-04T19:30:00Z"
}
```

#### List Invoices
```http
GET /invoices?page=1&page_size=20&status=sent&customer_email=customer@example.com
```

#### Get Invoice
```http
GET /invoices/{invoice_id}
```

#### Update Invoice (Draft Only)
```http
PATCH /invoices/{invoice_id}

{
  "description": "Updated description",
  "due_date": "2026-04-15T00:00:00Z"
}
```

#### Send Invoice
```http
POST /invoices/{invoice_id}/send

{
  "message": "Thank you for your business!"
}
```

#### Send Reminder
```http
POST /invoices/{invoice_id}/remind
```

#### Cancel Invoice
```http
POST /invoices/{invoice_id}/cancel
```

#### Duplicate Invoice
```http
POST /invoices/{invoice_id}/duplicate
```

### Automated Features

**Overdue Detection:**
- System automatically marks invoices as OVERDUE when past due date
- Configurable reminder schedule (default: 7 days before, day of, 3 days after)

**Status Updates:**
- VIEWED status triggered when customer opens payment link
- PAID status triggered when payment is confirmed
- Webhook events sent for all status changes

### Code Example

```python
import requests

# Create and send invoice
invoice = {
    "customer_email": "client@company.com",
    "line_items": [
        {"description": "Consulting Services", "quantity": 20, "unit_price": 150.00}
    ],
    "due_date": "2026-04-01T00:00:00Z",
    "send_immediately": True
}

response = requests.post(
    'https://api.dariforbusiness.com/invoices',
    headers={'X-API-Key': 'your_api_key'},
    json=invoice
)

invoice_data = response.json()
print(f"Invoice sent: {invoice_data['payment_url']}")
```

---

## Subscriptions & Recurring Payments

Flexible subscription billing with plans, trials, and automated recurring payments.

### Architecture

**Two-tier system:**
1. **Subscription Plans** - Templates defining pricing and billing cycle
2. **Subscriptions** - Customer enrollments in plans

### Features

- **Flexible billing intervals** - Daily, weekly, monthly, quarterly, yearly
- **Trial periods** - Free trial before first charge
- **Pause/resume** - Temporary subscription suspension
- **Cancellation** - Immediate or at period end
- **Payment retry** - Automatic retry on failed payments
- **Proration** - (Future) Mid-cycle changes
- **Multiple plans** - Tiered pricing (Basic, Pro, Enterprise)

### Subscription States

```
TRIALING → ACTIVE → PAUSED → ACTIVE
                ↓       ↓
             PAST_DUE → CANCELLED
```

### API Endpoints

#### Create Subscription Plan
```http
POST /subscriptions/plans

{
  "name": "Pro Plan",
  "description": "Full access to all features",
  "amount": 49.99,
  "fiat_currency": "USD",
  "interval": "monthly",
  "interval_count": 1,
  "trial_days": 14,
  "accepted_tokens": ["USDC"],
  "accepted_chains": ["polygon"],
  "features": [
    "Unlimited payments",
    "Advanced analytics",
    "Priority support",
    "API access"
  ]
}
```

**Response:**
```json
{
  "id": "plan_pro2026",
  "name": "Pro Plan",
  "amount": 49.99,
  "interval": "monthly",
  "trial_days": 14,
  "is_active": true,
  "subscriber_count": 0,
  "created_at": "2026-03-04T19:30:00Z"
}
```

#### List Plans
```http
GET /subscriptions/plans?is_active=true
```

#### Update Plan
```http
PATCH /subscriptions/plans/{plan_id}

{
  "name": "Pro Plan (Updated)",
  "features": ["New feature added"]
}
```

#### Create Subscription
```http
POST /subscriptions

{
  "plan_id": "plan_pro2026",
  "customer_email": "user@example.com",
  "customer_name": "Jane Doe",
  "customer_id": "cust_123",
  "skip_trial": false
}
```

**Response:**
```json
{
  "id": "sub_abc123",
  "plan_id": "plan_pro2026",
  "plan_name": "Pro Plan",
  "customer_email": "user@example.com",
  "status": "trialing",
  "current_period_start": "2026-03-04T19:30:00Z",
  "current_period_end": "2026-03-18T19:30:00Z",
  "trial_end": "2026-03-18T19:30:00Z",
  "next_payment_at": "2026-03-18T19:30:00Z",
  "next_payment_url": "https://api.dariforbusiness.com/subscription/sub_abc123/pay"
}
```

#### List Subscriptions
```http
GET /subscriptions?status=active&plan_id=plan_pro2026
```

#### Get Subscription
```http
GET /subscriptions/{subscription_id}
```

#### Cancel Subscription
```http
POST /subscriptions/{subscription_id}/cancel

{
  "cancel_immediately": false,
  "reason": "User requested cancellation"
}
```

#### Pause Subscription
```http
POST /subscriptions/{subscription_id}/pause
```

#### Resume Subscription
```http
POST /subscriptions/{subscription_id}/resume
```

#### List Subscription Payments
```http
GET /subscriptions/{subscription_id}/payments
```

### Payment Flow

1. **Trial Period** - No payment required, status: TRIALING
2. **Trial End** - Generate payment session, notify customer
3. **Payment Success** - Status: ACTIVE, start billing cycle
4. **Payment Failure** - Status: PAST_DUE, retry after 24h
5. **Renewal** - Automatic payment at end of each period

### Billing Cycle Examples

**Monthly:**
```
Period 1: Mar 4 - Apr 4 (Payment due: Apr 4)
Period 2: Apr 4 - May 4 (Payment due: May 4)
```

**Bi-weekly (interval_count: 2):**
```
Period 1: Mar 4 - Mar 18 (Payment due: Mar 18)
Period 2: Mar 18 - Apr 1 (Payment due: Apr 1)
```

### Webhooks

**Subscription Events:**
- `subscription.created`
- `subscription.activated`
- `subscription.renewed`
- `subscription.payment_failed`
- `subscription.cancelled`

### Code Example

```javascript
// Create a subscription plan
const plan = await fetch('https://api.dariforbusiness.com/subscriptions/plans', {
  method: 'POST',
  headers: {
    'X-API-Key': 'your_api_key',
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    name: 'Starter Plan',
    amount: 19.99,
    interval: 'monthly',
    trial_days: 7
  })
}).then(r => r.json());

// Subscribe a customer
const subscription = await fetch('https://api.dariforbusiness.com/subscriptions', {
  method: 'POST',
  headers: {
    'X-API-Key': 'your_api_key',
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    plan_id: plan.id,
    customer_email: 'customer@example.com'
  })
}).then(r => r.json());

console.log('Payment URL:', subscription.next_payment_url);
```

---

## Refund Processing

Process full and partial refunds for completed payments with automated on-chain transactions.

### Features

- **Full refunds** - Return entire payment amount
- **Partial refunds** - Return specified amount
- **Multi-token support** - Refund in original payment token
- **Status tracking** - PENDING → PROCESSING → COMPLETED
- **Retry logic** - Automatic retry on failure
- **Audit trail** - Complete refund history

### Refund States

```
PENDING → PROCESSING → COMPLETED
    ↓
  FAILED (retryable)
```

### API Endpoints

#### Create Refund
```http
POST /refunds

{
  "payment_session_id": "ps_abc123",
  "amount": 50.00,
  "refund_address": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb",
  "reason": "Customer requested refund"
}
```

**Response:**
```json
{
  "id": "ref_xyz789",
  "payment_session_id": "ps_abc123",
  "amount": 50.00,
  "token": "USDC",
  "chain": "polygon",
  "refund_address": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb",
  "status": "pending",
  "reason": "Customer requested refund",
  "created_at": "2026-03-04T19:30:00Z"
}
```

#### List Refunds
```http
GET /refunds?status=completed&payment_session_id=ps_abc123
```

#### Get Refund
```http
GET /refunds/{refund_id}
```

#### Cancel Refund (Pending Only)
```http
POST /refunds/{refund_id}/cancel
```

#### Retry Failed Refund
```http
POST /refunds/{refund_id}/retry
```

### Refund Limits

- Cannot refund more than original payment amount
- Considers previous refunds (partial refund tracking)
- Payment must be in PAID status

### Webhooks

- `refund.created`
- `refund.processing`
- `refund.completed`
- `refund.failed`

### Code Example

```python
# Process a full refund
refund = requests.post(
    'https://api.dariforbusiness.com/refunds',
    headers={'X-API-Key': 'your_api_key'},
    json={
        'payment_session_id': 'ps_abc123',
        'refund_address': '0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb',
        'reason': 'Order cancelled by customer'
    }
).json()

print(f"Refund created: {refund['id']}")
print(f"Status: {refund['status']}")
```

---

## Merchant Analytics

Real-time analytics dashboard with revenue tracking, conversion metrics, and detailed reports.

### Features

- **Overview dashboard** - Key metrics at a glance
- **Revenue charts** - Time-series data for visualization
- **Token breakdown** - Volume by cryptocurrency
- **Chain breakdown** - Volume by blockchain
- **Conversion funnel** - Session creation → payment success
- **Trend analysis** - Period-over-period comparison
- **Custom date ranges** - Day, week, month, year views

### Key Metrics

- **Total volume** - Payment volume in USD
- **Payment count** - Number of transactions
- **Success rate** - Percentage of completed payments
- **Average payment** - Mean transaction value
- **Conversion rate** - Sessions to payments ratio
- **Top tokens** - Most used cryptocurrencies
- **Top chains** - Most used blockchains

### API Endpoints

#### Analytics Overview
```http
GET /analytics/overview?period=month
```

**Response:**
```json
{
  "period_start": "2026-02-04T00:00:00Z",
  "period_end": "2026-03-04T19:30:00Z",
  "period": "month",
  "payments": {
    "total_payments": 1247,
    "successful_payments": 1189,
    "failed_payments": 58,
    "total_volume_usd": 89456.78,
    "avg_payment_usd": 75.24,
    "conversion_rate": 95.35
  },
  "volume_by_token": [
    {
      "token": "USDC",
      "volume_usd": 67842.34,
      "payment_count": 892
    },
    {
      "token": "USDT",
      "volume_usd": 21614.44,
      "payment_count": 297
    }
  ],
  "volume_by_chain": [
    {
      "chain": "polygon",
      "volume_usd": 54789.12,
      "payment_count": 734
    },
    {
      "chain": "stellar",
      "volume_usd": 23456.78,
      "payment_count": 312
    },
    {
      "chain": "ethereum",
      "volume_usd": 11210.88,
      "payment_count": 143
    }
  ],
  "invoices_sent": 45,
  "invoices_paid": 38,
  "invoice_volume_usd": 23456.78,
  "active_subscriptions": 89,
  "new_subscriptions": 23,
  "churned_subscriptions": 5,
  "subscription_mrr": 4447.11,
  "payments_change_pct": 12.5,
  "volume_change_pct": 18.3
}
```

#### Revenue Time Series
```http
GET /analytics/revenue?period=month
```

**Response:**
```json
{
  "period": "month",
  "interval": "day",
  "data": [
    {
      "date": "2026-02-04T00:00:00Z",
      "volume_usd": 2845.67,
      "payment_count": 38
    },
    {
      "date": "2026-02-05T00:00:00Z",
      "volume_usd": 3124.89,
      "payment_count": 42
    }
    // ... more data points
  ]
}
```

#### Payment Summary
```http
GET /analytics/payments/summary?days=30
```

#### Conversion Metrics
```http
GET /analytics/conversion?days=30
```

**Response:**
```json
{
  "period_days": 30,
  "total_sessions": 1305,
  "completed_sessions": 1189,
  "expired_sessions": 116,
  "conversion_rate": 91.11,
  "avg_time_to_payment_seconds": 247
}
```

#### Chain Analytics
```http
GET /analytics/chains?days=30
```

**Response:**
```json
{
  "period_days": 30,
  "chains": [
    {
      "chain": "polygon",
      "payment_count": 734,
      "volume_usd": 54789.12,
      "percentage": 61.25
    },
    {
      "chain": "stellar",
      "payment_count": 312,
      "volume_usd": 23456.78,
      "percentage": 26.22
    }
  ]
}
```

### Dashboard Integration

```javascript
// Fetch analytics for dashboard
async function loadDashboard() {
  const overview = await fetch(
    'https://api.dariforbusiness.com/analytics/overview?period=month',
    { headers: { 'X-API-Key': 'your_api_key' } }
  ).then(r => r.json());

  const revenue = await fetch(
    'https://api.dariforbusiness.com/analytics/revenue?period=month',
    { headers: { 'X-API-Key': 'your_api_key' } }
  ).then(r => r.json());

  // Render charts
  renderVolumeChart(revenue.data);
  renderTokenPieChart(overview.volume_by_token);
  renderChainDistribution(overview.volume_by_chain);
  renderMetrics(overview.payments);
}
```

---

## Team Management

Multi-user access with role-based permissions for merchant accounts.

### Roles & Permissions

| Role | Permissions | Use Case |
|------|-------------|----------|
| **Owner** | Full access + billing | Account owner |
| **Admin** | Full access (no billing) | Operations manager |
| **Developer** | API keys, webhooks, payments | Technical integration |
| **Finance** | Invoices, refunds, analytics | Accounting team |
| **Viewer** | Read-only access | Auditor, stakeholder |

### Permission Matrix

| Action | Owner | Admin | Developer | Finance | Viewer |
|--------|-------|-------|-----------|---------|--------|
| View payments | ✅ | ✅ | ✅ | ✅ | ✅ |
| Create payments | ✅ | ✅ | ✅ | ❌ | ❌ |
| Manage API keys | ✅ | ✅ | ✅ | ❌ | ❌ |
| View invoices | ✅ | ✅ | ✅ | ✅ | ✅ |
| Create invoices | ✅ | ✅ | ❌ | ✅ | ❌ |
| Process refunds | ✅ | ✅ | ❌ | ✅ | ❌ |
| View analytics | ✅ | ✅ | ✅ | ✅ | ✅ |
| Manage team | ✅ | ✅ | ❌ | ❌ | ❌ |
| Manage settings | ✅ | ✅ | ❌ | ❌ | ❌ |
| Manage billing | ✅ | ❌ | ❌ | ❌ | ❌ |

### API Endpoints

#### Invite Team Member
```http
POST /team/invite

{
  "email": "developer@company.com",
  "name": "John Developer",
  "role": "developer"
}
```

**Response:**
```json
{
  "id": "usr_abc123",
  "email": "developer@company.com",
  "name": "John Developer",
  "role": "developer",
  "is_active": true,
  "invite_pending": true,
  "created_at": "2026-03-04T19:30:00Z"
}
```

#### List Team Members
```http
GET /team
```

#### Get Team Member
```http
GET /team/{member_id}
```

#### Update Team Member
```http
PATCH /team/{member_id}

{
  "role": "admin",
  "is_active": true
}
```

#### Remove Team Member
```http
DELETE /team/{member_id}
```

#### Resend Invitation
```http
POST /team/{member_id}/resend-invite
```

#### List Role Permissions
```http
GET /team/roles/permissions
```

### Invitation Flow

1. **Merchant invites user** - POST /team/invite
2. **System generates invite token** - 7-day expiration
3. **Email sent to user** - With acceptance link
4. **User accepts invite** - POST /team/accept-invite
5. **User sets password** - Account activated
6. **User can log in** - Full access granted

#### Accept Invitation (Public Endpoint)
```http
POST /team/accept-invite

{
  "token": "invite_token_from_email",
  "password": "secure_password123",
  "name": "John Developer"
}
```

### Code Example

```python
# Invite a developer
invite = requests.post(
    'https://api.dariforbusiness.com/team/invite',
    headers={'X-API-Key': 'your_api_key'},
    json={
        'email': 'dev@company.com',
        'name': 'Jane Dev',
        'role': 'developer'
    }
).json()

print(f"Invited {invite['email']} as {invite['role']}")

# List all team members
team = requests.get(
    'https://api.dariforbusiness.com/team',
    headers={'X-API-Key': 'your_api_key'}
).json()

for member in team['members']:
    print(f"{member['name']} - {member['role']} - Active: {member['is_active']}")
```

---

## Idempotency Keys

Prevent duplicate API operations by including idempotency keys in requests.

### How It Works

1. Client generates unique key (e.g., UUID)
2. Include in request header: `Idempotency-Key: {key}`
3. Server stores request fingerprint
4. Duplicate requests return cached response
5. Keys expire after 24 hours

### Supported Endpoints

- POST /api/sessions/create
- POST /payment-links
- POST /invoices
- POST /subscriptions
- POST /refunds

### Usage

```http
POST /payment-links
X-API-Key: your_api_key
Idempotency-Key: unique_key_12345

{
  "name": "My Link",
  "amount_fiat": 100.00
}
```

**First Request:** Processes normally, stores response
**Duplicate Request:** Returns cached response immediately

### Response Headers

```http
Idempotency-Key-Status: cached
```

### Error Handling

**409 Conflict** - Key is currently being processed
```json
{
  "detail": "A request with this idempotency key is still being processed"
}
```

### Best Practices

1. **Generate UUIDs** - Use UUID v4 for uniqueness
2. **One key per operation** - New key for each distinct operation
3. **Store keys** - Save keys to retry safely
4. **Handle 409** - Wait and retry if still processing

### Code Example

```javascript
import { v4 as uuidv4 } from 'uuid';

async function createPaymentLinkIdempotent(data) {
  const idempotencyKey = uuidv4();
  
  const response = await fetch('https://api.dariforbusiness.com/payment-links', {
    method: 'POST',
    headers: {
      'X-API-Key': 'your_api_key',
      'Idempotency-Key': idempotencyKey,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(data)
  });

  if (response.status === 409) {
    // Still processing, wait and retry
    await new Promise(resolve => setTimeout(resolve, 1000));
    return createPaymentLinkIdempotent(data);
  }

  return response.json();
}
```

---

## Event Queue & Webhooks

Async event processing system for reliable webhook delivery and background jobs.

### Architecture

```
Action → Event Created → Event Queue → Processor → Webhook Delivery
                                    ↓
                               Retry Logic (5 attempts)
```

### Event Types

**Payment Events:**
- `payment.created`
- `payment.pending`
- `payment.confirmed`
- `payment.failed`
- `payment.expired`

**Invoice Events:**
- `invoice.created`
- `invoice.sent`
- `invoice.viewed`
- `invoice.paid`
- `invoice.overdue`
- `invoice.cancelled`

**Subscription Events:**
- `subscription.created`
- `subscription.activated`
- `subscription.renewed`
- `subscription.paused`
- `subscription.cancelled`
- `subscription.payment_failed`

**Refund Events:**
- `refund.created`
- `refund.processing`
- `refund.completed`
- `refund.failed`

### Event Payload Structure

```json
{
  "id": "evt_abc123",
  "event_type": "payment.confirmed",
  "entity_type": "payment",
  "entity_id": "ps_xyz789",
  "merchant_id": "mch_abc123",
  "payload": {
    "session_id": "ps_xyz789",
    "amount_fiat": "100.00",
    "currency": "USD",
    "status": "paid",
    "token": "USDC",
    "chain": "polygon",
    "tx_hash": "0x123...",
    "timestamp": "2026-03-04T19:30:00Z"
  },
  "created_at": "2026-03-04T19:30:00Z"
}
```

### Webhook Configuration

Set webhook URL in merchant profile:
```http
PUT /merchant/profile

{
  "webhook_url": "https://yoursite.com/webhooks/dari",
  "webhook_secret": "whsec_abc123xyz"
}
```

### Webhook Delivery

**Request:**
```http
POST https://yoursite.com/webhooks/dari
Content-Type: application/json
X-Dari-Signature: sha256=...

{
  "event": "payment.confirmed",
  "session_id": "ps_xyz789",
  "amount": "100.00",
  "currency": "USD",
  "token": "USDC",
  "chain": "polygon",
  "tx_hash": "0x123...",
  "timestamp": "2026-03-04T19:30:00Z"
}
```

### Retry Strategy

| Attempt | Delay |
|---------|-------|
| 1 | Immediate |
| 2 | 1 minute |
| 3 | 5 minutes |
| 4 | 15 minutes |
| 5 | 1 hour |
| 6 | 2 hours |

After 6 failed attempts, webhook marked as failed.

### Signature Verification

```python
import hmac
import hashlib

def verify_webhook(payload, signature, secret):
    """Verify webhook signature"""
    expected = hmac.new(
        secret.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(f"sha256={expected}", signature)

# Usage
@app.post('/webhooks/dari')
async def handle_webhook(request: Request):
    payload = await request.body()
    signature = request.headers.get('X-Dari-Signature')
    
    if not verify_webhook(payload.decode(), signature, WEBHOOK_SECRET):
        raise HTTPException(403, 'Invalid signature')
    
    data = json.loads(payload)
    # Process webhook...
```

### Event Service API

```python
from app.services.event_queue import EventService, emit_payment_event

# Create event
db = get_db()
event_service = EventService(db)

event = event_service.create_event(
    event_type="payment.confirmed",
    entity_type="payment",
    entity_id="ps_xyz789",
    payload={"amount": 100.00, "token": "USDC"},
    merchant_id="mch_abc123"
)

# Or use helper
emit_payment_event(db, "payment.confirmed", payment_session)
```

---

## Database Schema

### New Tables

#### payment_links
```sql
CREATE TABLE payment_links (
    id VARCHAR(50) PRIMARY KEY,
    merchant_id UUID REFERENCES merchants(id),
    name VARCHAR(100) NOT NULL,
    description TEXT,
    amount_fiat DECIMAL(10, 2),
    fiat_currency VARCHAR(10) DEFAULT 'USD',
    is_amount_fixed BOOLEAN DEFAULT TRUE,
    accepted_tokens JSONB,
    accepted_chains JSONB,
    is_active BOOLEAN DEFAULT TRUE,
    is_single_use BOOLEAN DEFAULT FALSE,
    expires_at TIMESTAMP,
    view_count INTEGER DEFAULT 0,
    payment_count INTEGER DEFAULT 0,
    total_collected_usd DECIMAL(14, 2) DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);
```

#### invoices
```sql
CREATE TABLE invoices (
    id VARCHAR(50) PRIMARY KEY,
    invoice_number VARCHAR(50) NOT NULL,
    merchant_id UUID REFERENCES merchants(id),
    customer_email VARCHAR(255) NOT NULL,
    customer_name VARCHAR(255),
    line_items JSONB,
    subtotal DECIMAL(14, 2) NOT NULL,
    tax DECIMAL(14, 2) DEFAULT 0,
    discount DECIMAL(14, 2) DEFAULT 0,
    total DECIMAL(14, 2) NOT NULL,
    status invoice_status DEFAULT 'draft',
    due_date TIMESTAMP NOT NULL,
    sent_at TIMESTAMP,
    paid_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);
```

#### subscription_plans
```sql
CREATE TABLE subscription_plans (
    id VARCHAR(50) PRIMARY KEY,
    merchant_id UUID REFERENCES merchants(id),
    name VARCHAR(100) NOT NULL,
    amount DECIMAL(10, 2) NOT NULL,
    interval subscription_interval NOT NULL,
    interval_count INTEGER DEFAULT 1,
    trial_days INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);
```

#### subscriptions
```sql
CREATE TABLE subscriptions (
    id VARCHAR(50) PRIMARY KEY,
    plan_id VARCHAR(50) REFERENCES subscription_plans(id),
    merchant_id UUID REFERENCES merchants(id),
    customer_email VARCHAR(255) NOT NULL,
    status subscription_status DEFAULT 'active',
    current_period_start TIMESTAMP NOT NULL,
    current_period_end TIMESTAMP NOT NULL,
    next_payment_at TIMESTAMP,
    cancel_at TIMESTAMP,
    cancelled_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);
```

#### refunds
```sql
CREATE TABLE refunds (
    id VARCHAR(50) PRIMARY KEY,
    payment_session_id VARCHAR(100) REFERENCES payment_sessions(id),
    merchant_id UUID REFERENCES merchants(id),
    amount DECIMAL(14, 6) NOT NULL,
    token VARCHAR(10) NOT NULL,
    chain VARCHAR(20) NOT NULL,
    refund_address VARCHAR(100) NOT NULL,
    status refund_status DEFAULT 'pending',
    tx_hash VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW()
);
```

#### merchant_users
```sql
CREATE TABLE merchant_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id UUID REFERENCES merchants(id),
    email VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255),
    role merchant_role DEFAULT 'viewer',
    is_active BOOLEAN DEFAULT TRUE,
    invite_token VARCHAR(255),
    invite_expires TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(merchant_id, email)
);
```

#### events
```sql
CREATE TABLE events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id UUID REFERENCES merchants(id),
    event_type VARCHAR(50) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    entity_id VARCHAR(100) NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    attempts INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);
```

#### idempotency_keys
```sql
CREATE TABLE idempotency_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key VARCHAR(100) NOT NULL UNIQUE,
    merchant_id UUID REFERENCES merchants(id),
    endpoint VARCHAR(200) NOT NULL,
    response_body JSONB,
    is_processing BOOLEAN DEFAULT FALSE,
    completed BOOLEAN DEFAULT FALSE,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### Enums

```sql
CREATE TYPE invoice_status AS ENUM ('draft', 'sent', 'viewed', 'paid', 'overdue', 'cancelled');
CREATE TYPE subscription_status AS ENUM ('active', 'paused', 'cancelled', 'past_due', 'trialing');
CREATE TYPE subscription_interval AS ENUM ('daily', 'weekly', 'monthly', 'quarterly', 'yearly');
CREATE TYPE refund_status AS ENUM ('pending', 'processing', 'completed', 'failed');
CREATE TYPE merchant_role AS ENUM ('owner', 'admin', 'developer', 'finance', 'viewer');
```

---

## Migration Guide

### Step 1: Backup Database

```bash
# PostgreSQL
pg_dump -U postgres dari_db > backup_$(date +%Y%m%d).sql

# Alternative: Export data
python scripts/backup_data.py
```

### Step 2: Run Migration

```bash
# Apply enterprise features migration
psql -U postgres -d dari_db -f migrations/enterprise_features.sql

# Verify tables created
psql -U postgres -d dari_db -c "\dt"
```

### Step 3: Update Application

```bash
# Pull latest code
git pull origin main

# Install dependencies
pip install -r requirements.txt

# Restart server
./start.sh
```

### Step 4: Verify Installation

```bash
# Check API health
curl https://api.dariforbusiness.com/

# Test new endpoints
curl -H "X-API-Key: your_api_key" \
     https://api.dariforbusiness.com/payment-links
```

### Rollback (If Needed)

```bash
# Restore backup
psql -U postgres -d dari_db < backup_20260304.sql

# Revert code
git checkout v1.9.0
```

---

## Integration Examples

### Complete Payment Link Flow

```javascript
// 1. Create payment link
const link = await fetch('https://api.dariforbusiness.com/payment-links', {
  method: 'POST',
  headers: {
    'X-API-Key': 'your_api_key',
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    name: 'Digital Product',
    amount_fiat: 49.99,
    accepted_tokens: ['USDC'],
    accepted_chains: ['polygon']
  })
}).then(r => r.json());

// 2. Share link
console.log('Share:', link.checkout_url);

// 3. Track analytics
const analytics = await fetch(
  `https://api.dariforbusiness.com/payment-links/${link.id}/analytics`,
  { headers: { 'X-API-Key': 'your_api_key' } }
).then(r => r.json());

console.log(`Views: ${analytics.views}, Payments: ${analytics.payments}`);
```

### Invoice + Webhook Flow

```python
# 1. Create invoice
invoice = requests.post(
    'https://api.dariforbusiness.com/invoices',
    headers={'X-API-Key': 'your_api_key'},
    json={
        'customer_email': 'client@company.com',
        'line_items': [
            {'description': 'Services', 'quantity': 1, 'unit_price': 1000.00}
        ],
        'due_date': '2026-04-01T00:00:00Z',
        'send_immediately': True
    }
).json()

# 2. Handle webhook
@app.post('/webhooks/dari')
async def handle_webhook(request: Request):
    payload = await request.json()
    
    if payload['event'] == 'invoice.paid':
        invoice_id = payload['invoice_id']
        # Update your database
        db.execute(
            "UPDATE orders SET status = 'paid' WHERE invoice_id = ?",
            (invoice_id,)
        )
```

### Subscription Management

```python
# 1. Create plan
plan = requests.post(
    'https://api.dariforbusiness.com/subscriptions/plans',
    headers={'X-API-Key': 'your_api_key'},
    json={
        'name': 'Pro Plan',
        'amount': 29.99,
        'interval': 'monthly',
        'trial_days': 14
    }
).json()

# 2. Subscribe customer
subscription = requests.post(
    'https://api.dariforbusiness.com/subscriptions',
    headers={'X-API-Key': 'your_api_key'},
    json={
        'plan_id': plan['id'],
        'customer_email': 'user@example.com'
    }
).json()

# 3. Handle renewal webhooks
@app.post('/webhooks/dari')
async def handle_subscription_webhook(payload: dict):
    if payload['event'] == 'subscription.renewed':
        # Grant access for next period
        extend_access(payload['customer_email'], days=30)
    elif payload['event'] == 'subscription.payment_failed':
        # Send reminder
        send_payment_reminder(payload['customer_email'])
```

### Analytics Dashboard

```javascript
async function renderDashboard() {
  // Fetch data
  const [overview, revenue] = await Promise.all([
    fetch('https://api.dariforbusiness.com/analytics/overview?period=month', {
      headers: { 'X-API-Key': 'your_api_key' }
    }).then(r => r.json()),
    fetch('https://api.dariforbusiness.com/analytics/revenue?period=month', {
      headers: { 'X-API-Key': 'your_api_key' }
    }).then(r => r.json())
  ]);

  // Render metrics
  document.getElementById('total-volume').textContent = 
    `$${overview.payments.total_volume_usd.toLocaleString()}`;
  
  document.getElementById('payment-count').textContent = 
    overview.payments.total_payments;
  
  document.getElementById('conversion-rate').textContent = 
    `${overview.payments.conversion_rate}%`;

  // Render chart
  new Chart(document.getElementById('revenue-chart'), {
    type: 'line',
    data: {
      labels: revenue.data.map(d => d.date),
      datasets: [{
        label: 'Revenue (USD)',
        data: revenue.data.map(d => d.volume_usd)
      }]
    }
  });
}
```

---

## Support & Resources

### Documentation
- API Reference: https://docs.dariforbusiness.com
- GitHub: https://github.com/your-org/dari-backend
- Changelog: https://github.com/your-org/dari-backend/releases

### Support Channels
- Email: support@dariforbusiness.com
- Discord: https://discord.gg/dariforbusiness
- GitHub Issues: https://github.com/your-org/dari-backend/issues

### Rate Limits
- Default: 100 requests/minute per API key
- Enterprise: Custom limits available
- Webhooks: No rate limit on delivery

### Status Page
- https://status.dariforbusiness.com

---

**End of Enterprise Features Documentation**

*Version 2.0.0 | March 4, 2026*
