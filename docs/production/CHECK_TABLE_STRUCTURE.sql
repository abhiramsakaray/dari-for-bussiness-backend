-- Check actual table structures
SELECT 'merchant_subscriptions columns:' as info;
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'merchant_subscriptions'
ORDER BY ordinal_position;

SELECT 'withdrawal_limits columns:' as info;
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'withdrawal_limits'
ORDER BY ordinal_position;
