-- Migration: Add payment_started_at to payment_sessions
-- Description: Add payment_started_at column to track when user starts payment
-- Version: 2026-04-09

BEGIN;

-- Add payment_started_at column
ALTER TABLE payment_sessions
ADD COLUMN payment_started_at TIMESTAMP NULL;

-- Add comment for clarity
COMMENT ON COLUMN payment_sessions.payment_started_at IS 'Timestamp when user starts payment (opens checkout page or initiates payment). Used for 15-minute timeout calculation.';

-- Create index for expiration queries
CREATE INDEX IF NOT EXISTS idx_payment_sessions_payment_started_at 
ON payment_sessions(payment_started_at);

COMMIT;
