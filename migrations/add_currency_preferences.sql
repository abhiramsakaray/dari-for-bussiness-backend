-- Migration: Add Currency Preference Fields to Merchants Table
-- Description: Adds currency_preference, currency_locale, and currency_decimal_places
--              fields to support backend-driven currency handling with proper formatting.
-- Date: 2026-04-12

-- Add new currency preference columns
ALTER TABLE merchants 
ADD COLUMN IF NOT EXISTS currency_preference VARCHAR(10) DEFAULT 'USD' NOT NULL,
ADD COLUMN IF NOT EXISTS currency_locale VARCHAR(10) DEFAULT 'en_US' NOT NULL,
ADD COLUMN IF NOT EXISTS currency_decimal_places INTEGER DEFAULT 2 NOT NULL;

-- Create index on currency_preference for faster lookups
CREATE INDEX IF NOT EXISTS idx_merchants_currency_preference 
ON merchants(currency_preference);

-- Update existing merchants to use their base_currency as currency_preference
UPDATE merchants 
SET currency_preference = COALESCE(base_currency, 'USD')
WHERE currency_preference = 'USD';

-- Set locale based on country (best effort mapping)
UPDATE merchants
SET currency_locale = CASE
    WHEN country = 'United States' OR country = 'US' THEN 'en_US'
    WHEN country = 'United Kingdom' OR country = 'UK' THEN 'en_GB'
    WHEN country = 'India' THEN 'en_IN'
    WHEN country = 'Germany' THEN 'de_DE'
    WHEN country = 'France' THEN 'fr_FR'
    WHEN country = 'Spain' THEN 'es_ES'
    WHEN country = 'Italy' THEN 'it_IT'
    WHEN country = 'Japan' THEN 'ja_JP'
    WHEN country = 'China' THEN 'zh_CN'
    WHEN country = 'Brazil' THEN 'pt_BR'
    WHEN country = 'Canada' THEN 'en_CA'
    WHEN country = 'Australia' THEN 'en_AU'
    ELSE 'en_US'
END
WHERE currency_locale = 'en_US';

-- Set decimal places based on currency
UPDATE merchants
SET currency_decimal_places = CASE
    WHEN currency_preference IN ('JPY', 'KRW', 'VND', 'CLP') THEN 0  -- No decimal places
    WHEN currency_preference IN ('BTC', 'ETH') THEN 8  -- Crypto currencies
    ELSE 2  -- Standard fiat currencies
END;

-- Add comment to table
COMMENT ON COLUMN merchants.currency_preference IS 'ISO 4217 currency code for merchant''s preferred currency';
COMMENT ON COLUMN merchants.currency_locale IS 'Locale string for currency formatting (e.g., en_US, en_IN, de_DE)';
COMMENT ON COLUMN merchants.currency_decimal_places IS 'Number of decimal places for currency formatting';

-- Rollback script (commented out, uncomment to rollback)
-- DROP INDEX IF EXISTS idx_merchants_currency_preference;
-- ALTER TABLE merchants DROP COLUMN IF EXISTS currency_preference;
-- ALTER TABLE merchants DROP COLUMN IF EXISTS currency_locale;
-- ALTER TABLE merchants DROP COLUMN IF EXISTS currency_decimal_places;
