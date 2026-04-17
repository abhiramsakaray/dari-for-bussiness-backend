-- ============================================================
-- FINAL DATABASE FIXES
-- Run this to complete the database setup
-- ============================================================

-- 1. Stellar enum already added ✅

-- 2. Fix DEFAULT values for ID columns
ALTER TABLE merchant_subscriptions 
ALTER COLUMN id SET DEFAULT gen_random_uuid();

ALTER TABLE withdrawal_limits 
ALTER COLUMN id SET DEFAULT gen_random_uuid();

-- 3. Check what columns exist and show results
\echo '✅ Checking database status...'

SELECT 'Blockchain networks available:' as info;
SELECT enumlabel as network 
FROM pg_enum 
WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname = 'blockchainnetwork')
ORDER BY enumlabel;

SELECT 'Merchants count:' as info;
SELECT COUNT(*) as total_merchants FROM merchants;

SELECT 'Payment sessions count:' as info;
SELECT COUNT(*) as total_sessions FROM payment_sessions;

SELECT 'Subscriptions count:' as info;
SELECT COUNT(*) as total_subscriptions FROM subscriptions;

\echo '✅ Database is ready!'
\echo ''
\echo 'Next steps:'
\echo '1. Restart your backend: sudo systemctl restart dari-api'
\echo '2. Check logs: sudo journalctl -u dari-api -f'
\echo '3. Test API: curl http://localhost:8000/docs'
