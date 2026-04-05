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
