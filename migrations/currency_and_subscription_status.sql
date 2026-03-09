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
-- UPDATE merchants SET base_currency = 'INR', currency_symbol = '₹', currency_name = 'Indian Rupee' WHERE country = 'India';
-- UPDATE merchants SET base_currency = 'EUR', currency_symbol = '€', currency_name = 'Euro' WHERE country IN ('Germany', 'France', 'Italy', 'Spain', 'Netherlands');
-- etc.

-- 4. Index for faster currency-based queries (optional)
CREATE INDEX IF NOT EXISTS idx_merchants_base_currency ON merchants(base_currency);
