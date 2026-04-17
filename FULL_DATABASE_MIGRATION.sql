"""
Database Migration: Add api_key column to merchants table

Run this SQL directly in PostgreSQL to add the api_key field to existing merchants table.
"""

-- Step 1: Add the api_key column
ALTER TABLE merchants 
ADD COLUMN IF NOT EXISTS api_key VARCHAR UNIQUE;

-- Step 2: Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_merchants_api_key ON merchants(api_key);

-- Step 3: Verify the column was added
SELECT column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'merchants' AND column_name = 'api_key';

-- Expected result:
-- column_name | data_type | is_nullable
-- api_key     | character varying | YES
-- Migration: Add Currency Preference Fields to Merchants Table
-- Description: Adds currency_preference, currency_locale, and currency_decimal_places
--              fields to support backend-driven currency handling with proper formatting.
-- Date: 2026-04-12

-- Add new currency preference columns
ALTER TABLE merchants 
ADD COLUMN IF NOT EXISTS currency_preference VARCHAR(10) DEFAULT 'USD' NOT NULL,
ADD COLUMN IF NOT EXISTS currency_locale VARCHAR(10) DEFAULT 'en_US' NOT NULL,
ADD COLUMN IF NOT EXISTS currency_decimal_places INTEGER DEFAULT 2 NOT NULL;

-- Create index on currency_preference for faster lookups
CREATE INDEX IF NOT EXISTS idx_merchants_currency_preference 
ON merchants(currency_preference);

-- Update existing merchants to use their base_currency as currency_preference
UPDATE merchants 
SET currency_preference = COALESCE(base_currency, 'USD')
WHERE currency_preference = 'USD';

-- Set locale based on country (best effort mapping)
UPDATE merchants
SET currency_locale = CASE
    WHEN country = 'United States' OR country = 'US' THEN 'en_US'
    WHEN country = 'United Kingdom' OR country = 'UK' THEN 'en_GB'
    WHEN country = 'India' THEN 'en_IN'
    WHEN country = 'Germany' THEN 'de_DE'
    WHEN country = 'France' THEN 'fr_FR'
    WHEN country = 'Spain' THEN 'es_ES'
    WHEN country = 'Italy' THEN 'it_IT'
    WHEN country = 'Japan' THEN 'ja_JP'
    WHEN country = 'China' THEN 'zh_CN'
    WHEN country = 'Brazil' THEN 'pt_BR'
    WHEN country = 'Canada' THEN 'en_CA'
    WHEN country = 'Australia' THEN 'en_AU'
    ELSE 'en_US'
END
WHERE currency_locale = 'en_US';

-- Set decimal places based on currency
UPDATE merchants
SET currency_decimal_places = CASE
    WHEN currency_preference IN ('JPY', 'KRW', 'VND', 'CLP') THEN 0  -- No decimal places
    WHEN currency_preference IN ('BTC', 'ETH') THEN 8  -- Crypto currencies
    ELSE 2  -- Standard fiat currencies
END;

-- Add comment to table
COMMENT ON COLUMN merchants.currency_preference IS 'ISO 4217 currency code for merchant''s preferred currency';
COMMENT ON COLUMN merchants.currency_locale IS 'Locale string for currency formatting (e.g., en_US, en_IN, de_DE)';
COMMENT ON COLUMN merchants.currency_decimal_places IS 'Number of decimal places for currency formatting';

-- Rollback script (commented out, uncomment to rollback)
-- DROP INDEX IF EXISTS idx_merchants_currency_preference;
-- ALTER TABLE merchants DROP COLUMN IF EXISTS currency_preference;
-- ALTER TABLE merchants DROP COLUMN IF EXISTS currency_locale;
-- ALTER TABLE merchants DROP COLUMN IF EXISTS currency_decimal_places;
-- Add first_failed_at column to track when first payment failure occurred
-- This enables accurate grace period calculations

ALTER TABLE web3_subscriptions 
ADD COLUMN IF NOT EXISTS first_failed_at TIMESTAMP NULL;

-- Add comment for documentation
COMMENT ON COLUMN web3_subscriptions.first_failed_at IS 'Timestamp of first payment failure for accurate grace period tracking';

-- Create index for efficient queries
CREATE INDEX IF NOT EXISTS idx_web3_subs_first_failed 
ON web3_subscriptions(first_failed_at) 
WHERE first_failed_at IS NOT NULL;
-- Migration: Add payment_started_at to payment_sessions
-- Description: Add payment_started_at column to track when user starts payment
-- Version: 2026-04-09

BEGIN;

-- Add payment_started_at column
ALTER TABLE payment_sessions
ADD COLUMN payment_started_at TIMESTAMP NULL;

-- Add comment for clarity
COMMENT ON COLUMN payment_sessions.payment_started_at IS 'Timestamp when user starts payment (opens checkout page or initiates payment). Used for 15-minute timeout calculation.';

-- Create index for expiration queries
CREATE INDEX IF NOT EXISTS idx_payment_sessions_payment_started_at 
ON payment_sessions(payment_started_at);

COMMIT;
-- Team RBAC Database Migration
-- Creates tables and columns for role-based access control system

-- ============================================
-- 1. CREATE NEW TABLES
-- ============================================

-- Permissions table: Defines all available permissions
CREATE TABLE IF NOT EXISTS permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(100) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    category VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_permissions_code ON permissions(code);
CREATE INDEX idx_permissions_category ON permissions(category);

-- Role permissions table: Maps permissions to roles
CREATE TABLE IF NOT EXISTS role_permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role VARCHAR(50) NOT NULL,
    permission_id UUID NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(role, permission_id)
);

CREATE INDEX idx_role_permissions_role ON role_permissions(role);
CREATE INDEX idx_role_permissions_permission ON role_permissions(permission_id);

-- Team member permissions table: Custom permission grants/revokes per team member
CREATE TABLE IF NOT EXISTS team_member_permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_member_id UUID NOT NULL REFERENCES merchant_users(id) ON DELETE CASCADE,
    permission_id UUID NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    granted BOOLEAN DEFAULT true NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    created_by UUID REFERENCES merchant_users(id),
    UNIQUE(team_member_id, permission_id)
);

CREATE INDEX idx_member_permissions_member ON team_member_permissions(team_member_id);
CREATE INDEX idx_member_permissions_permission ON team_member_permissions(permission_id);
CREATE INDEX idx_member_permissions_granted ON team_member_permissions(granted);

-- Activity logs table: Audit trail for all team member actions
CREATE TABLE IF NOT EXISTS activity_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id UUID NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
    team_member_id UUID REFERENCES merchant_users(id) ON DELETE SET NULL,
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50),
    resource_id VARCHAR(255),
    details JSONB,
    ip_address VARCHAR(45),
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_activity_logs_merchant ON activity_logs(merchant_id);
CREATE INDEX idx_activity_logs_member ON activity_logs(team_member_id);
CREATE INDEX idx_activity_logs_action ON activity_logs(action);
CREATE INDEX idx_activity_logs_created ON activity_logs(created_at);
CREATE INDEX idx_activity_logs_merchant_member ON activity_logs(merchant_id, team_member_id);
CREATE INDEX idx_activity_logs_action_created ON activity_logs(action, created_at);

-- Team member sessions table: Track active sessions
CREATE TABLE IF NOT EXISTS team_member_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_member_id UUID NOT NULL REFERENCES merchant_users(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) NOT NULL,
    ip_address VARCHAR(45),
    user_agent TEXT,
    expires_at TIMESTAMP NOT NULL,
    last_activity TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW(),
    revoked_at TIMESTAMP
);

CREATE INDEX idx_sessions_member ON team_member_sessions(team_member_id);
CREATE INDEX idx_sessions_token ON team_member_sessions(token_hash);
CREATE INDEX idx_sessions_expires ON team_member_sessions(expires_at);
CREATE INDEX idx_sessions_member_active ON team_member_sessions(team_member_id, revoked_at);

-- ============================================
-- 2. ADD COLUMNS TO EXISTING TABLES
-- ============================================

-- Add password reset and security columns to merchant_users
ALTER TABLE merchant_users 
ADD COLUMN IF NOT EXISTS password_reset_token VARCHAR(255),
ADD COLUMN IF NOT EXISTS password_reset_expires_at TIMESTAMP,
ADD COLUMN IF NOT EXISTS failed_login_attempts INT DEFAULT 0 NOT NULL,
ADD COLUMN IF NOT EXISTS locked_until TIMESTAMP,
ADD COLUMN IF NOT EXISTS created_by UUID REFERENCES merchant_users(id);

-- Add index for password reset token lookups
CREATE INDEX IF NOT EXISTS idx_merchant_users_reset_token ON merchant_users(password_reset_token);

-- ============================================
-- 3. COMMENTS FOR DOCUMENTATION
-- ============================================

COMMENT ON TABLE permissions IS 'Defines all available permissions in the system';
COMMENT ON TABLE role_permissions IS 'Maps default permissions to each role';
COMMENT ON TABLE team_member_permissions IS 'Custom permission grants/revokes per team member';
COMMENT ON TABLE activity_logs IS 'Audit trail for all team member actions';
COMMENT ON TABLE team_member_sessions IS 'Tracks active team member sessions';

COMMENT ON COLUMN team_member_permissions.granted IS 'true = grant permission, false = revoke permission';
COMMENT ON COLUMN merchant_users.failed_login_attempts IS 'Counter for failed login attempts (resets on successful login)';
COMMENT ON COLUMN merchant_users.locked_until IS 'Account locked until this timestamp (null = not locked)';
COMMENT ON COLUMN merchant_users.created_by IS 'Team member who created this account';
-- Add coupon tracking fields to payment_sessions table
-- Run after: promo_codes.sql

ALTER TABLE payment_sessions
    ADD COLUMN IF NOT EXISTS coupon_code VARCHAR(50),
    ADD COLUMN IF NOT EXISTS discount_amount NUMERIC(14, 2);

CREATE INDEX IF NOT EXISTS idx_payment_sessions_coupon ON payment_sessions(coupon_code)
    WHERE coupon_code IS NOT NULL;
-- Migration: Add currency fields to merchants + PENDING_PAYMENT subscription status
-- Date: 2025-01-XX

-- 1. Add currency fields to merchants table
ALTER TABLE merchants ADD COLUMN IF NOT EXISTS base_currency VARCHAR(10) NOT NULL DEFAULT 'USD';
ALTER TABLE merchants ADD COLUMN IF NOT EXISTS currency_symbol VARCHAR(10) NOT NULL DEFAULT '$';
ALTER TABLE merchants ADD COLUMN IF NOT EXISTS currency_name VARCHAR(50) NOT NULL DEFAULT 'US Dollar';

-- 2. Add pending_payment to subscription status enum
-- PostgreSQL requires explicit ALTER TYPE for enums
ALTER TYPE subscriptionstatus ADD VALUE IF NOT EXISTS 'pending_payment';

-- 3. Backfill existing merchants with currency from their country
-- (Run the Python script below after this migration for accurate mapping)
-- UPDATE merchants SET base_currency = 'INR', currency_symbol = 'â‚¹', currency_name = 'Indian Rupee' WHERE country = 'India';
-- UPDATE merchants SET base_currency = 'EUR', currency_symbol = 'â‚¬', currency_name = 'Euro' WHERE country IN ('Germany', 'France', 'Italy', 'Spain', 'Netherlands');
-- etc.

-- 4. Index for faster currency-based queries (optional)
CREATE INDEX IF NOT EXISTS idx_merchants_base_currency ON merchants(base_currency);
-- Migration: Dual Currency, Tokenization, Cross-border, and Risk Scoring
-- Adds fields for payer/merchant dual currency tracking, cross-border detection,
-- auto-tokenization, and fraud risk scoring to payment_sessions.

-- â”€â”€ Tokenization â”€â”€
ALTER TABLE payment_sessions
    ADD COLUMN IF NOT EXISTS is_tokenized BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS token_created_at TIMESTAMP;

-- â”€â”€ Dual Currency: Payer â”€â”€
ALTER TABLE payment_sessions
    ADD COLUMN IF NOT EXISTS payer_currency VARCHAR(10),
    ADD COLUMN IF NOT EXISTS payer_currency_symbol VARCHAR(10),
    ADD COLUMN IF NOT EXISTS payer_amount_local NUMERIC(14, 2),
    ADD COLUMN IF NOT EXISTS payer_exchange_rate NUMERIC(18, 8);

-- â”€â”€ Dual Currency: Merchant â”€â”€
ALTER TABLE payment_sessions
    ADD COLUMN IF NOT EXISTS merchant_currency VARCHAR(10),
    ADD COLUMN IF NOT EXISTS merchant_currency_symbol VARCHAR(10),
    ADD COLUMN IF NOT EXISTS merchant_amount_local NUMERIC(14, 2),
    ADD COLUMN IF NOT EXISTS merchant_exchange_rate NUMERIC(18, 8);

-- â”€â”€ Cross-border / Compliance â”€â”€
ALTER TABLE payment_sessions
    ADD COLUMN IF NOT EXISTS is_cross_border BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS payer_country VARCHAR(100),
    ADD COLUMN IF NOT EXISTS risk_score NUMERIC(5, 2),
    ADD COLUMN IF NOT EXISTS risk_flags JSONB;

-- â”€â”€ Indexes for common queries â”€â”€
CREATE INDEX IF NOT EXISTS idx_payment_sessions_payer_currency
    ON payment_sessions (payer_currency);
CREATE INDEX IF NOT EXISTS idx_payment_sessions_merchant_currency
    ON payment_sessions (merchant_currency);
CREATE INDEX IF NOT EXISTS idx_payment_sessions_is_cross_border
    ON payment_sessions (is_cross_border) WHERE is_cross_border = TRUE;
CREATE INDEX IF NOT EXISTS idx_payment_sessions_risk_score
    ON payment_sessions (risk_score) WHERE risk_score IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_payment_sessions_is_tokenized
    ON payment_sessions (is_tokenized) WHERE is_tokenized = TRUE;
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
-- ============================================================
-- Migration: v2.2.0 Enterprise Infrastructure Upgrade
-- ============================================================
-- Adds:
--   1. PROCESSING / CONFIRMED status to payment_sessions
--   2. ledger_entries table (immutable double-entry ledger)
--   3. payment_state_transitions table (state machine audit)
--   4. compliance_screenings table (AML/OFAC audit)
--   5. Indexes for new tables
-- ============================================================

-- 1. Payment status: add PROCESSING and CONFIRMED values ----
-- PostgreSQL enums need ALTER TYPE; SQLite ignores this.
DO $$
BEGIN
    -- Add 'processing' if not exists
    IF NOT EXISTS (
        SELECT 1 FROM pg_enum
        WHERE enumlabel = 'processing'
          AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'paymentstatus')
    ) THEN
        ALTER TYPE paymentstatus ADD VALUE 'processing';
    END IF;

    -- Add 'confirmed' if not exists
    IF NOT EXISTS (
        SELECT 1 FROM pg_enum
        WHERE enumlabel = 'confirmed'
          AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'paymentstatus')
    ) THEN
        ALTER TYPE paymentstatus ADD VALUE 'confirmed';
    END IF;
END $$;


-- 2. Ledger Entries -----------------------------------------
CREATE TABLE IF NOT EXISTS ledger_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id UUID NOT NULL REFERENCES merchants(id),
    session_id VARCHAR REFERENCES payment_sessions(id),

    entry_type VARCHAR(30) NOT NULL,  -- debit, credit, conversion, settlement, fee, refund_debit, refund_credit
    amount NUMERIC(20, 8) NOT NULL,
    currency VARCHAR(10) NOT NULL,
    direction VARCHAR(6) NOT NULL,    -- debit or credit

    counter_amount NUMERIC(20, 8),
    counter_currency VARCHAR(10),
    exchange_rate NUMERIC(18, 8),

    reference_type VARCHAR(50),
    reference_id VARCHAR,
    description VARCHAR(500),

    balance_after NUMERIC(20, 8),

    entry_hash VARCHAR(64) NOT NULL,
    prev_hash VARCHAR(64),

    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_ledger_merchant ON ledger_entries(merchant_id);
CREATE INDEX IF NOT EXISTS ix_ledger_session ON ledger_entries(session_id);
CREATE INDEX IF NOT EXISTS ix_ledger_type ON ledger_entries(entry_type);
CREATE INDEX IF NOT EXISTS ix_ledger_created ON ledger_entries(created_at);


-- 3. Payment State Transitions ------------------------------
CREATE TABLE IF NOT EXISTS payment_state_transitions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id VARCHAR NOT NULL REFERENCES payment_sessions(id),
    from_state VARCHAR(30) NOT NULL,
    to_state VARCHAR(30) NOT NULL,
    trigger VARCHAR(100),
    actor VARCHAR(200),
    metadata JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_transitions_session ON payment_state_transitions(session_id);
CREATE INDEX IF NOT EXISTS ix_transitions_created ON payment_state_transitions(created_at);


-- 4. Compliance Screenings ----------------------------------
CREATE TABLE IF NOT EXISTS compliance_screenings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id VARCHAR REFERENCES payment_sessions(id),
    merchant_id UUID REFERENCES merchants(id),

    screening_type VARCHAR(50) NOT NULL,  -- ofac, jurisdiction, threshold, velocity
    result VARCHAR(20) NOT NULL,          -- pass, flag, block
    risk_level VARCHAR(20),               -- low, medium, high, critical

    entity_type VARCHAR(50),
    entity_value VARCHAR(255),
    country VARCHAR(100),

    details JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_compliance_session ON compliance_screenings(session_id);
CREATE INDEX IF NOT EXISTS ix_compliance_result ON compliance_screenings(result);
CREATE INDEX IF NOT EXISTS ix_compliance_created ON compliance_screenings(created_at);


-- 5. Add ledger entry type enum (for strict PG type safety) --
-- Not strictly required since we use VARCHAR, but good practice.
-- DO $$
-- BEGIN
--     CREATE TYPE ledger_entry_type AS ENUM (
--         'debit', 'credit', 'conversion', 'settlement', 'fee', 'refund_debit', 'refund_credit'
--     );
-- EXCEPTION
--     WHEN duplicate_object THEN NULL;
-- END $$;
-- Migration: Multi-chain upgrade for Dari for Business
-- Description: Adds support for multi-chain stablecoin payments (USDC, USDT, PYUSD)
-- across Stellar, Ethereum, Polygon, Base, Tron, and Solana
-- Date: 2025-01-XX

-- =============================================================================
-- 1. CREATE NEW TABLES
-- =============================================================================

-- Supported tokens registry
CREATE TABLE IF NOT EXISTS tokens (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    name VARCHAR(50) NOT NULL,
    chain VARCHAR(20) NOT NULL,
    contract_address VARCHAR(100),
    decimals INTEGER DEFAULT 6,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, chain)
);

-- Merchant wallets per chain
CREATE TABLE IF NOT EXISTS merchant_wallets (
    id SERIAL PRIMARY KEY,
    merchant_id INTEGER NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
    chain VARCHAR(20) NOT NULL,
    wallet_address VARCHAR(100) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    is_verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(merchant_id, chain)
);

-- Payment events for audit trail
CREATE TABLE IF NOT EXISTS payment_events (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(50) NOT NULL REFERENCES payment_sessions(id) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL,
    data JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- 2. UPDATE PAYMENT_SESSIONS TABLE
-- =============================================================================

-- Add new columns for multi-chain support
ALTER TABLE payment_sessions ADD COLUMN IF NOT EXISTS token VARCHAR(10);
ALTER TABLE payment_sessions ADD COLUMN IF NOT EXISTS chain VARCHAR(20);
ALTER TABLE payment_sessions ADD COLUMN IF NOT EXISTS amount_token DECIMAL(20, 8);
ALTER TABLE payment_sessions ADD COLUMN IF NOT EXISTS accepted_tokens TEXT;
ALTER TABLE payment_sessions ADD COLUMN IF NOT EXISTS accepted_chains TEXT;
ALTER TABLE payment_sessions ADD COLUMN IF NOT EXISTS merchant_wallet VARCHAR(100);
ALTER TABLE payment_sessions ADD COLUMN IF NOT EXISTS deposit_address VARCHAR(100);
ALTER TABLE payment_sessions ADD COLUMN IF NOT EXISTS block_number BIGINT;
ALTER TABLE payment_sessions ADD COLUMN IF NOT EXISTS confirmations INTEGER DEFAULT 0;

-- =============================================================================
-- 3. POPULATE DEFAULT TOKENS
-- =============================================================================

INSERT INTO tokens (symbol, name, chain, contract_address, decimals) VALUES
-- Stellar
('USDC', 'USD Coin', 'stellar', 'GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN', 7),

-- Ethereum
('USDC', 'USD Coin', 'ethereum', '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48', 6),
('USDT', 'Tether USD', 'ethereum', '0xdAC17F958D2ee523a2206206994597C13D831ec7', 6),
('PYUSD', 'PayPal USD', 'ethereum', '0x6c3ea9036406852006290770BEdFcAbA0e23A0e8', 6),

-- Polygon
('USDC', 'USD Coin', 'polygon', '0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359', 6),
('USDT', 'Tether USD', 'polygon', '0xc2132D05D31c914a87C6611C10748AEb04B58e8F', 6),

-- Base
('USDC', 'USD Coin', 'base', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913', 6),

-- Tron
('USDT', 'Tether USD', 'tron', 'TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t', 6),
('USDC', 'USD Coin', 'tron', 'TEkxiTehnzSmSe2XqrBj4w32RUN966rdz8', 6)

ON CONFLICT (symbol, chain) DO NOTHING;

-- =============================================================================
-- 4. CREATE INDEXES
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_merchant_wallets_merchant_id ON merchant_wallets(merchant_id);
CREATE INDEX IF NOT EXISTS idx_merchant_wallets_chain ON merchant_wallets(chain);
CREATE INDEX IF NOT EXISTS idx_payment_events_session_id ON payment_events(session_id);
CREATE INDEX IF NOT EXISTS idx_payment_sessions_chain ON payment_sessions(chain);
CREATE INDEX IF NOT EXISTS idx_payment_sessions_token ON payment_sessions(token);
CREATE INDEX IF NOT EXISTS idx_tokens_chain ON tokens(chain);
CREATE INDEX IF NOT EXISTS idx_tokens_symbol ON tokens(symbol);

-- =============================================================================
-- 5. UPDATE FUNCTION FOR TIMESTAMP
-- =============================================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply trigger to merchant_wallets
DROP TRIGGER IF EXISTS update_merchant_wallets_updated_at ON merchant_wallets;
CREATE TRIGGER update_merchant_wallets_updated_at
    BEFORE UPDATE ON merchant_wallets
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- 6. MIGRATION NOTES
-- =============================================================================

-- After running this migration:
-- 1. Existing payment sessions retain backward compatibility via amount_usdc field
-- 2. New sessions should use token, chain, and amount_token fields
-- 3. Merchants need to add wallets for each chain they want to accept payments on
-- 4. The tokens table can be extended with additional tokens as needed

-- To rollback (if needed):
-- DROP TABLE IF EXISTS payment_events;
-- DROP TABLE IF EXISTS merchant_wallets;
-- DROP TABLE IF EXISTS tokens;
-- ALTER TABLE payment_sessions DROP COLUMN IF EXISTS token;
-- ALTER TABLE payment_sessions DROP COLUMN IF EXISTS chain;
-- ALTER TABLE payment_sessions DROP COLUMN IF EXISTS amount_token;
-- ALTER TABLE payment_sessions DROP COLUMN IF EXISTS accepted_tokens;
-- ALTER TABLE payment_sessions DROP COLUMN IF EXISTS accepted_chains;
-- ALTER TABLE payment_sessions DROP COLUMN IF EXISTS merchant_wallet;
-- ALTER TABLE payment_sessions DROP COLUMN IF EXISTS deposit_address;
-- ALTER TABLE payment_sessions DROP COLUMN IF EXISTS block_number;
-- ALTER TABLE payment_sessions DROP COLUMN IF EXISTS confirmations;
-- Normalize legacy uppercase subscription status values to lowercase values expected by ORM.
-- Safe to run multiple times.

ALTER TYPE subscription_status ADD VALUE IF NOT EXISTS 'pending_payment';
ALTER TYPE subscription_status ADD VALUE IF NOT EXISTS 'PENDING_PAYMENT';

UPDATE subscriptions
SET status = CASE status::text
    WHEN 'ACTIVE' THEN 'active'::subscription_status
    WHEN 'PAUSED' THEN 'paused'::subscription_status
    WHEN 'CANCELLED' THEN 'cancelled'::subscription_status
    WHEN 'PAST_DUE' THEN 'past_due'::subscription_status
    WHEN 'TRIALING' THEN 'trialing'::subscription_status
    WHEN 'PENDING_PAYMENT' THEN 'pending_payment'::subscription_status
    ELSE status
END
WHERE status::text IN (
    'ACTIVE', 'PAUSED', 'CANCELLED', 'PAST_DUE', 'TRIALING', 'PENDING_PAYMENT'
);
-- Onboarding Flow Migration
-- Adds merchant onboarding fields and Google OAuth support

-- Add onboarding columns to merchants table
ALTER TABLE merchants ADD COLUMN IF NOT EXISTS google_id VARCHAR(255) UNIQUE;
ALTER TABLE merchants ADD COLUMN IF NOT EXISTS merchant_category VARCHAR(50) DEFAULT 'individual';
ALTER TABLE merchants ADD COLUMN IF NOT EXISTS business_name VARCHAR(255);
ALTER TABLE merchants ADD COLUMN IF NOT EXISTS business_email VARCHAR(255);
ALTER TABLE merchants ADD COLUMN IF NOT EXISTS country VARCHAR(100);
ALTER TABLE merchants ADD COLUMN IF NOT EXISTS onboarding_completed BOOLEAN DEFAULT FALSE;
ALTER TABLE merchants ADD COLUMN IF NOT EXISTS onboarding_step INTEGER DEFAULT 0;
ALTER TABLE merchants ADD COLUMN IF NOT EXISTS avatar_url VARCHAR(500);

-- Make password_hash nullable (Google OAuth users may not have a password)
ALTER TABLE merchants ALTER COLUMN password_hash DROP NOT NULL;

-- Index for Google OAuth lookups
CREATE INDEX IF NOT EXISTS idx_merchants_google_id ON merchants(google_id);

-- Index for onboarding status
CREATE INDEX IF NOT EXISTS idx_merchants_onboarding ON merchants(onboarding_completed);
-- Migration: Add payer data collection & payment tokenization support
-- Date: 2026-03-08

-- 1. Add new columns to payment_sessions
ALTER TABLE payment_sessions ADD COLUMN IF NOT EXISTS collect_payer_data BOOLEAN DEFAULT FALSE;
ALTER TABLE payment_sessions ADD COLUMN IF NOT EXISTS payer_email VARCHAR(255);
ALTER TABLE payment_sessions ADD COLUMN IF NOT EXISTS payer_name VARCHAR(255);
ALTER TABLE payment_sessions ADD COLUMN IF NOT EXISTS payment_token VARCHAR(100);

-- Index for token lookups
CREATE INDEX IF NOT EXISTS ix_payment_sessions_payment_token ON payment_sessions(payment_token);

-- 2. Create payer_info table
CREATE TABLE IF NOT EXISTS payer_info (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id VARCHAR NOT NULL REFERENCES payment_sessions(id),
    merchant_id UUID NOT NULL REFERENCES merchants(id),

    -- Contact
    email VARCHAR(255),
    name VARCHAR(255),
    phone VARCHAR(50),

    -- Billing address
    billing_address_line1 VARCHAR(255),
    billing_address_line2 VARCHAR(255),
    billing_city VARCHAR(100),
    billing_state VARCHAR(100),
    billing_postal_code VARCHAR(20),
    billing_country VARCHAR(100),

    -- Shipping address
    shipping_address_line1 VARCHAR(255),
    shipping_city VARCHAR(100),
    shipping_state VARCHAR(100),
    shipping_postal_code VARCHAR(20),
    shipping_country VARCHAR(100),

    -- Metadata
    custom_fields JSON,

    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_payer_info_session_id ON payer_info(session_id);
CREATE INDEX IF NOT EXISTS ix_payer_info_merchant_id ON payer_info(merchant_id);
-- Promo Code / Coupon Management System
-- Migration: Add promo_codes and promo_code_usage tables

-- Promo Codes table
CREATE TABLE IF NOT EXISTS promo_codes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id UUID NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
    code VARCHAR(50) NOT NULL,
    type VARCHAR(20) NOT NULL CHECK (type IN ('percentage', 'fixed')),
    discount_value NUMERIC(14, 2) NOT NULL,
    max_discount_amount NUMERIC(14, 2),
    min_order_amount NUMERIC(14, 2) DEFAULT 0,
    usage_limit_total INTEGER,
    usage_limit_per_user INTEGER,
    used_count INTEGER NOT NULL DEFAULT 0,
    start_date TIMESTAMP NOT NULL,
    expiry_date TIMESTAMP NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'deleted')),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_promo_merchant_code UNIQUE (merchant_id, code)
);

CREATE INDEX IF NOT EXISTS idx_promo_codes_merchant_id ON promo_codes(merchant_id);
CREATE INDEX IF NOT EXISTS idx_promo_codes_code ON promo_codes(code);
CREATE INDEX IF NOT EXISTS idx_promo_codes_status ON promo_codes(status);

-- Promo Code Usage tracking table
CREATE TABLE IF NOT EXISTS promo_code_usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    promo_code_id UUID NOT NULL REFERENCES promo_codes(id) ON DELETE CASCADE,
    merchant_id UUID NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
    customer_id VARCHAR(255) NOT NULL,
    payment_id VARCHAR(255),
    discount_applied NUMERIC(14, 2) NOT NULL,
    used_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_promo_usage_code_id ON promo_code_usage(promo_code_id);
CREATE INDEX IF NOT EXISTS idx_promo_usage_customer ON promo_code_usage(promo_code_id, customer_id);
CREATE INDEX IF NOT EXISTS idx_promo_usage_merchant ON promo_code_usage(merchant_id);
-- Migration: Refund balance checks + Recurring payment trial features
-- Date: 2025-01-01
-- Description: Adds refund balance/settlement tracking fields, subscription trial features,
--              and customer payment method fields for end-to-end recurring payments.

-- ============= REFUNDS =============

-- Add refund source & balance tracking columns
ALTER TABLE refunds ADD COLUMN IF NOT EXISTS refund_source VARCHAR(30) DEFAULT 'platform_balance';
ALTER TABLE refunds ADD COLUMN IF NOT EXISTS merchant_balance_at_request NUMERIC(20, 8);
ALTER TABLE refunds ADD COLUMN IF NOT EXISTS settlement_status VARCHAR(30);
ALTER TABLE refunds ADD COLUMN IF NOT EXISTS insufficient_funds_at TIMESTAMP;
ALTER TABLE refunds ADD COLUMN IF NOT EXISTS queued_until TIMESTAMP;
ALTER TABLE refunds ADD COLUMN IF NOT EXISTS failure_reason VARCHAR(500);

-- Add new refund statuses to enum (PostgreSQL requires explicit ALTER TYPE)
-- Note: Only run these if the values don't already exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'QUEUED' AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'refundstatus')) THEN
        ALTER TYPE refundstatus ADD VALUE 'QUEUED';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'INSUFFICIENT_FUNDS' AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'refundstatus')) THEN
        ALTER TYPE refundstatus ADD VALUE 'INSUFFICIENT_FUNDS';
    END IF;
END
$$;

-- ============= SUBSCRIPTION PLANS =============

-- Trial features
ALTER TABLE subscription_plans ADD COLUMN IF NOT EXISTS trial_type VARCHAR(20) DEFAULT 'free';
ALTER TABLE subscription_plans ADD COLUMN IF NOT EXISTS trial_price NUMERIC(10, 2);

-- Setup fee
ALTER TABLE subscription_plans ADD COLUMN IF NOT EXISTS setup_fee NUMERIC(10, 2) DEFAULT 0;

-- Max billing cycles (null = unlimited)
ALTER TABLE subscription_plans ADD COLUMN IF NOT EXISTS max_billing_cycles INTEGER;

-- ============= SUBSCRIPTIONS =============

-- Trial tracking
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS trial_reminder_sent BOOLEAN DEFAULT FALSE;
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS trial_converted_at TIMESTAMP;

-- Payment statistics
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS total_payments_collected INTEGER DEFAULT 0;
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS total_revenue NUMERIC(14, 2) DEFAULT 0;

-- Customer payment method (for auto-billing)
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS customer_wallet_address VARCHAR(200);
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS customer_chain VARCHAR(20);
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS customer_token VARCHAR(10);

-- Billing configuration
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS max_payment_retries INTEGER DEFAULT 3;
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS grace_period_days INTEGER DEFAULT 3;
-- Seed Permission Data
-- Inserts all permission definitions and role-permission mappings

-- ============================================
-- 1. INSERT PERMISSION DEFINITIONS
-- ============================================

-- Payments permissions
INSERT INTO permissions (code, name, description, category) VALUES
('payments.view', 'View Payments', 'View payment transactions and details', 'payments'),
('payments.create', 'Create Payments', 'Create new payment sessions', 'payments'),
('payments.refund', 'Process Refunds', 'Initiate and process refunds', 'payments'),
('payments.export', 'Export Payments', 'Export payment data to CSV/Excel', 'payments')
ON CONFLICT (code) DO NOTHING;

-- Invoices permissions
INSERT INTO permissions (code, name, description, category) VALUES
('invoices.view', 'View Invoices', 'View invoice details', 'invoices'),
('invoices.create', 'Create Invoices', 'Create new invoices', 'invoices'),
('invoices.update', 'Update Invoices', 'Edit existing invoices', 'invoices'),
('invoices.delete', 'Delete Invoices', 'Delete invoices', 'invoices'),
('invoices.send', 'Send Invoices', 'Send invoices to customers', 'invoices')
ON CONFLICT (code) DO NOTHING;

-- Payment Links permissions
INSERT INTO permissions (code, name, description, category) VALUES
('payment_links.view', 'View Payment Links', 'View payment link details', 'payment_links'),
('payment_links.create', 'Create Payment Links', 'Create new payment links', 'payment_links'),
('payment_links.update', 'Update Payment Links', 'Edit existing payment links', 'payment_links'),
('payment_links.delete', 'Delete Payment Links', 'Delete payment links', 'payment_links')
ON CONFLICT (code) DO NOTHING;

-- Subscriptions permissions
INSERT INTO permissions (code, name, description, category) VALUES
('subscriptions.view', 'View Subscriptions', 'View subscription details', 'subscriptions'),
('subscriptions.create', 'Create Subscriptions', 'Create subscription plans', 'subscriptions'),
('subscriptions.update', 'Update Subscriptions', 'Edit subscription plans', 'subscriptions'),
('subscriptions.cancel', 'Cancel Subscriptions', 'Cancel active subscriptions', 'subscriptions')
ON CONFLICT (code) DO NOTHING;

-- Withdrawals permissions
INSERT INTO permissions (code, name, description, category) VALUES
('withdrawals.view', 'View Withdrawals', 'View withdrawal requests', 'withdrawals'),
('withdrawals.create', 'Create Withdrawals', 'Create withdrawal requests', 'withdrawals'),
('withdrawals.approve', 'Approve Withdrawals', 'Approve pending withdrawals', 'withdrawals')
ON CONFLICT (code) DO NOTHING;

-- Coupons permissions
INSERT INTO permissions (code, name, description, category) VALUES
('coupons.view', 'View Coupons', 'View coupon details', 'coupons'),
('coupons.create', 'Create Coupons', 'Create new coupons', 'coupons'),
('coupons.update', 'Update Coupons', 'Edit existing coupons', 'coupons'),
('coupons.delete', 'Delete Coupons', 'Delete coupons', 'coupons')
ON CONFLICT (code) DO NOTHING;

-- Team Management permissions
INSERT INTO permissions (code, name, description, category) VALUES
('team.view', 'View Team Members', 'View team member list and details', 'team'),
('team.create', 'Add Team Members', 'Invite and create team member accounts', 'team'),
('team.update', 'Update Team Members', 'Edit team member roles and permissions', 'team'),
('team.delete', 'Remove Team Members', 'Remove team members from account', 'team'),
('team.view_logs', 'View Activity Logs', 'View team member activity logs', 'team')
ON CONFLICT (code) DO NOTHING;

-- API & Integrations permissions
INSERT INTO permissions (code, name, description, category) VALUES
('api_keys.view', 'View API Keys', 'View API key details', 'integrations'),
('api_keys.manage', 'Manage API Keys', 'Create and delete API keys', 'integrations'),
('webhooks.view', 'View Webhooks', 'View webhook configurations', 'integrations'),
('webhooks.manage', 'Manage Webhooks', 'Create, update, and delete webhooks', 'integrations')
ON CONFLICT (code) DO NOTHING;

-- Analytics permissions
INSERT INTO permissions (code, name, description, category) VALUES
('analytics.view', 'View Analytics', 'View analytics dashboard and reports', 'analytics'),
('analytics.export', 'Export Analytics', 'Export analytics data', 'analytics')
ON CONFLICT (code) DO NOTHING;

-- Settings permissions
INSERT INTO permissions (code, name, description, category) VALUES
('settings.view', 'View Settings', 'View account settings', 'settings'),
('settings.update', 'Update Settings', 'Update account settings', 'settings'),
('settings.billing', 'Manage Billing', 'Manage billing and subscription plans', 'settings')
ON CONFLICT (code) DO NOTHING;

-- Wallets permissions
INSERT INTO permissions (code, name, description, category) VALUES
('wallets.view', 'View Wallets', 'View wallet addresses and balances', 'wallets'),
('wallets.manage', 'Manage Wallets', 'Add and remove wallet addresses', 'wallets')
ON CONFLICT (code) DO NOTHING;

-- ============================================
-- 2. INSERT ROLE-PERMISSION MAPPINGS
-- ============================================

-- OWNER role: All permissions (using wildcard in code, but explicit here for clarity)
INSERT INTO role_permissions (role, permission_id)
SELECT 'owner', id FROM permissions
ON CONFLICT (role, permission_id) DO NOTHING;

-- ADMIN role: Full access except billing
INSERT INTO role_permissions (role, permission_id)
SELECT 'admin', id FROM permissions WHERE code IN (
    -- Payments
    'payments.view', 'payments.create', 'payments.refund', 'payments.export',
    -- Invoices
    'invoices.view', 'invoices.create', 'invoices.update', 'invoices.delete', 'invoices.send',
    -- Payment Links
    'payment_links.view', 'payment_links.create', 'payment_links.update', 'payment_links.delete',
    -- Subscriptions
    'subscriptions.view', 'subscriptions.create', 'subscriptions.update', 'subscriptions.cancel',
    -- Withdrawals
    'withdrawals.view', 'withdrawals.create',
    -- Coupons
    'coupons.view', 'coupons.create', 'coupons.update', 'coupons.delete',
    -- Team
    'team.view', 'team.create', 'team.update', 'team.delete', 'team.view_logs',
    -- Integrations
    'api_keys.view', 'webhooks.view',
    -- Analytics
    'analytics.view', 'analytics.export',
    -- Settings
    'settings.view', 'settings.update',
    -- Wallets
    'wallets.view'
)
ON CONFLICT (role, permission_id) DO NOTHING;

-- DEVELOPER role: API, webhooks, payments view
INSERT INTO role_permissions (role, permission_id)
SELECT 'developer', id FROM permissions WHERE code IN (
    'payments.view',
    'invoices.view',
    'payment_links.view',
    'subscriptions.view',
    'api_keys.view', 'api_keys.manage',
    'webhooks.view', 'webhooks.manage',
    'analytics.view',
    'settings.view'
)
ON CONFLICT (role, permission_id) DO NOTHING;

-- FINANCE role: Payments, invoices, refunds, analytics
INSERT INTO role_permissions (role, permission_id)
SELECT 'finance', id FROM permissions WHERE code IN (
    -- Payments
    'payments.view', 'payments.create', 'payments.refund', 'payments.export',
    -- Invoices
    'invoices.view', 'invoices.create', 'invoices.update', 'invoices.delete', 'invoices.send',
    -- Payment Links
    'payment_links.view',
    -- Subscriptions
    'subscriptions.view',
    -- Withdrawals
    'withdrawals.view', 'withdrawals.create', 'withdrawals.approve',
    -- Coupons
    'coupons.view',
    -- Analytics
    'analytics.view', 'analytics.export',
    -- Settings
    'settings.view'
)
ON CONFLICT (role, permission_id) DO NOTHING;

-- VIEWER role: Read-only access
INSERT INTO role_permissions (role, permission_id)
SELECT 'viewer', id FROM permissions WHERE code IN (
    'payments.view',
    'invoices.view',
    'payment_links.view',
    'subscriptions.view',
    'withdrawals.view',
    'coupons.view',
    'analytics.view',
    'settings.view'
)
ON CONFLICT (role, permission_id) DO NOTHING;

-- ============================================
-- 3. VERIFICATION QUERIES
-- ============================================

-- Count permissions per role
SELECT 
    role,
    COUNT(*) as permission_count
FROM role_permissions
GROUP BY role
ORDER BY role;

-- Show all permissions
SELECT 
    category,
    COUNT(*) as permission_count
FROM permissions
GROUP BY category
ORDER BY category;
-- Add missing subscription status labels used by application code.
-- Safe to run multiple times.
ALTER TYPE subscription_status ADD VALUE IF NOT EXISTS 'PENDING_PAYMENT';
ALTER TYPE subscription_status ADD VALUE IF NOT EXISTS 'PENDING_PAYMENT';
-- Subscription Tiers Migration
-- Adds subscription plans, limits, and billing tracking

-- Add subscription_tier column to merchants table
ALTER TABLE merchants ADD COLUMN IF NOT EXISTS subscription_tier VARCHAR(20) DEFAULT 'free' NOT NULL;

-- Create merchant_subscriptions table
CREATE TABLE IF NOT EXISTS merchant_subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id UUID NOT NULL UNIQUE REFERENCES merchants(id) ON DELETE CASCADE,
    
    -- Subscription details (using VARCHAR instead of ENUM for compatibility)
    tier VARCHAR(20) NOT NULL DEFAULT 'free',
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    
    -- Billing
    monthly_price NUMERIC(10, 2) NOT NULL DEFAULT 0,
    transaction_fee_percent NUMERIC(4, 2) NOT NULL DEFAULT 1.5,
    
    -- Limits (null = unlimited)
    monthly_volume_limit NUMERIC(14, 2),
    payment_link_limit INTEGER,
    invoice_limit INTEGER,
    team_member_limit INTEGER NOT NULL DEFAULT 1,
    
    -- Usage tracking for current billing period
    current_volume NUMERIC(14, 2) NOT NULL DEFAULT 0,
    current_payment_links INTEGER NOT NULL DEFAULT 0,
    current_invoices INTEGER NOT NULL DEFAULT 0,
    
    -- Dates
    trial_ends_at TIMESTAMP,
    current_period_start TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    current_period_end TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP + INTERVAL '1 month'),
    cancelled_at TIMESTAMP,
    
    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- Check constraints for tier and status
    CONSTRAINT check_subscription_tier CHECK (tier IN ('free', 'growth', 'business', 'enterprise')),
    CONSTRAINT check_subscription_status CHECK (status IN ('active', 'past_due', 'cancelled', 'trialing'))
);

-- Index for quick merchant subscription lookups
CREATE INDEX IF NOT EXISTS idx_merchant_subscriptions_merchant_id ON merchant_subscriptions(merchant_id);
CREATE INDEX IF NOT EXISTS idx_merchant_subscriptions_tier ON merchant_subscriptions(tier);
CREATE INDEX IF NOT EXISTS idx_merchant_subscriptions_status ON merchant_subscriptions(status);

-- Function to automatically create free subscription for new merchants
CREATE OR REPLACE FUNCTION create_default_subscription()
RETURNS TRIGGER AS $$
BEGIN
    -- Create free tier subscription for new merchant
    INSERT INTO merchant_subscriptions (
        merchant_id,
        tier,
        status,
        monthly_price,
        transaction_fee_percent,
        monthly_volume_limit,
        payment_link_limit,
        invoice_limit,
        team_member_limit,
        current_period_end
    ) VALUES (
        NEW.id,
        'free',
        'active',
        0,
        1.5,  -- 1.5% transaction fee
        1000,  -- $1,000 monthly limit
        2,  -- 2 payment links
        5,  -- 5 invoices
        1,  -- 1 team member
        CURRENT_TIMESTAMP + INTERVAL '1 month'
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to create default subscription for new merchants
DROP TRIGGER IF EXISTS trigger_create_default_subscription ON merchants;
CREATE TRIGGER trigger_create_default_subscription
AFTER INSERT ON merchants
FOR EACH ROW
EXECUTE FUNCTION create_default_subscription();

-- Migrate existing merchants to free tier
INSERT INTO merchant_subscriptions (
    merchant_id,
    tier,
    status,
    monthly_price,
    transaction_fee_percent,
    monthly_volume_limit,
    payment_link_limit,
    invoice_limit,
    team_member_limit,
    current_period_end
)
SELECT 
    id,
    'free',
    'active',
    0,
    1.5,
    1000,
    2,
    5,
    1,
    CURRENT_TIMESTAMP + INTERVAL '1 month'
FROM merchants
WHERE id NOT IN (SELECT merchant_id FROM merchant_subscriptions);

-- Update all merchants subscription_tier to match their subscription
UPDATE merchants m
SET subscription_tier = s.tier
FROM merchant_subscriptions s
WHERE m.id = s.merchant_id;
-- Withdrawal Feature Migration
-- Supports withdrawals to external wallets across all blockchain networks

-- ============================================================
-- Withdrawals Table
-- ============================================================
CREATE TABLE IF NOT EXISTS withdrawals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    merchant_id UUID NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
    
    -- Amount
    amount NUMERIC(20, 8) NOT NULL,
    token VARCHAR(10) NOT NULL,           -- USDC, USDT, PYUSD
    chain VARCHAR(20) NOT NULL,           -- stellar, ethereum, polygon, base, tron
    
    -- Destination
    destination_address VARCHAR(200) NOT NULL,
    destination_memo VARCHAR(100),         -- For Stellar memo field
    
    -- Status tracking
    status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending, processing, completed, failed, cancelled
    
    -- Transaction details
    tx_hash VARCHAR(200),                  -- Blockchain transaction hash
    network_fee NUMERIC(20, 8),            -- Estimated/actual network fee
    platform_fee NUMERIC(20, 8) DEFAULT 0, -- Platform withdrawal fee
    
    -- Processing details
    submitted_at TIMESTAMP,                -- When sent to blockchain
    confirmed_at TIMESTAMP,                -- When confirmed on chain
    failed_reason VARCHAR(500),            -- Reason for failure
    
    -- Metadata
    notes VARCHAR(500),                    -- Merchant notes
    ip_address VARCHAR(45),                -- Request IP for security
    
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_withdrawals_merchant_id ON withdrawals(merchant_id);
CREATE INDEX IF NOT EXISTS idx_withdrawals_status ON withdrawals(status);
CREATE INDEX IF NOT EXISTS idx_withdrawals_chain ON withdrawals(chain);
CREATE INDEX IF NOT EXISTS idx_withdrawals_created_at ON withdrawals(created_at);
CREATE INDEX IF NOT EXISTS idx_withdrawals_tx_hash ON withdrawals(tx_hash);

-- Add balance tracking to merchants
ALTER TABLE merchants ADD COLUMN IF NOT EXISTS balance_usdc NUMERIC(20, 8) DEFAULT 0;
ALTER TABLE merchants ADD COLUMN IF NOT EXISTS balance_usdt NUMERIC(20, 8) DEFAULT 0;
ALTER TABLE merchants ADD COLUMN IF NOT EXISTS balance_pyusd NUMERIC(20, 8) DEFAULT 0;

-- Withdrawal limits table (per subscription tier)
CREATE TABLE IF NOT EXISTS withdrawal_limits (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tier VARCHAR(20) NOT NULL UNIQUE,          -- free, growth, business, enterprise
    daily_limit NUMERIC(20, 8) NOT NULL,       -- Max daily withdrawal
    min_withdrawal NUMERIC(20, 8) NOT NULL,    -- Minimum withdrawal amount
    max_per_transaction NUMERIC(20, 8) NOT NULL, -- Max per single withdrawal
    withdrawal_fee_percent NUMERIC(5, 2) DEFAULT 0, -- Fee percentage
    withdrawal_fee_flat NUMERIC(10, 2) DEFAULT 0,   -- Flat fee in USD
    cooldown_minutes INTEGER DEFAULT 0,             -- Minutes between withdrawals
    requires_2fa BOOLEAN DEFAULT FALSE
);

-- Insert default limits per tier
INSERT INTO withdrawal_limits (tier, daily_limit, min_withdrawal, max_per_transaction, withdrawal_fee_percent, withdrawal_fee_flat, cooldown_minutes, requires_2fa)
VALUES 
    ('free', 100, 5, 50, 1.0, 1.00, 60, FALSE),
    ('growth', 5000, 5, 2500, 0.5, 0.50, 15, FALSE),
    ('business', 25000, 1, 10000, 0.25, 0.00, 5, TRUE),
    ('enterprise', 100000, 1, 50000, 0.10, 0.00, 0, TRUE)
ON CONFLICT (tier) DO UPDATE 
SET daily_limit = EXCLUDED.daily_limit,
    min_withdrawal = EXCLUDED.min_withdrawal,
    max_per_transaction = EXCLUDED.max_per_transaction,
    withdrawal_fee_percent = EXCLUDED.withdrawal_fee_percent,
    withdrawal_fee_flat = EXCLUDED.withdrawal_fee_flat,
    cooldown_minutes = EXCLUDED.cooldown_minutes,
    requires_2fa = EXCLUDED.requires_2fa;
