-- Add missing subscription status labels used by application code.
-- Safe to run multiple times.
ALTER TYPE subscription_status ADD VALUE IF NOT EXISTS 'PENDING_PAYMENT';
ALTER TYPE subscription_status ADD VALUE IF NOT EXISTS 'PENDING_PAYMENT';
