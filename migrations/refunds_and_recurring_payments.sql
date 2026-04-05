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
