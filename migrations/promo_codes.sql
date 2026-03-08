-- Promo Code / Coupon Management System
-- Migration: Add promo_codes and promo_code_usage tables

-- Promo Codes table
CREATE TABLE IF NOT EXISTS promo_codes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id UUID NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
    code VARCHAR(50) NOT NULL,
    type VARCHAR(20) NOT NULL CHECK (type IN ('percentage', 'fixed')),
    discount_value NUMERIC(14, 2) NOT NULL,
    max_discount_amount NUMERIC(14, 2),
    min_order_amount NUMERIC(14, 2) DEFAULT 0,
    usage_limit_total INTEGER,
    usage_limit_per_user INTEGER,
    used_count INTEGER NOT NULL DEFAULT 0,
    start_date TIMESTAMP NOT NULL,
    expiry_date TIMESTAMP NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'deleted')),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_promo_merchant_code UNIQUE (merchant_id, code)
);

CREATE INDEX IF NOT EXISTS idx_promo_codes_merchant_id ON promo_codes(merchant_id);
CREATE INDEX IF NOT EXISTS idx_promo_codes_code ON promo_codes(code);
CREATE INDEX IF NOT EXISTS idx_promo_codes_status ON promo_codes(status);

-- Promo Code Usage tracking table
CREATE TABLE IF NOT EXISTS promo_code_usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    promo_code_id UUID NOT NULL REFERENCES promo_codes(id) ON DELETE CASCADE,
    merchant_id UUID NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
    customer_id VARCHAR(255) NOT NULL,
    payment_id VARCHAR(255),
    discount_applied NUMERIC(14, 2) NOT NULL,
    used_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_promo_usage_code_id ON promo_code_usage(promo_code_id);
CREATE INDEX IF NOT EXISTS idx_promo_usage_customer ON promo_code_usage(promo_code_id, customer_id);
CREATE INDEX IF NOT EXISTS idx_promo_usage_merchant ON promo_code_usage(merchant_id);
