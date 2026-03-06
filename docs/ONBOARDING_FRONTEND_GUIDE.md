# Onboarding Flow - Frontend Integration Guide

## Overview

The new onboarding system provides a simplified, Stripe/Shopify-style merchant signup experience with **3 easy steps**:

1. **Signup** - Google OAuth or Email/Password
2. **Business Details** - Business info and category selection
3. **Wallet Setup** - Auto-generate blockchain wallets (Complete)

> **Note:** KYC/KYB verification is **NOT** required during onboarding. It's only needed later for fiat withdrawals.

---

## API Endpoints

### Base URL
```
http://localhost:8000
```

---

## Step 1: Signup

### Option A: Email/Password Registration

**Endpoint:** `POST /auth/register`

**Request Body:**
```json
{
  "name": "John Doe",
  "email": "john@example.com",
  "password": "SecurePass123!",
  "merchant_category": "individual"
}
```

**merchant_category Options:**
- `individual` - Individual/Freelancer
- `startup` - Startup
- `small_business` - Small Business
- `enterprise` - Enterprise
- `ngo` - NGO/Non-Profit

**Response (201 Created):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "api_key": "pk_live_xxxxxxxxxxxx"
}
```

**Frontend Integration:**
```typescript
const register = async (name: string, email: string, password: string, category: string) => {
  const response = await fetch('http://localhost:8000/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name,
      email,
      password,
      merchant_category: category
    })
  });
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail);
  }
  
  const data = await response.json();
  
  // Store tokens
  localStorage.setItem('access_token', data.access_token);
  localStorage.setItem('api_key', data.api_key);
  
  return data;
};
```

---

### Option B: Google OAuth Login

**Endpoint:** `POST /auth/google`

**Request Body:**
```json
{
  "token": "ya29.a0AfH6SMBx..."
}
```

**Response (200 OK):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "api_key": "pk_live_xxxxxxxxxxxx",
  "is_new_user": true,
  "onboarding_completed": false
}
```

**Frontend Integration with Google Sign-In:**

```typescript
import { GoogleOAuthProvider, GoogleLogin } from '@react-oauth/google';

const GoogleSignIn = () => {
  const handleGoogleSuccess = async (credentialResponse: any) => {
    try {
      const response = await fetch('http://localhost:8000/auth/google', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          token: credentialResponse.credential
        })
      });
      
      const data = await response.json();
      
      // Store tokens
      localStorage.setItem('access_token', data.access_token);
      localStorage.setItem('api_key', data.api_key);
      
      // Check onboarding status
      if (data.is_new_user || !data.onboarding_completed) {
        // Redirect to onboarding
        window.location.href = '/onboarding/business-details';
      } else {
        // Redirect to dashboard
        window.location.href = '/dashboard';
      }
    } catch (error) {
      console.error('Google login failed:', error);
    }
  };
  
  return (
    <GoogleOAuthProvider clientId="YOUR_GOOGLE_CLIENT_ID">
      <GoogleLogin
        onSuccess={handleGoogleSuccess}
        onError={() => console.log('Login Failed')}
      />
    </GoogleOAuthProvider>
  );
};
```

**Get Google Client ID:**
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project
3. Enable Google+ API
4. Create OAuth 2.0 credentials
5. Add authorized redirect URIs (e.g., `http://localhost:3000`)

---

## Step 2: Business Details

**Endpoint:** `POST /onboarding/business-details`

**Headers:**
```
Authorization: Bearer <access_token>
```

**Request Body:**
```json
{
  "business_name": "Acme Corp",
  "business_email": "billing@acme.com",
  "country": "United States",
  "merchant_category": "startup"
}
```

**Response (200 OK):**
```json
{
  "message": "Business details saved successfully",
  "step": 2,
  "next_step": "wallet_setup"
}
```

**Frontend Integration:**
```typescript
const submitBusinessDetails = async (details: {
  business_name: string;
  business_email?: string;
  country: string;
  merchant_category: string;
}) => {
  const token = localStorage.getItem('access_token');
  
  const response = await fetch('http://localhost:8000/onboarding/business-details', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    },
    body: JSON.stringify(details)
  });
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail);
  }
  
  return await response.json();
};
```

---

## Step 3: Wallet Setup & Complete

**Endpoint:** `POST /onboarding/complete`

**Headers:**
```
Authorization: Bearer <access_token>
```

**Request Body:**
```json
{
  "chains": ["stellar", "ethereum", "polygon"],
  "tokens": ["USDC", "USDT"],
  "auto_generate": true
}
```

**Supported Chains:**
- `stellar` - Stellar Network
- `ethereum` - Ethereum Mainnet
- `polygon` - Polygon (Matic)
- `base` - Base (Coinbase L2)
- `tron` - Tron Network

**Supported Tokens:**
- `USDC` - USD Coin
- `USDT` - Tether USD
- `PYUSD` - PayPal USD

**Response (200 OK):**
```json
{
  "message": "Onboarding completed successfully! 🎉",
  "merchant_id": "550e8400-e29b-41d4-a716-446655440000",
  "api_key": "pk_live_xxxxxxxxxxxx",
  "onboarding_completed": true,
  "wallets": [
    {
      "chain": "stellar",
      "wallet_address": "GDZS...",
      "is_active": true
    },
    {
      "chain": "ethereum",
      "wallet_address": "0x742d...",
      "is_active": true
    },
    {
      "chain": "polygon",
      "wallet_address": "0x742d...",
      "is_active": true
    }
  ]
}
```

**Frontend Integration:**
```typescript
const completeOnboarding = async (
  chains: string[] = ['stellar', 'ethereum', 'polygon'],
  tokens: string[] = ['USDC', 'USDT']
) => {
  const token = localStorage.getItem('access_token');
  
  const response = await fetch('http://localhost:8000/onboarding/complete', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    },
    body: JSON.stringify({
      chains,
      tokens,
      auto_generate: true
    })
  });
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail);
  }
  
  const data = await response.json();
  
  // Update API key if new one was generated
  if (data.api_key) {
    localStorage.setItem('api_key', data.api_key);
  }
  
  return data;
};
```

---

## Check Onboarding Status

**Endpoint:** `GET /onboarding/status`

**Headers:**
```
Authorization: Bearer <access_token>
```

**Response (200 OK):**
```json
{
  "step": 2,
  "onboarding_completed": false,
  "merchant_id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "John Doe",
  "email": "john@example.com",
  "merchant_category": "individual",
  "business_name": "Acme Corp",
  "business_email": "billing@acme.com",
  "country": "United States",
  "has_wallets": false,
  "wallet_count": 0
}
```

**Frontend Integration:**
```typescript
const checkOnboardingStatus = async () => {
  const token = localStorage.getItem('access_token');
  
  const response = await fetch('http://localhost:8000/onboarding/status', {
    method: 'GET',
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });
  
  if (!response.ok) {
    throw new Error('Failed to fetch onboarding status');
  }
  
  return await response.json();
};
```

---

## Complete React Example

```tsx
import React, { useState, useEffect } from 'react';
import { GoogleOAuthProvider, GoogleLogin } from '@react-oauth/google';

type OnboardingStep = 'signup' | 'business_details' | 'wallet_setup' | 'complete';

const OnboardingFlow = () => {
  const [step, setStep] = useState<OnboardingStep>('signup');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // Step 1: Signup
  const handleEmailSignup = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    
    const formData = new FormData(e.target as HTMLFormElement);
    
    try {
      const response = await fetch('http://localhost:8000/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: formData.get('name'),
          email: formData.get('email'),
          password: formData.get('password'),
          merchant_category: formData.get('category')
        })
      });
      
      if (!response.ok) throw new Error('Registration failed');
      
      const data = await response.json();
      localStorage.setItem('access_token', data.access_token);
      localStorage.setItem('api_key', data.api_key);
      
      setStep('business_details');
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };
  
  // Step 2: Business Details
  const handleBusinessDetails = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    
    const formData = new FormData(e.target as HTMLFormElement);
    const token = localStorage.getItem('access_token');
    
    try {
      const response = await fetch('http://localhost:8000/onboarding/business-details', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          business_name: formData.get('business_name'),
          business_email: formData.get('business_email'),
          country: formData.get('country'),
          merchant_category: formData.get('category')
        })
      });
      
      if (!response.ok) throw new Error('Failed to save business details');
      
      setStep('wallet_setup');
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };
  
  // Step 3: Complete Onboarding
  const handleCompleteOnboarding = async () => {
    setLoading(true);
    setError(null);
    
    const token = localStorage.getItem('access_token');
    
    try {
      const response = await fetch('http://localhost:8000/onboarding/complete', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          chains: ['stellar', 'ethereum', 'polygon'],
          tokens: ['USDC', 'USDT'],
          auto_generate: true
        })
      });
      
      if (!response.ok) throw new Error('Failed to complete onboarding');
      
      const data = await response.json();
      setStep('complete');
      
      // Redirect to dashboard after 2 seconds
      setTimeout(() => {
        window.location.href = '/dashboard';
      }, 2000);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };
  
  return (
    <div className="onboarding-container">
      {error && <div className="error">{error}</div>}
      
      {step === 'signup' && (
        <div className="signup-step">
          <h1>Create your account</h1>
          
          <GoogleOAuthProvider clientId="YOUR_GOOGLE_CLIENT_ID">
            <GoogleLogin
              onSuccess={async (credentialResponse) => {
                // Handle Google OAuth
              }}
              onError={() => setError('Google login failed')}
            />
          </GoogleOAuthProvider>
          
          <div className="divider">OR</div>
          
          <form onSubmit={handleEmailSignup}>
            <input name="name" placeholder="Full Name" required />
            <input name="email" type="email" placeholder="Email" required />
            <input name="password" type="password" placeholder="Password" required />
            <select name="category" required>
              <option value="individual">Individual/Freelancer</option>
              <option value="startup">Startup</option>
              <option value="small_business">Small Business</option>
              <option value="enterprise">Enterprise</option>
              <option value="ngo">NGO/Non-Profit</option>
            </select>
            <button type="submit" disabled={loading}>
              {loading ? 'Creating account...' : 'Continue'}
            </button>
          </form>
        </div>
      )}
      
      {step === 'business_details' && (
        <div className="business-details-step">
          <h1>Tell us about your business</h1>
          <form onSubmit={handleBusinessDetails}>
            <input name="business_name" placeholder="Business Name" required />
            <input name="business_email" type="email" placeholder="Business Email (optional)" />
            <input name="country" placeholder="Country" required />
            <select name="category" required>
              <option value="individual">Individual/Freelancer</option>
              <option value="startup">Startup</option>
              <option value="small_business">Small Business</option>
              <option value="enterprise">Enterprise</option>
              <option value="ngo">NGO/Non-Profit</option>
            </select>
            <button type="submit" disabled={loading}>
              {loading ? 'Saving...' : 'Continue'}
            </button>
          </form>
        </div>
      )}
      
      {step === 'wallet_setup' && (
        <div className="wallet-setup-step">
          <h1>Set up your payment wallet</h1>
          <p>We'll automatically generate secure blockchain wallets for you.</p>
          <button onClick={handleCompleteOnboarding} disabled={loading}>
            {loading ? 'Creating wallets...' : 'Complete Setup'}
          </button>
        </div>
      )}
      
      {step === 'complete' && (
        <div className="complete-step">
          <h1>🎉 You're all set!</h1>
          <p>Redirecting to dashboard...</p>
        </div>
      )}
    </div>
  );
};

export default OnboardingFlow;
```

---

## Authentication After Onboarding

Once onboarding is complete, use the JWT token for all authenticated requests:

```typescript
const fetchWithAuth = async (url: string, options: RequestInit = {}) => {
  const token = localStorage.getItem('access_token');
  
  return fetch(url, {
    ...options,
    headers: {
      ...options.headers,
      'Authorization': `Bearer ${token}`
    }
  });
};

// Example: Get merchant profile
const getProfile = async () => {
  const response = await fetchWithAuth('http://localhost:8000/merchant/profile');
  return await response.json();
};
```

---

## Error Handling

All endpoints return standard error responses:

```json
{
  "detail": "Email already registered"
}
```

**Common Error Codes:**
- `400` - Bad Request (validation error)
- `401` - Unauthorized (invalid/missing token)
- `403` - Forbidden (insufficient permissions)
- `409` - Conflict (duplicate email, etc.)
- `500` - Internal Server Error

---

## Environment Variables

Add to your frontend `.env`:

```env
VITE_API_BASE_URL=http://localhost:8000
VITE_GOOGLE_CLIENT_ID=your-google-client-id-here
```

---

## Next Steps

After onboarding is complete, merchants can:

1. **Create payment sessions** - Use the API key from onboarding
2. **Configure webhooks** - Receive payment notifications
3. **View analytics** - Track payments and revenue
4. **Manage team** - Add team members (enterprise feature)
5. **Set up KYC/KYB** - Required only for fiat withdrawals

See [ENTERPRISE_FEATURES.md](ENTERPRISE_FEATURES.md) for advanced features documentation.

---

## Support

For questions or issues:
- API Documentation: `http://localhost:8000/docs`
- GitHub Issues: [Create an issue](https://github.com/yourusername/chainpe)
- Email: support@dari.in
