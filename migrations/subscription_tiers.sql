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
