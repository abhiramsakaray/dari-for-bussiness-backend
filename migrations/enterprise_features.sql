-- Enterprise Features Migration
-- Run this migration to add Payment Links, Invoices, Subscriptions, Refunds, 
-- Team Management, Idempotency, Events, Analytics, and Fraud Detection

-- ============================================================================
-- PAYMENT LINKS
-- ============================================================================

CREATE TABLE IF NOT EXISTS payment_links (
    id VARCHAR(50) PRIMARY KEY,  -- link_xxx format
    merchant_id UUID NOT NULL REFERENCES merchants(id),
    
    -- Link details
    name VARCHAR(100) NOT NULL,
    description TEXT,
    
    -- Amount configuration
    amount_fiat DECIMAL(10, 2),
    fiat_currency VARCHAR(10) DEFAULT 'USD' NOT NULL,
    is_amount_fixed BOOLEAN DEFAULT TRUE,
    min_amount DECIMAL(10, 2),
    max_amount DECIMAL(10, 2),
    
    -- Payment options (JSON arrays)
    accepted_tokens JSONB,
    accepted_chains JSONB,
    
    -- URLs
    success_url VARCHAR(500),
    cancel_url VARCHAR(500),
    
    -- Configuration
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    is_single_use BOOLEAN DEFAULT FALSE,
    expires_at TIMESTAMP,
    
    -- Analytics
    view_count INTEGER DEFAULT 0,
    payment_count INTEGER DEFAULT 0,
    total_collected_usd DECIMAL(14, 2) DEFAULT 0,
    
    -- Metadata
    link_metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_payment_links_merchant ON payment_links(merchant_id);
CREATE INDEX idx_payment_links_active ON payment_links(is_active) WHERE is_active = TRUE;


-- Junction table for payment links and sessions
CREATE TABLE IF NOT EXISTS payment_link_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    payment_link_id VARCHAR(50) NOT NULL REFERENCES payment_links(id),
    session_id VARCHAR(100) NOT NULL REFERENCES payment_sessions(id),
    created_at TIMESTAMP DEFAULT NOW() NOT NULL
);

CREATE INDEX idx_payment_link_sessions_link ON payment_link_sessions(payment_link_id);


-- ============================================================================
-- INVOICES
-- ============================================================================

CREATE TYPE invoice_status AS ENUM ('draft', 'sent', 'viewed', 'paid', 'overdue', 'cancelled');

CREATE TABLE IF NOT EXISTS invoices (
    id VARCHAR(50) PRIMARY KEY,  -- inv_xxx format
    invoice_number VARCHAR(50) NOT NULL,
    merchant_id UUID NOT NULL REFERENCES merchants(id),
    
    -- Customer info
    customer_email VARCHAR(255) NOT NULL,
    customer_name VARCHAR(255),
    customer_address TEXT,
    
    -- Invoice details
    description TEXT,
    line_items JSONB,  -- [{description, quantity, unit_price, total}]
    
    -- Amounts
    subtotal DECIMAL(14, 2) NOT NULL,
    tax DECIMAL(14, 2) DEFAULT 0,
    discount DECIMAL(14, 2) DEFAULT 0,
    total DECIMAL(14, 2) NOT NULL,
    fiat_currency VARCHAR(10) DEFAULT 'USD',
    
    -- Payment options
    accepted_tokens JSONB,
    accepted_chains JSONB,
    
    -- Status & Dates
    status invoice_status DEFAULT 'draft' NOT NULL,
    issue_date TIMESTAMP DEFAULT NOW() NOT NULL,
    due_date TIMESTAMP NOT NULL,
    sent_at TIMESTAMP,
    viewed_at TIMESTAMP,
    paid_at TIMESTAMP,
    
    -- Payment tracking
    payment_session_id VARCHAR(100) REFERENCES payment_sessions(id),
    amount_paid DECIMAL(14, 2) DEFAULT 0,
    
    -- Notifications
    reminder_sent BOOLEAN DEFAULT FALSE,
    overdue_sent BOOLEAN DEFAULT FALSE,
    
    -- Metadata
    notes TEXT,
    terms TEXT,
    footer TEXT,
    invoice_metadata JSONB,
    
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_invoices_merchant ON invoices(merchant_id);
CREATE INDEX idx_invoices_status ON invoices(status);
CREATE INDEX idx_invoices_due_date ON invoices(due_date);
CREATE INDEX idx_invoices_customer ON invoices(customer_email);


-- ============================================================================
-- SUBSCRIPTION PLANS
-- ============================================================================

CREATE TYPE subscription_interval AS ENUM ('daily', 'weekly', 'monthly', 'quarterly', 'yearly');
CREATE TYPE subscription_status AS ENUM ('active', 'paused', 'cancelled', 'past_due', 'trialing');

CREATE TABLE IF NOT EXISTS subscription_plans (
    id VARCHAR(50) PRIMARY KEY,  -- plan_xxx format
    merchant_id UUID NOT NULL REFERENCES merchants(id),
    
    -- Plan details
    name VARCHAR(100) NOT NULL,
    description TEXT,
    
    -- Pricing
    amount DECIMAL(10, 2) NOT NULL,
    fiat_currency VARCHAR(10) DEFAULT 'USD',
    interval subscription_interval NOT NULL,
    interval_count INTEGER DEFAULT 1,
    
    -- Trial
    trial_days INTEGER DEFAULT 0,
    
    -- Payment options
    accepted_tokens JSONB,
    accepted_chains JSONB,
    
    -- Configuration
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    
    -- Metadata
    features JSONB,
    plan_metadata JSONB,
    
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_subscription_plans_merchant ON subscription_plans(merchant_id);


-- ============================================================================
-- SUBSCRIPTIONS
-- ============================================================================

CREATE TABLE IF NOT EXISTS subscriptions (
    id VARCHAR(50) PRIMARY KEY,  -- sub_xxx format
    plan_id VARCHAR(50) NOT NULL REFERENCES subscription_plans(id),
    merchant_id UUID NOT NULL REFERENCES merchants(id),
    
    -- Subscriber info
    customer_email VARCHAR(255) NOT NULL,
    customer_name VARCHAR(255),
    customer_id VARCHAR(100),
    
    -- Status
    status subscription_status DEFAULT 'active',
    
    -- Billing cycle
    current_period_start TIMESTAMP NOT NULL,
    current_period_end TIMESTAMP NOT NULL,
    billing_anchor TIMESTAMP NOT NULL,
    
    -- Trial
    trial_start TIMESTAMP,
    trial_end TIMESTAMP,
    
    -- Payment tracking
    last_payment_at TIMESTAMP,
    next_payment_at TIMESTAMP,
    failed_payment_count INTEGER DEFAULT 0,
    
    -- Cancellation
    cancel_at TIMESTAMP,
    cancelled_at TIMESTAMP,
    cancel_reason VARCHAR(500),
    
    -- Metadata
    subscription_metadata JSONB,
    
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_subscriptions_merchant ON subscriptions(merchant_id);
CREATE INDEX idx_subscriptions_status ON subscriptions(status);
CREATE INDEX idx_subscriptions_customer ON subscriptions(customer_email);
CREATE INDEX idx_subscriptions_next_payment ON subscriptions(next_payment_at);


-- ============================================================================
-- SUBSCRIPTION PAYMENTS
-- ============================================================================

CREATE TABLE IF NOT EXISTS subscription_payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subscription_id VARCHAR(50) NOT NULL REFERENCES subscriptions(id),
    payment_session_id VARCHAR(100) REFERENCES payment_sessions(id),
    invoice_id VARCHAR(50) REFERENCES invoices(id),
    
    -- Payment period
    period_start TIMESTAMP NOT NULL,
    period_end TIMESTAMP NOT NULL,
    
    -- Amount
    amount DECIMAL(10, 2) NOT NULL,
    fiat_currency VARCHAR(10) DEFAULT 'USD',
    
    -- Status
    status VARCHAR(20) DEFAULT 'created',
    paid_at TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT NOW() NOT NULL
);

CREATE INDEX idx_subscription_payments_subscription ON subscription_payments(subscription_id);


-- ============================================================================
-- REFUNDS
-- ============================================================================

CREATE TYPE refund_status AS ENUM ('pending', 'processing', 'completed', 'failed');

CREATE TABLE IF NOT EXISTS refunds (
    id VARCHAR(50) PRIMARY KEY,  -- ref_xxx format
    payment_session_id VARCHAR(100) NOT NULL REFERENCES payment_sessions(id),
    merchant_id UUID NOT NULL REFERENCES merchants(id),
    
    -- Refund details
    amount DECIMAL(14, 6) NOT NULL,
    token VARCHAR(10) NOT NULL,
    chain VARCHAR(20) NOT NULL,
    
    -- Destination
    refund_address VARCHAR(100) NOT NULL,
    
    -- Status
    status refund_status DEFAULT 'pending',
    
    -- Transaction
    tx_hash VARCHAR(100),
    
    -- Reason
    reason TEXT,
    
    -- Initiated by
    initiated_by UUID,
    
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    processed_at TIMESTAMP,
    completed_at TIMESTAMP
);

CREATE INDEX idx_refunds_merchant ON refunds(merchant_id);
CREATE INDEX idx_refunds_session ON refunds(payment_session_id);
CREATE INDEX idx_refunds_status ON refunds(status);


-- ============================================================================
-- MERCHANT TEAM
-- ============================================================================

CREATE TYPE merchant_role AS ENUM ('owner', 'admin', 'developer', 'finance', 'viewer');

CREATE TABLE IF NOT EXISTS merchant_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id UUID NOT NULL REFERENCES merchants(id),
    
    -- User info
    email VARCHAR(255) NOT NULL,
    name VARCHAR(255),
    password_hash VARCHAR(255),
    
    -- Role
    role merchant_role DEFAULT 'viewer',
    
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    invite_token VARCHAR(255),
    invite_expires TIMESTAMP,
    last_login TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW(),
    
    UNIQUE(merchant_id, email)
);

CREATE INDEX idx_merchant_users_merchant ON merchant_users(merchant_id);
CREATE INDEX idx_merchant_users_email ON merchant_users(email);


-- ============================================================================
-- IDEMPOTENCY KEYS
-- ============================================================================

CREATE TABLE IF NOT EXISTS idempotency_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key VARCHAR(100) NOT NULL UNIQUE,
    merchant_id UUID NOT NULL REFERENCES merchants(id),
    
    -- Request info
    endpoint VARCHAR(200) NOT NULL,
    request_hash VARCHAR(64),
    
    -- Response
    response_code INTEGER,
    response_body JSONB,
    
    -- Status
    is_processing BOOLEAN DEFAULT FALSE,
    completed BOOLEAN DEFAULT FALSE,
    
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    expires_at TIMESTAMP NOT NULL
);

CREATE INDEX idx_idempotency_keys_key ON idempotency_keys(key);
CREATE INDEX idx_idempotency_keys_merchant_key ON idempotency_keys(merchant_id, key);


-- ============================================================================
-- EVENT QUEUE
-- ============================================================================

CREATE TABLE IF NOT EXISTS events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id UUID REFERENCES merchants(id),
    
    -- Event info
    event_type VARCHAR(50) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    entity_id VARCHAR(100) NOT NULL,
    
    -- Payload
    payload JSONB NOT NULL,
    
    -- Processing status
    status VARCHAR(20) DEFAULT 'pending',
    attempts INTEGER DEFAULT 0,
    last_attempt TIMESTAMP,
    error_message TEXT,
    
    -- Timing
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    processed_at TIMESTAMP,
    scheduled_for TIMESTAMP
);

CREATE INDEX idx_events_type ON events(event_type);
CREATE INDEX idx_events_status ON events(status);
CREATE INDEX idx_events_status_created ON events(status, created_at);


-- ============================================================================
-- WEBHOOK DELIVERIES
-- ============================================================================

CREATE TABLE IF NOT EXISTS webhook_deliveries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id UUID NOT NULL REFERENCES merchants(id),
    event_id UUID REFERENCES events(id),
    
    -- Webhook details
    url VARCHAR(500) NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    payload JSONB NOT NULL,
    
    -- Delivery status
    status VARCHAR(20) DEFAULT 'pending',
    http_status INTEGER,
    response_body TEXT,
    
    -- Attempts
    attempt_count INTEGER DEFAULT 0,
    next_retry TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    delivered_at TIMESTAMP
);

CREATE INDEX idx_webhook_deliveries_merchant ON webhook_deliveries(merchant_id);
CREATE INDEX idx_webhook_deliveries_status ON webhook_deliveries(status);


-- ============================================================================
-- ANALYTICS SNAPSHOTS
-- ============================================================================

CREATE TABLE IF NOT EXISTS analytics_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id UUID NOT NULL REFERENCES merchants(id),
    
    -- Time period
    date TIMESTAMP NOT NULL,
    period VARCHAR(20) DEFAULT 'daily',
    
    -- Payment metrics
    total_payments INTEGER DEFAULT 0,
    successful_payments INTEGER DEFAULT 0,
    failed_payments INTEGER DEFAULT 0,
    
    -- Volume
    total_volume_usd DECIMAL(14, 2) DEFAULT 0,
    
    -- By token/chain
    volume_by_token JSONB,
    payments_by_token JSONB,
    volume_by_chain JSONB,
    payments_by_chain JSONB,
    
    -- Conversions
    sessions_created INTEGER DEFAULT 0,
    conversion_rate DECIMAL(5, 2),
    
    -- Averages
    avg_payment_usd DECIMAL(10, 2),
    avg_confirmation_time INTEGER,
    
    -- Invoices
    invoices_sent INTEGER DEFAULT 0,
    invoices_paid INTEGER DEFAULT 0,
    invoice_volume_usd DECIMAL(14, 2) DEFAULT 0,
    
    -- Subscriptions
    active_subscriptions INTEGER DEFAULT 0,
    new_subscriptions INTEGER DEFAULT 0,
    churned_subscriptions INTEGER DEFAULT 0,
    subscription_revenue_usd DECIMAL(14, 2) DEFAULT 0,
    
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    
    UNIQUE(merchant_id, date, period)
);

CREATE INDEX idx_analytics_merchant ON analytics_snapshots(merchant_id);
CREATE INDEX idx_analytics_merchant_date ON analytics_snapshots(merchant_id, date);


-- ============================================================================
-- RISK SIGNALS
-- ============================================================================

CREATE TABLE IF NOT EXISTS risk_signals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id UUID REFERENCES merchants(id),
    payment_session_id VARCHAR(100) REFERENCES payment_sessions(id),
    
    -- Signal details
    signal_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) DEFAULT 'low',
    
    -- Context
    wallet_address VARCHAR(100),
    ip_address VARCHAR(50),
    user_agent TEXT,
    
    -- Details
    description TEXT,
    details JSONB,
    
    -- Action taken
    action_taken VARCHAR(50),
    reviewed BOOLEAN DEFAULT FALSE,
    reviewed_by UUID,
    reviewed_at TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT NOW() NOT NULL
);

CREATE INDEX idx_risk_signals_merchant ON risk_signals(merchant_id);
CREATE INDEX idx_risk_signals_severity ON risk_signals(severity);
CREATE INDEX idx_risk_signals_type ON risk_signals(signal_type);


-- ============================================================================
-- API KEYS
-- ============================================================================

CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id UUID NOT NULL REFERENCES merchants(id),
    
    -- Key details
    key_prefix VARCHAR(10) NOT NULL,
    key_hash VARCHAR(255) NOT NULL,
    name VARCHAR(100),
    
    -- Permissions
    permissions JSONB,
    
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    last_used TIMESTAMP,
    
    -- Rate limiting
    rate_limit INTEGER DEFAULT 100,
    
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    expires_at TIMESTAMP
);

CREATE INDEX idx_api_keys_merchant ON api_keys(merchant_id);
CREATE INDEX idx_api_keys_prefix ON api_keys(key_prefix);


-- ============================================================================
-- CLEANUP FUNCTIONS
-- ============================================================================

-- Function to clean expired idempotency keys (run daily)
CREATE OR REPLACE FUNCTION cleanup_expired_idempotency_keys()
RETURNS void AS $$
BEGIN
    DELETE FROM idempotency_keys WHERE expires_at < NOW();
END;
$$ LANGUAGE plpgsql;

-- Function to mark overdue invoices
CREATE OR REPLACE FUNCTION mark_overdue_invoices()
RETURNS void AS $$
BEGIN
    UPDATE invoices 
    SET status = 'overdue', updated_at = NOW()
    WHERE status = 'sent' 
      AND due_date < NOW();
END;
$$ LANGUAGE plpgsql;
