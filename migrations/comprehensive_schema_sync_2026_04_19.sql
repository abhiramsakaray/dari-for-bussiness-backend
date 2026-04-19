-- ============================================================================
-- COMPREHENSIVE DATABASE MIGRATION
-- Date: 2026-04-19
-- Description: Synchronizes database schema with current application models
-- ============================================================================

BEGIN;

-- ============================================================================
-- 1. MERCHANTS TABLE - Add missing webhook rotation columns
-- ============================================================================

ALTER TABLE merchants 
ADD COLUMN IF NOT EXISTS webhook_secret_previous VARCHAR,
ADD COLUMN IF NOT EXISTS webhook_secret_rotated_at TIMESTAMP;

-- ============================================================================
-- 2. MERCHANT_SUBSCRIPTIONS TABLE - Ensure all columns exist
-- ============================================================================

-- Add missing usage tracking columns if they don't exist
ALTER TABLE merchant_subscriptions 
ADD COLUMN IF NOT EXISTS current_volume NUMERIC(14, 2) DEFAULT 0 NOT NULL,
ADD COLUMN IF NOT EXISTS current_payment_links INTEGER DEFAULT 0 NOT NULL,
ADD COLUMN IF NOT EXISTS current_invoices INTEGER DEFAULT 0 NOT NULL;

-- Add missing timestamp columns
ALTER TABLE merchant_subscriptions 
ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- ============================================================================
-- 3. FIX/CREATE TRIGGER FUNCTION FOR DEFAULT SUBSCRIPTION
-- ============================================================================

-- Drop existing trigger if it exists
DROP TRIGGER IF EXISTS create_merchant_subscription ON merchants;

-- Create or replace the trigger function with all required columns
-- Uses ON CONFLICT to handle duplicate merchant_id gracefully
CREATE OR REPLACE FUNCTION create_default_subscription()
RETURNS TRIGGER AS $$
BEGIN
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
        current_volume,
        current_payment_links,
        current_invoices,
        current_period_start,
        current_period_end,
        created_at
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
        0,  -- current_volume starts at 0
        0,  -- current_payment_links starts at 0
        0,  -- current_invoices starts at 0
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP + INTERVAL '1 month',
        CURRENT_TIMESTAMP
    )
    ON CONFLICT (merchant_id) DO NOTHING;  -- Gracefully handle duplicates
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Recreate the trigger
CREATE TRIGGER create_merchant_subscription
    AFTER INSERT ON merchants
    FOR EACH ROW
    EXECUTE FUNCTION create_default_subscription();

-- ============================================================================
-- 4. PAYMENT_SESSIONS TABLE - Ensure all multi-currency columns exist
-- ============================================================================

ALTER TABLE payment_sessions
ADD COLUMN IF NOT EXISTS payer_currency VARCHAR(10),
ADD COLUMN IF NOT EXISTS payer_currency_symbol VARCHAR(10),
ADD COLUMN IF NOT EXISTS payer_amount_local NUMERIC(14, 2),
ADD COLUMN IF NOT EXISTS payer_exchange_rate NUMERIC(18, 8),
ADD COLUMN IF NOT EXISTS merchant_currency VARCHAR(10),
ADD COLUMN IF NOT EXISTS merchant_currency_symbol VARCHAR(10),
ADD COLUMN IF NOT EXISTS merchant_amount_local NUMERIC(14, 2),
ADD COLUMN IF NOT EXISTS merchant_exchange_rate NUMERIC(18, 8),
ADD COLUMN IF NOT EXISTS is_cross_border BOOLEAN DEFAULT FALSE NOT NULL,
ADD COLUMN IF NOT EXISTS payer_country VARCHAR(100),
ADD COLUMN IF NOT EXISTS risk_score NUMERIC(5, 2),
ADD COLUMN IF NOT EXISTS risk_flags JSON;

-- ============================================================================
-- 5. INVOICES TABLE - Ensure blockchain and multi-currency columns exist
-- ============================================================================

ALTER TABLE invoices
ADD COLUMN IF NOT EXISTS tx_hash VARCHAR,
ADD COLUMN IF NOT EXISTS chain VARCHAR(20),
ADD COLUMN IF NOT EXISTS token_symbol VARCHAR(10),
ADD COLUMN IF NOT EXISTS token_amount VARCHAR,
ADD COLUMN IF NOT EXISTS payer_currency VARCHAR(10),
ADD COLUMN IF NOT EXISTS payer_amount_local NUMERIC(14, 2),
ADD COLUMN IF NOT EXISTS merchant_currency VARCHAR(10),
ADD COLUMN IF NOT EXISTS merchant_amount_local NUMERIC(14, 2);

-- ============================================================================
-- 6. PAYER_INFO TABLE - Ensure encrypted PII columns exist
-- ============================================================================

ALTER TABLE payer_info
ADD COLUMN IF NOT EXISTS email_encrypted BYTEA,
ADD COLUMN IF NOT EXISTS name_encrypted BYTEA,
ADD COLUMN IF NOT EXISTS phone_encrypted BYTEA;

-- ============================================================================
-- 7. REFUNDS TABLE - Ensure all tracking columns exist
-- ============================================================================

ALTER TABLE refunds
ADD COLUMN IF NOT EXISTS refund_source VARCHAR(30) DEFAULT 'platform_balance',
ADD COLUMN IF NOT EXISTS merchant_balance_at_request NUMERIC(20, 8),
ADD COLUMN IF NOT EXISTS settlement_status VARCHAR(30),
ADD COLUMN IF NOT EXISTS insufficient_funds_at TIMESTAMP,
ADD COLUMN IF NOT EXISTS queued_until TIMESTAMP,
ADD COLUMN IF NOT EXISTS failure_reason VARCHAR(500);

-- ============================================================================
-- 8. WEB3_SUBSCRIPTIONS TABLE - Ensure all columns exist
-- ============================================================================

ALTER TABLE web3_subscriptions
ADD COLUMN IF NOT EXISTS first_failed_at TIMESTAMP,
ADD COLUMN IF NOT EXISTS max_retries INTEGER DEFAULT 0 NOT NULL,
ADD COLUMN IF NOT EXISTS retry_interval_hours INTEGER DEFAULT 24 NOT NULL,
ADD COLUMN IF NOT EXISTS grace_period_days INTEGER DEFAULT 3,
ADD COLUMN IF NOT EXISTS paused_at TIMESTAMP,
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- ============================================================================
-- 9. MERCHANT_USERS TABLE - Ensure password reset columns exist
-- ============================================================================

ALTER TABLE merchant_users
ADD COLUMN IF NOT EXISTS password_reset_token VARCHAR(255),
ADD COLUMN IF NOT EXISTS password_reset_expires_at TIMESTAMP,
ADD COLUMN IF NOT EXISTS failed_login_attempts INTEGER DEFAULT 0 NOT NULL,
ADD COLUMN IF NOT EXISTS locked_until TIMESTAMP;

-- Add index for password reset token if it doesn't exist
CREATE INDEX IF NOT EXISTS idx_merchant_users_reset_token ON merchant_users(password_reset_token);

-- ============================================================================
-- 10. CREATE MISSING INDEXES FOR PERFORMANCE
-- ============================================================================

-- Payment sessions indexes
CREATE INDEX IF NOT EXISTS idx_payment_merchant_status ON payment_sessions(merchant_id, status);
CREATE INDEX IF NOT EXISTS idx_payment_created_at ON payment_sessions(created_at);

-- Refunds indexes
CREATE INDEX IF NOT EXISTS idx_refund_merchant_status ON refunds(merchant_id, status);
CREATE INDEX IF NOT EXISTS idx_refund_payment_session ON refunds(payment_session_id);
CREATE INDEX IF NOT EXISTS idx_refund_created_at ON refunds(created_at);

-- Withdrawals indexes
CREATE INDEX IF NOT EXISTS idx_withdrawals_merchant_id ON withdrawals(merchant_id);
CREATE INDEX IF NOT EXISTS idx_withdrawals_status ON withdrawals(status);
CREATE INDEX IF NOT EXISTS idx_withdrawals_chain ON withdrawals(chain);
CREATE INDEX IF NOT EXISTS idx_withdrawals_created_at ON withdrawals(created_at);

-- Analytics indexes
CREATE INDEX IF NOT EXISTS ix_analytics_merchant_date ON analytics_snapshots(merchant_id, date);

-- Audit logs indexes
CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_logs(actor_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs(action, timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_resource ON audit_logs(resource_type, resource_id);
CREATE INDEX IF NOT EXISTS idx_audit_ip ON audit_logs(ip_address, timestamp);

-- Activity logs indexes
CREATE INDEX IF NOT EXISTS idx_activity_merchant_member ON activity_logs(merchant_id, team_member_id);
CREATE INDEX IF NOT EXISTS idx_activity_action_created ON activity_logs(action, created_at);

-- Team member sessions indexes
CREATE INDEX IF NOT EXISTS idx_session_member_active ON team_member_sessions(team_member_id, revoked_at);

-- Promo codes indexes
CREATE INDEX IF NOT EXISTS idx_promo_codes_merchant_id ON promo_codes(merchant_id);
CREATE INDEX IF NOT EXISTS idx_promo_codes_code ON promo_codes(code);
CREATE INDEX IF NOT EXISTS idx_promo_codes_status ON promo_codes(status);

-- Promo code usage indexes
CREATE INDEX IF NOT EXISTS idx_promo_usage_code_id ON promo_code_usage(promo_code_id);
CREATE INDEX IF NOT EXISTS idx_promo_usage_merchant ON promo_code_usage(merchant_id);

-- Web3 subscription indexes
CREATE INDEX IF NOT EXISTS idx_web3_subs_merchant ON web3_subscriptions(merchant_id);
CREATE INDEX IF NOT EXISTS idx_web3_subs_subscriber ON web3_subscriptions(subscriber_address);
CREATE INDEX IF NOT EXISTS idx_web3_subs_status ON web3_subscriptions(status);
CREATE INDEX IF NOT EXISTS idx_web3_subs_next_payment ON web3_subscriptions(next_payment_at);

-- Subscription mandate indexes
CREATE INDEX IF NOT EXISTS idx_mandates_subscriber ON subscription_mandates(subscriber_address);
CREATE INDEX IF NOT EXISTS idx_mandates_merchant ON subscription_mandates(merchant_id);
CREATE INDEX IF NOT EXISTS idx_mandates_status ON subscription_mandates(status);

-- Ledger indexes
CREATE INDEX IF NOT EXISTS ix_ledger_merchant ON ledger_entries(merchant_id);
CREATE INDEX IF NOT EXISTS ix_ledger_session ON ledger_entries(session_id);
CREATE INDEX IF NOT EXISTS ix_ledger_type ON ledger_entries(entry_type);
CREATE INDEX IF NOT EXISTS ix_ledger_created ON ledger_entries(created_at);

-- Compliance screening indexes
CREATE INDEX IF NOT EXISTS ix_compliance_session ON compliance_screenings(session_id);
CREATE INDEX IF NOT EXISTS ix_compliance_result ON compliance_screenings(result);
CREATE INDEX IF NOT EXISTS ix_compliance_created ON compliance_screenings(created_at);

-- Payment state transitions indexes
CREATE INDEX IF NOT EXISTS ix_transitions_session ON payment_state_transitions(session_id);
CREATE INDEX IF NOT EXISTS ix_transitions_created ON payment_state_transitions(created_at);

-- ============================================================================
-- 11. UPDATE EXISTING DATA (if needed)
-- ============================================================================

-- Set default values for existing rows in merchant_subscriptions
UPDATE merchant_subscriptions 
SET 
    current_volume = COALESCE(current_volume, 0),
    current_payment_links = COALESCE(current_payment_links, 0),
    current_invoices = COALESCE(current_invoices, 0),
    created_at = COALESCE(created_at, CURRENT_TIMESTAMP)
WHERE current_volume IS NULL 
   OR current_payment_links IS NULL 
   OR current_invoices IS NULL
   OR created_at IS NULL;

COMMIT;

-- ============================================================================
-- MIGRATION COMPLETE
-- ============================================================================

-- Verify critical tables
SELECT 'merchants' as table_name, COUNT(*) as row_count FROM merchants
UNION ALL
SELECT 'merchant_subscriptions', COUNT(*) FROM merchant_subscriptions
UNION ALL
SELECT 'payment_sessions', COUNT(*) FROM payment_sessions
UNION ALL
SELECT 'refunds', COUNT(*) FROM refunds;

-- Show any merchants without subscriptions (should be 0 after trigger fix)
SELECT COUNT(*) as merchants_without_subscription
FROM merchants m
LEFT JOIN merchant_subscriptions ms ON m.id = ms.merchant_id
WHERE ms.id IS NULL;
