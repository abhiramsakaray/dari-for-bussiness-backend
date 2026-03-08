-- Migration: Add payer data collection & payment tokenization support
-- Date: 2026-03-08

-- 1. Add new columns to payment_sessions
ALTER TABLE payment_sessions ADD COLUMN IF NOT EXISTS collect_payer_data BOOLEAN DEFAULT FALSE;
ALTER TABLE payment_sessions ADD COLUMN IF NOT EXISTS payer_email VARCHAR(255);
ALTER TABLE payment_sessions ADD COLUMN IF NOT EXISTS payer_name VARCHAR(255);
ALTER TABLE payment_sessions ADD COLUMN IF NOT EXISTS payment_token VARCHAR(100);

-- Index for token lookups
CREATE INDEX IF NOT EXISTS ix_payment_sessions_payment_token ON payment_sessions(payment_token);

-- 2. Create payer_info table
CREATE TABLE IF NOT EXISTS payer_info (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id VARCHAR NOT NULL REFERENCES payment_sessions(id),
    merchant_id UUID NOT NULL REFERENCES merchants(id),

    -- Contact
    email VARCHAR(255),
    name VARCHAR(255),
    phone VARCHAR(50),

    -- Billing address
    billing_address_line1 VARCHAR(255),
    billing_address_line2 VARCHAR(255),
    billing_city VARCHAR(100),
    billing_state VARCHAR(100),
    billing_postal_code VARCHAR(20),
    billing_country VARCHAR(100),

    -- Shipping address
    shipping_address_line1 VARCHAR(255),
    shipping_city VARCHAR(100),
    shipping_state VARCHAR(100),
    shipping_postal_code VARCHAR(20),
    shipping_country VARCHAR(100),

    -- Metadata
    custom_fields JSON,

    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_payer_info_session_id ON payer_info(session_id);
CREATE INDEX IF NOT EXISTS ix_payer_info_merchant_id ON payer_info(merchant_id);
