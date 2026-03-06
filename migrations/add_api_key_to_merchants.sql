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
