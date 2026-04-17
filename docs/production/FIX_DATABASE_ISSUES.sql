-- ============================================================
-- CRITICAL DATABASE FIXES
-- Fixes the 3 issues from migration
-- ============================================================

-- 1. Add 'stellar' to blockchainnetwork enum
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_enum 
        WHERE enumlabel = 'stellar' 
        AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'blockchainnetwork')
    ) THEN
        ALTER TYPE blockchainnetwork ADD VALUE 'stellar';
        RAISE NOTICE '✅ Added stellar to blockchainnetwork enum';
    ELSE
        RAISE NOTICE 'ℹ️  stellar already exists in blockchainnetwork enum';
    END IF;
END $$;

-- 2. Fix merchant_subscriptions table - add DEFAULT for id
ALTER TABLE merchant_subscriptions 
ALTER COLUMN id SET DEFAULT gen_random_uuid();

-- 3. Fix withdrawal_limits table - add DEFAULT for id
ALTER TABLE withdrawal_limits 
ALTER COLUMN id SET DEFAULT gen_random_uuid();

-- 4. Insert missing data with proper UUIDs
INSERT INTO merchant_subscriptions (
    id,
    merchant_id,
    tier,
    status,
    transaction_fee_percent,
    monthly_fee,
    monthly_transaction_limit,
    api_rate_limit_per_minute,
    max_team_members,
    max_api_keys,
    started_at
)
SELECT 
    gen_random_uuid(),
    id,
    'free',
    'active',
    0.00,
    1.50,
    1000.00,
    2,
    5,
    1,
    NOW()
FROM merchants
WHERE id NOT IN (SELECT merchant_id FROM merchant_subscriptions)
ON CONFLICT (merchant_id) DO NOTHING;

-- 5. Insert withdrawal limits for free tier
INSERT INTO withdrawal_limits (
    id,
    tier,
    daily_limit_usdc,
    min_withdrawal_usdc,
    max_withdrawal_usdc,
    fee_percent,
    fee_fixed_usdc,
    processing_time_hours,
    requires_kyc
) VALUES (
    gen_random_uuid(),
    'free',
    100.00000000,
    5.00000000,
    50.00000000,
    1.00,
    1.00,
    60,
    false
)
ON CONFLICT (tier) DO NOTHING;

-- 6. Verify fixes
SELECT 'merchant_subscriptions' as table_name, COUNT(*) as count FROM merchant_subscriptions
UNION ALL
SELECT 'withdrawal_limits', COUNT(*) FROM withdrawal_limits;

-- 7. Check enum values
SELECT enumlabel as blockchain_network 
FROM pg_enum 
WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname = 'blockchainnetwork')
ORDER BY enumlabel;

RAISE NOTICE '✅ All fixes applied successfully!';
