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
