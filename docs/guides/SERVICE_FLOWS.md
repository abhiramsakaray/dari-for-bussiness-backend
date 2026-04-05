# Dari for Business — Service Flow Diagrams

Visual diagrams of all Dari payment gateway services.

---

## 1. One-Time Payment Flow

```mermaid
sequenceDiagram
    participant M as Merchant Backend
    participant D as Dari API
    participant C as Customer
    participant B as Blockchain

    M->>D: POST /v1/payment_sessions (amount, currency)
    D-->>M: session_id + checkout_url
    M->>C: Redirect to checkout_url
    C->>D: Opens checkout page
    D-->>C: Show amount, select chain/token
    C->>C: Approves wallet tx
    C->>B: Sends stablecoin to deposit address
    B-->>D: Listener detects payment
    D->>D: Verify amount, mark PAID
    D->>D: Auto-create Invoice
    D->>M: Webhook: payment.succeeded
    D->>C: Redirect to success_url
```

---

## 2. Subscription (Recurring) Payment Flow

```mermaid
sequenceDiagram
    participant M as Merchant
    participant D as Dari API
    participant C as Customer
    participant SC as Smart Contract
    participant R as Relayer

    M->>D: Create subscription plan
    D-->>M: plan_id + subscribe_url
    C->>D: Opens subscribe_url
    C->>C: Approves ERC-20 spend (USDC/USDT)
    C->>D: Submits wallet address + signature
    R->>SC: createSubscription(subscriber, merchant, token, amount, interval)
    D->>M: Webhook: subscription.created

    loop Every billing cycle
        D->>D: Scheduler finds due subscriptions
        R->>SC: executePayment(subId)
        SC->>SC: transferFrom(subscriber → merchant)
        D->>D: Record payment, create invoice
        D->>M: Webhook: subscription.payment_executed
    end

    C->>D: Cancel subscription
    R->>SC: cancelSubscription(subId)
    D->>M: Webhook: subscription.cancelled
```

---

## 3. Merchant Onboarding Flow

```mermaid
flowchart TD
    A[Merchant Signs Up] --> B{Auth Method}
    B -->|Email/Password| C[Register Account]
    B -->|Google OAuth| D[Google Sign In]
    C --> E[Auto-generate API Key]
    D --> E
    E --> F[Auto-generate Webhook Secret]
    F --> G[Onboarding Step 0: Profile]

    G --> H[Step 1: Business Details]
    H --> I[Step 2: Select Plan]
    I --> J[Step 3: Add Wallet Address]
    J --> K[Step 4: Configure Webhooks]
    K --> L[Step 5: Integration Guide]
    L --> M[Onboarding Complete ✅]

    M --> N[Dashboard Access]
    N --> O[Create Payment Sessions]
    N --> P[Create Payment Links]
    N --> Q[Create Invoices]
    N --> R[Create Subscription Plans]
```

---

## 4. Checkout Page Flow

```mermaid
flowchart TD
    A[Customer Opens checkout_url] --> B{Session Valid?}
    B -->|Expired| C[Show Expired Page]
    B -->|Already Paid| D[Show Success Page]
    B -->|Valid| E[Show Payment Form]

    E --> F[Customer Enters Email/Name]
    F --> G[Select Chain + Token]
    G --> H[Show Deposit Address + QR]

    H --> I{Payment Method}
    I -->|Manual Transfer| J[Customer Sends from Wallet]
    I -->|Wallet Connect| K[Sign with MetaMask]
    I -->|EIP-712 Signature| L[Gasless Signature Checkout]

    J --> M[Listener Detects Payment]
    K --> M
    L --> M

    M --> N[Verify Amount + Token]
    N --> O[Mark Session PAID]
    O --> P[Auto-Create Invoice]
    P --> Q[Send Webhook to Merchant]
    Q --> R[Redirect to success_url]
```

---

## 5. Invoice & Export Flow

```mermaid
flowchart LR
    A[Payment Confirmed] --> B[Auto-Create Invoice]
    B --> C[Invoice with Multi-Currency Data]
    C --> D[Payer Currency Amount]
    C --> E[Stablecoin Amount + Symbol]
    C --> F[Merchant Currency Amount]
    C --> G[Tx Hash + Chain]

    C --> H{Export Options}
    H -->|PDF| I[Professional PDF for filing]
    H -->|CSV| J[Accounting software import]
    H -->|PNG| K[Shareable image]
```

---

## 6. Webhook Delivery Flow

```mermaid
sequenceDiagram
    participant D as Dari Backend
    participant Q as Event Queue
    participant M as Merchant Server

    D->>Q: Create event (payment.succeeded)
    Q->>Q: Serialize payload + timestamp
    Q->>Q: HMAC-SHA256 sign (merchant's webhook_secret)
    Q->>M: POST to merchant webhook_url
    Note over Q,M: Headers: X-Payment-Signature = t=timestamp,v1=hmac

    alt 2xx Response
        Q->>Q: Mark delivered ✅
    else Non-2xx or Timeout
        Q->>Q: Retry (up to 3 times)
        Q->>Q: Exponential backoff
    end

    Note over M: Merchant verifies signature:
    Note over M: 1. Extract timestamp + signature
    Note over M: 2. Compute HMAC-SHA256(secret, timestamp.body)
    Note over M: 3. Compare (constant-time)
    Note over M: 4. Reject if timestamp > 5 min old
```

---

## 7. Tax Reporting Flow

```mermaid
flowchart TD
    A[Merchant Dashboard] --> B{Report Type}

    B -->|Summary| C[GET /tax-reports/summary]
    C --> D[Total Revenue, Tax, Refunds]
    C --> E[Breakdown by Token/Chain]
    C --> F[Subscription vs One-Time Split]

    B -->|Transactions| G[GET /tax-reports/transactions]
    G --> H[Per-Payment Multi-Currency Details]
    G --> I{Format?}
    I -->|JSON| J[API Response]
    I -->|CSV| K[Download for Accounting]

    B -->|Subscriptions| L[GET /tax-reports/subscription-revenue]
    L --> M[MRR, ARR, Churn Rate]
    L --> N[Per-Subscription Breakdown]
```

---

## 8. Refund Flow

```mermaid
sequenceDiagram
    participant M as Merchant
    participant D as Dari API
    participant B as Blockchain

    M->>D: POST /refunds (session_id, amount, refund_address)
    D->>D: Check eligibility (paid, not already refunded)
    D->>D: Check merchant balance

    alt Sufficient Balance
        D->>B: Send stablecoin to refund_address
        B-->>D: Tx confirmed
        D->>D: Update payment status
        D->>M: Webhook: refund.completed
    else Insufficient Balance
        D->>D: Queue refund or use external wallet
        D->>M: Return: insufficient_funds (options available)
    end
```

---

## 9. Payment Link Flow

```mermaid
flowchart TD
    A[Merchant Creates Payment Link] --> B[GET /payment-links]
    B --> C[Returns checkout_url]

    D[Customer Opens Link] --> E{Amount Fixed?}
    E -->|Yes| F[Show Fixed Amount]
    E -->|No| G[Customer Enters Amount]

    F --> H[Create Payment Session]
    G --> H
    H --> I[Standard Checkout Flow]
    I --> J[Payment Confirmed]

    J --> K{Single Use?}
    K -->|Yes| L[Deactivate Link]
    K -->|No| M[Link Remains Active]
```

---

## 10. Multi-Chain Architecture

```mermaid
flowchart TD
    subgraph API["Dari API Server (FastAPI)"]
        A[Payment Sessions]
        B[Invoices & Export]
        C[Tax Reports]
        D[Subscriptions]
        E[Webhooks]
    end

    subgraph Listeners["Blockchain Listeners (run_listeners.py)"]
        F[Stellar Listener]
        G[EVM Listener]
        H[Tron Listener]
    end

    subgraph EVM["EVM Chains (shared listener)"]
        I[Ethereum]
        J[Polygon]
        K[Base]
        L[BSC]
        M[Arbitrum]
    end

    subgraph Contracts["DariSubscriptions.sol"]
        N[Deployed on all 5 EVM chains]
        O[UUPS Upgradeable Proxy]
    end

    G --> I
    G --> J
    G --> K
    G --> L
    G --> M

    N --> I
    N --> J
    N --> K
    N --> L
    N --> M

    A --> E
    D --> N
