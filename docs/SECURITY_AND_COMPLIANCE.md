# Dari for Business - Complete System & Security Overview

This document provides a comprehensive overview of the security architecture, compliance standards, data protection mechanisms, API design, and monitoring infrastructure for the **Dari for Business** multi-chain payment gateway.

---

## 1. System Architecture Overview

Dari for Business is a robust, multi-chain Python/FastAPI backend designed to process fiat-to-crypto and crypto-native payments smoothly.

### 1.1 Core Components
*   **FastAPI Application**: The central gateway providing RESTful interfaces for merchant dashboards, public checkouts, and admin operations.
*   **Database**: Relational database (e.g., PostgreSQL/SQLite) storing merchant profiles, payment sessions, invoices, and analytics.
*   **Redis Token Vault**: A fast, ephemeral storage system used for tokenizing sensitive checkout session data to avoid persisting raw payment requests.
*   **Blockchain Relayers / Listeners**: Dedicated background workers that interact directly with RPC endpoints across various networks:
    *   **EVM Chains**: Ethereum, Polygon, Base, Arbitrum, BSC.
    *   **Non-EVM**: Stellar (Soroban contracts), Tron (TVM contracts), Solana (Anchor programs).

---

## 2. Comprehensive Security Architecture

Security is built into Dari at multiple layers, protecting against both external API attacks and internal data leaks.

### 2.1 API & Transport Security
*   **Idempotency (`IdempotencyMiddleware`)**: Crucial for payment systems to prevent double-charging. POST interfaces (like `/invoices`, `/refunds`, `/withdrawals`) validate `Idempotency-Key` headers and cache 200/201/202 responses or return a `409 Conflict` if the same request is still processing.
*   **Security Headers (`SecurityHeadersMiddleware`)**: Applied globally to ensure OWASP compliance:
    *   `Strict-Transport-Security` (HSTS)
    *   `X-Frame-Options` (DENY/SAMEORIGIN)
    *   `X-Content-Type-Options` (nosniff)
    *   `Content-Security-Policy`

### 2.2 Replay Protection
Endpoints that trigger money movement (e.g., `/refunds`, `/withdrawals`) enforce Replay Protection. Every sensitive API request must include:
*   `X-Request-Nonce`: A unique string for the request.
*   `X-Request-Timestamp`: The epoch time of the request.
*   **Validation**: The backend rejects any requests older than 5 minutes or any requests attempting to reuse a previously seen nonce.

### 2.3 Authentication & Authorization
*   **JWT Access Tokens**: All state-modifying requests require a Bearer token.
*   **Role-Based Access Control (RBAC)**: Enforced via dependency injection (`require_merchant`, `require_admin`). Merchants can only access data and initiate withdrawals associated with their specific `merchant_id` UUID.

### 2.4 Internal Webhook Integrity
*   **HMAC-SHA256 Signatures**: Whenever the system dispatches internal webhook events (e.g., `payment.completed`), the payload is hashed using `API_KEY_SECRET`. Clients verify the `X-Webhook-Signature` header to guarantee the event genuinely originated from Dari.

---

## 3. Compliance and User Data Protection

Dari for Business handles financial transactions and is designed to adhere to global compliance norms (such as PCI-DSS principles and general PII data protection).

### 3.1 PCI-DSS Style Data Masking
Raw user data (such as emails, API keys, passwords, and sensitive tokens) are explicitly scrubbed from server logs. 
*   **Masking Utility**: `mask_sensitive_value()` automatically obfuscates sensitive keys before any logging occurs.
*   **Data Minimization**: Credit card data and private keys are never stored on this backend. For crypto, only wallet addresses and amounts are logged and persisted.

### 3.2 Redis-Backed Token Vault
When a payment session is instantiated on the frontend, the data is heavily tokenized.
*   **Opaque Tokens (`ptok_...`)**: Only opaque tokens are sent across the wire after checkout initialization.
*   **Short Time-To-Live (TTL)**: The Redis Token Vault forcefully expires these instances after exactly **30 minutes**, thoroughly minimizing the window of vulnerability if a token is intercepted.

### 3.3 Anti-Money Laundering (AML) & Risk
*   **TRM Labs Risk Scoring**: The platform integrates with TRM Labs to evaluate incoming payment URLs and wallet addresses. Flags (such as interacting with sanctioned wallets or mixers) halt the checkout and flag the session for manual admin review.

---

## 4. API Usage Patterns

The REST API exposes functionality divided functionally between merchant integrations and backend operations.

### 4.1 Merchant Integrations
*   **Endpoints**: `/payments`, `/invoices`, `/refunds`, `/withdrawals`
*   **Usage**: Merchants provision API keys to programmatically generate payment sessions.
*   **Multi-chain Web3 Subscriptions**: Our proprietary smart contracts (DariSubscriptions) on EVM, Tron, Solana, and Stellar allow developers to subscribe users to completely autonomous "pull-based" recurring payments using standard Stablecoins. 

### 4.2 Front-end Public Flows
*   **Endpoints**: `/checkout`, `/public/sessions`
*   **Usage**: Interfaces hit by the end-customer. They are heavily rate-limited and rely entirely on opaque vault tokens (`ptok_...`) instead of authenticated merchant credentials to prevent API key exposure in the browser.

---

## 5. System Observability and Monitoring

Comprehensive monitoring ensures quick remediation of failed transactions or blockchain RPC desyncs.

### 5.1 Prometheus Metrics
*   **MetricsMiddleware**: Intercepts requests and tracks:
    *   `http_requests_total`: Grouped by path, method, and HTTP status code.
    *   `http_request_duration_seconds`: Histogram of latency across endpoints.
*   **Endpoint**: Accessible via `/metrics` (typically scraped by a clustered Prometheus/Grafana stack).

### 5.2 Structured Logging
Logs are emitted with precise tags indicating `[AUTH DEBUGS]`, `[BLOCKCHAIN EVENT]`, or `[RISK ENGINE]`. 
*   Requests are tracked natively by the `log_requests` middleware, detailing `[STATUS_CODE] process_time` for all API calls.

### 5.3 Active Blockchain Listening
Separate listener services stream live blocks and invoke database updates when they detect merchant inbound transfers. These emit alerting metrics upon persistent remote RPC connection failures.
