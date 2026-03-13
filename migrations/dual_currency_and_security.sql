-- Migration: Dual Currency, Tokenization, Cross-border, and Risk Scoring
-- Adds fields for payer/merchant dual currency tracking, cross-border detection,
-- auto-tokenization, and fraud risk scoring to payment_sessions.

-- ── Tokenization ──
ALTER TABLE payment_sessions
    ADD COLUMN IF NOT EXISTS is_tokenized BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS token_created_at TIMESTAMP;

-- ── Dual Currency: Payer ──
ALTER TABLE payment_sessions
    ADD COLUMN IF NOT EXISTS payer_currency VARCHAR(10),
    ADD COLUMN IF NOT EXISTS payer_currency_symbol VARCHAR(10),
    ADD COLUMN IF NOT EXISTS payer_amount_local NUMERIC(14, 2),
    ADD COLUMN IF NOT EXISTS payer_exchange_rate NUMERIC(18, 8);

-- ── Dual Currency: Merchant ──
ALTER TABLE payment_sessions
    ADD COLUMN IF NOT EXISTS merchant_currency VARCHAR(10),
    ADD COLUMN IF NOT EXISTS merchant_currency_symbol VARCHAR(10),
    ADD COLUMN IF NOT EXISTS merchant_amount_local NUMERIC(14, 2),
    ADD COLUMN IF NOT EXISTS merchant_exchange_rate NUMERIC(18, 8);

-- ── Cross-border / Compliance ──
ALTER TABLE payment_sessions
    ADD COLUMN IF NOT EXISTS is_cross_border BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS payer_country VARCHAR(100),
    ADD COLUMN IF NOT EXISTS risk_score NUMERIC(5, 2),
    ADD COLUMN IF NOT EXISTS risk_flags JSONB;

-- ── Indexes for common queries ──
CREATE INDEX IF NOT EXISTS idx_payment_sessions_payer_currency
    ON payment_sessions (payer_currency);
CREATE INDEX IF NOT EXISTS idx_payment_sessions_merchant_currency
    ON payment_sessions (merchant_currency);
CREATE INDEX IF NOT EXISTS idx_payment_sessions_is_cross_border
    ON payment_sessions (is_cross_border) WHERE is_cross_border = TRUE;
CREATE INDEX IF NOT EXISTS idx_payment_sessions_risk_score
    ON payment_sessions (risk_score) WHERE risk_score IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_payment_sessions_is_tokenized
    ON payment_sessions (is_tokenized) WHERE is_tokenized = TRUE;
