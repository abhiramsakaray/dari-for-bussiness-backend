# Dari for Business - React Integration Examples

This directory contains React/TypeScript examples for integrating with the Dari for Business multi-chain payment gateway.

## Overview

Dari for Business enables merchants to accept stablecoin payments (USDC, USDT, PYUSD) across multiple blockchains (Stellar, Polygon, Ethereum, Base, Tron) through a unified API.

## File Structure

```
react_integration_examples/
├── api.ts              # Axios configuration with auth interceptors
├── auth.ts             # Authentication services
├── chainpe.ts          # Main payment service (NEW - Multi-chain)
├── CreatePayment.tsx   # Merchant dashboard - create payment sessions
├── PaymentFlow.tsx     # Customer checkout flow (NEW - Multi-chain)
└── README.md           # This file
```

## Quick Start

### 1. Install Dependencies

```bash
npm install axios
# or
yarn add axios
```

### 2. Set Environment Variables

```env
VITE_API_URL=http://localhost:8000
# or your production URL
```

### 3. Basic Usage

#### Create a Payment Session (Merchant Side)

```tsx
import { chainpeService } from './services/chainpe';

// Create multi-chain payment session
const session = await chainpeService.createSession({
  amount_fiat: 100.00,
  fiat_currency: 'USD',
  accepted_tokens: ['USDC', 'USDT'],
  accepted_chains: ['polygon', 'stellar', 'base'],
  order_id: 'ORDER-123',
  success_url: 'https://yourstore.com/success',
  cancel_url: 'https://yourstore.com/cancel',
  metadata: {
    customer_id: 'cust_123',
    product_ids: ['prod_1', 'prod_2']
  }
});

// Redirect customer to checkout
window.location.href = session.checkout_url;
```

#### Handle Customer Checkout (Customer Side)

```tsx
import { PaymentFlow } from './components/PaymentFlow';

function CheckoutPage() {
  const sessionId = new URLSearchParams(window.location.search).get('session_id');
  
  return <PaymentFlow sessionId={sessionId} />;
}
```

## API Reference

### Payment Session Creation

```typescript
interface PaymentSessionCreate {
  // Amount in fiat currency
  amount_fiat: number;
  fiat_currency?: string;  // Default: 'USD'
  
  // Multi-chain options
  accepted_tokens?: string[];  // Default: ['USDC']
  accepted_chains?: string[];  // Default: ['stellar']
  
  // Order details
  order_id?: string;  // Auto-generated if not provided
  
  // Redirect URLs
  success_url: string;
  cancel_url: string;
  
  // Additional data
  metadata?: Record<string, any>;
}
```

### Available Chains and Tokens

| Chain | Supported Tokens |
|-------|------------------|
| Stellar | USDC |
| Polygon | USDC, USDT |
| Ethereum | USDC, USDT, PYUSD |
| Base | USDC |
| Tron | USDT, USDC |
| Solana | Coming soon |

## Customer Payment Flow

### Step 1: Session Creation
Merchant creates a payment session with accepted payment methods.

### Step 2: Customer Selection
Customer chooses their preferred token and blockchain:
```typescript
await chainpeService.selectPaymentMethod(sessionId, {
  token: 'USDC',
  chain: 'polygon'
});
```

### Step 3: Payment Execution
Customer sends payment to the provided wallet address.

### Step 4: Confirmation
System detects payment and redirects to `success_url`.

## Advanced Features

### Wallet Management

```typescript
// List merchant wallets
const wallets = await chainpeService.listWallets();

// Add wallet for a chain
await chainpeService.addWallet('polygon', '0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb');

// Get wallet for specific chain
const wallet = await chainpeService.getWallet('polygon');

// Remove wallet
await chainpeService.deleteWallet('polygon');
```

### Payment Status Polling

```typescript
// Poll for payment status changes
const stopPolling = chainpeService.pollSessionStatus(
  sessionId,
  (status) => {
    console.log('Payment status:', status);
    
    if (status === 'paid') {
      // Update your order system
      updateOrderStatus(orderId, 'paid');
    }
  },
  3000  // Poll every 3 seconds
);

// Stop polling when component unmounts
return () => stopPolling();
```

### Webhooks

For production, implement webhook handling instead of polling:

```typescript
// Backend webhook endpoint
app.post('/webhooks/dari', async (req, res) => {
  const { event, session_id, chain, token, amount, tx_hash } = req.body;
  
  if (event === 'payment.success') {
    console.log(`Payment received: ${amount} ${token} on ${chain}`);
    console.log(`Transaction: ${tx_hash}`);
    
    // Update your database
    await db.orders.update({
      where: { sessionId: session_id },
      data: { 
        status: 'paid',
        paymentTxHash: tx_hash,
        paidAt: new Date()
      }
    });
  }
  
  res.json({ received: true });
});
```

## Error Handling

```typescript
try {
  const session = await chainpeService.createSession({...});
} catch (error) {
  if (error.response?.status === 401) {
    // Authentication error - refresh token or redirect to login
  } else if (error.response?.status === 400) {
    // Validation error - check request data
    console.error(error.response.data.detail);
  } else {
    // Other errors
    console.error('Payment creation failed:', error.message);
  }
}
```

## Security Best Practices

### 1. API Key Management
- Never expose API keys in client-side code
- Create sessions from your backend server
- Use environment variables

```typescript
// ❌ BAD - Client-side
const session = await fetch('http://localhost:8000/api/sessions', {
  headers: { 'X-API-Key': 'sk_live_xxxx' }  // NEVER DO THIS
});

// ✅ GOOD - Server-side
// Backend endpoint
app.post('/api/create-payment', async (req, res) => {
  const session = await createDariSession({
    apiKey: process.env.DARI_API_KEY,
    ...req.body
  });
  res.json(session);
});
```

### 2. Webhook Verification
Verify webhook signatures to ensure authenticity:

```typescript
const crypto = require('crypto');

function verifyWebhookSignature(payload, signature, secret) {
  const expectedSignature = crypto
    .createHmac('sha256', secret)
    .update(JSON.stringify(payload))
    .digest('hex');
    
  return signature === expectedSignature;
}
```

### 3. Amount Validation
Always verify payment amounts match your order:

```typescript
// Webhook handler
if (payment.amount_fiat !== order.total) {
  console.error('Amount mismatch!');
  return;
}
```

## TypeScript Types

All TypeScript interfaces are exported from `chainpe.ts`:

```typescript
import { 
  PaymentSession,
  PaymentOption,
  SelectPaymentMethod,
  MerchantWallet,
  PaymentSessionCreate
} from './services/chainpe';
```

## Testing

### Test Account
Use testnet for development:
```env
VITE_API_URL=http://localhost:8000
```

### Test Wallets
- **Stellar Testnet**: Use https://laboratory.stellar.org for creating test accounts
- **Polygon Mumbai**: Use https://faucet.polygon.technology
- **Base Goerli**: Use https://bridge.base.org

### Sample Integration Test

```typescript
describe('Payment Flow', () => {
  it('should create session and get payment options', async () => {
    // Create session
    const session = await chainpeService.createSession({
      amount_fiat: 10.00,
      accepted_tokens: ['USDC'],
      accepted_chains: ['stellar'],
      success_url: 'http://localhost:3000/success',
      cancel_url: 'http://localhost:3000/cancel'
    });
    
    expect(session.session_id).toBeDefined();
    
    // Get payment options
    const options = await chainpeService.getPaymentOptions(session.session_id);
    
    expect(options).toHaveLength(1);
    expect(options[0].token).toBe('USDC');
    expect(options[0].chain).toBe('stellar');
  });
});
```

## Production Checklist

- [ ] API keys stored securely (server-side only)
- [ ] Webhook endpoint implemented and verified
- [ ] Error handling and retry logic in place
- [ ] Payment status polling or webhooks configured
- [ ] Wallet addresses verified for each chain
- [ ] Success/cancel URLs configured
- [ ] SSL/TLS enabled on your website
- [ ] Customer support contact displayed
- [ ] Terms of service and refund policy clear

## Support

- **Documentation**: [docs.dariforbusiness.com](https://docs.dariforbusiness.com)
- **API Reference**: `http://localhost:8000/docs`
- **GitHub**: [github.com/dari-business/backend](https://github.com/dari-business/backend)
- **Discord**: [discord.gg/dari](https://discord.gg/dari)

## License

MIT License - See LICENSE file for details
