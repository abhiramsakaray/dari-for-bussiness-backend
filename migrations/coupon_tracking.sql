-- Add coupon tracking fields to payment_sessions table
-- Run after: promo_codes.sql

ALTER TABLE payment_sessions
    ADD COLUMN IF NOT EXISTS coupon_code VARCHAR(50),
    ADD COLUMN IF NOT EXISTS discount_amount NUMERIC(14, 2);

CREATE INDEX IF NOT EXISTS idx_payment_sessions_coupon ON payment_sessions(coupon_code)
    WHERE coupon_code IS NOT NULL;
