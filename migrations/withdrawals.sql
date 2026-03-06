-- Withdrawal Feature Migration
-- Supports withdrawals to external wallets across all blockchain networks

-- ============================================================
-- Withdrawals Table
-- ============================================================
CREATE TABLE IF NOT EXISTS withdrawals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    merchant_id UUID NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
    
    -- Amount
    amount NUMERIC(20, 8) NOT NULL,
    token VARCHAR(10) NOT NULL,           -- USDC, USDT, PYUSD
    chain VARCHAR(20) NOT NULL,           -- stellar, ethereum, polygon, base, tron
    
    -- Destination
    destination_address VARCHAR(200) NOT NULL,
    destination_memo VARCHAR(100),         -- For Stellar memo field
    
    -- Status tracking
    status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending, processing, completed, failed, cancelled
    
    -- Transaction details
    tx_hash VARCHAR(200),                  -- Blockchain transaction hash
    network_fee NUMERIC(20, 8),            -- Estimated/actual network fee
    platform_fee NUMERIC(20, 8) DEFAULT 0, -- Platform withdrawal fee
    
    -- Processing details
    submitted_at TIMESTAMP,                -- When sent to blockchain
    confirmed_at TIMESTAMP,                -- When confirmed on chain
    failed_reason VARCHAR(500),            -- Reason for failure
    
    -- Metadata
    notes VARCHAR(500),                    -- Merchant notes
    ip_address VARCHAR(45),                -- Request IP for security
    
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_withdrawals_merchant_id ON withdrawals(merchant_id);
CREATE INDEX IF NOT EXISTS idx_withdrawals_status ON withdrawals(status);
CREATE INDEX IF NOT EXISTS idx_withdrawals_chain ON withdrawals(chain);
CREATE INDEX IF NOT EXISTS idx_withdrawals_created_at ON withdrawals(created_at);
CREATE INDEX IF NOT EXISTS idx_withdrawals_tx_hash ON withdrawals(tx_hash);

-- Add balance tracking to merchants
ALTER TABLE merchants ADD COLUMN IF NOT EXISTS balance_usdc NUMERIC(20, 8) DEFAULT 0;
ALTER TABLE merchants ADD COLUMN IF NOT EXISTS balance_usdt NUMERIC(20, 8) DEFAULT 0;
ALTER TABLE merchants ADD COLUMN IF NOT EXISTS balance_pyusd NUMERIC(20, 8) DEFAULT 0;

-- Withdrawal limits table (per subscription tier)
CREATE TABLE IF NOT EXISTS withdrawal_limits (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tier VARCHAR(20) NOT NULL UNIQUE,          -- free, growth, business, enterprise
    daily_limit NUMERIC(20, 8) NOT NULL,       -- Max daily withdrawal
    min_withdrawal NUMERIC(20, 8) NOT NULL,    -- Minimum withdrawal amount
    max_per_transaction NUMERIC(20, 8) NOT NULL, -- Max per single withdrawal
    withdrawal_fee_percent NUMERIC(5, 2) DEFAULT 0, -- Fee percentage
    withdrawal_fee_flat NUMERIC(10, 2) DEFAULT 0,   -- Flat fee in USD
    cooldown_minutes INTEGER DEFAULT 0,             -- Minutes between withdrawals
    requires_2fa BOOLEAN DEFAULT FALSE
);

-- Insert default limits per tier
INSERT INTO withdrawal_limits (tier, daily_limit, min_withdrawal, max_per_transaction, withdrawal_fee_percent, withdrawal_fee_flat, cooldown_minutes, requires_2fa)
VALUES 
    ('free', 100, 5, 50, 1.0, 1.00, 60, FALSE),
    ('growth', 5000, 5, 2500, 0.5, 0.50, 15, FALSE),
    ('business', 25000, 1, 10000, 0.25, 0.00, 5, TRUE),
    ('enterprise', 100000, 1, 50000, 0.10, 0.00, 0, TRUE)
ON CONFLICT (tier) DO UPDATE 
SET daily_limit = EXCLUDED.daily_limit,
    min_withdrawal = EXCLUDED.min_withdrawal,
    max_per_transaction = EXCLUDED.max_per_transaction,
    withdrawal_fee_percent = EXCLUDED.withdrawal_fee_percent,
    withdrawal_fee_flat = EXCLUDED.withdrawal_fee_flat,
    cooldown_minutes = EXCLUDED.cooldown_minutes,
    requires_2fa = EXCLUDED.requires_2fa;
