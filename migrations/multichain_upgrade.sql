-- Migration: Multi-chain upgrade for Dari for Business
-- Description: Adds support for multi-chain stablecoin payments (USDC, USDT, PYUSD)
-- across Stellar, Ethereum, Polygon, Base, Tron, and Solana
-- Date: 2025-01-XX

-- =============================================================================
-- 1. CREATE NEW TABLES
-- =============================================================================

-- Supported tokens registry
CREATE TABLE IF NOT EXISTS tokens (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    name VARCHAR(50) NOT NULL,
    chain VARCHAR(20) NOT NULL,
    contract_address VARCHAR(100),
    decimals INTEGER DEFAULT 6,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, chain)
);

-- Merchant wallets per chain
CREATE TABLE IF NOT EXISTS merchant_wallets (
    id SERIAL PRIMARY KEY,
    merchant_id INTEGER NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
    chain VARCHAR(20) NOT NULL,
    wallet_address VARCHAR(100) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    is_verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(merchant_id, chain)
);

-- Payment events for audit trail
CREATE TABLE IF NOT EXISTS payment_events (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(50) NOT NULL REFERENCES payment_sessions(id) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL,
    data JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- 2. UPDATE PAYMENT_SESSIONS TABLE
-- =============================================================================

-- Add new columns for multi-chain support
ALTER TABLE payment_sessions ADD COLUMN IF NOT EXISTS token VARCHAR(10);
ALTER TABLE payment_sessions ADD COLUMN IF NOT EXISTS chain VARCHAR(20);
ALTER TABLE payment_sessions ADD COLUMN IF NOT EXISTS amount_token DECIMAL(20, 8);
ALTER TABLE payment_sessions ADD COLUMN IF NOT EXISTS accepted_tokens TEXT;
ALTER TABLE payment_sessions ADD COLUMN IF NOT EXISTS accepted_chains TEXT;
ALTER TABLE payment_sessions ADD COLUMN IF NOT EXISTS merchant_wallet VARCHAR(100);
ALTER TABLE payment_sessions ADD COLUMN IF NOT EXISTS deposit_address VARCHAR(100);
ALTER TABLE payment_sessions ADD COLUMN IF NOT EXISTS block_number BIGINT;
ALTER TABLE payment_sessions ADD COLUMN IF NOT EXISTS confirmations INTEGER DEFAULT 0;

-- =============================================================================
-- 3. POPULATE DEFAULT TOKENS
-- =============================================================================

INSERT INTO tokens (symbol, name, chain, contract_address, decimals) VALUES
-- Stellar
('USDC', 'USD Coin', 'stellar', 'GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN', 7),

-- Ethereum
('USDC', 'USD Coin', 'ethereum', '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48', 6),
('USDT', 'Tether USD', 'ethereum', '0xdAC17F958D2ee523a2206206994597C13D831ec7', 6),
('PYUSD', 'PayPal USD', 'ethereum', '0x6c3ea9036406852006290770BEdFcAbA0e23A0e8', 6),

-- Polygon
('USDC', 'USD Coin', 'polygon', '0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359', 6),
('USDT', 'Tether USD', 'polygon', '0xc2132D05D31c914a87C6611C10748AEb04B58e8F', 6),

-- Base
('USDC', 'USD Coin', 'base', '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913', 6),

-- Tron
('USDT', 'Tether USD', 'tron', 'TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t', 6),
('USDC', 'USD Coin', 'tron', 'TEkxiTehnzSmSe2XqrBj4w32RUN966rdz8', 6)

ON CONFLICT (symbol, chain) DO NOTHING;

-- =============================================================================
-- 4. CREATE INDEXES
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_merchant_wallets_merchant_id ON merchant_wallets(merchant_id);
CREATE INDEX IF NOT EXISTS idx_merchant_wallets_chain ON merchant_wallets(chain);
CREATE INDEX IF NOT EXISTS idx_payment_events_session_id ON payment_events(session_id);
CREATE INDEX IF NOT EXISTS idx_payment_sessions_chain ON payment_sessions(chain);
CREATE INDEX IF NOT EXISTS idx_payment_sessions_token ON payment_sessions(token);
CREATE INDEX IF NOT EXISTS idx_tokens_chain ON tokens(chain);
CREATE INDEX IF NOT EXISTS idx_tokens_symbol ON tokens(symbol);

-- =============================================================================
-- 5. UPDATE FUNCTION FOR TIMESTAMP
-- =============================================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply trigger to merchant_wallets
DROP TRIGGER IF EXISTS update_merchant_wallets_updated_at ON merchant_wallets;
CREATE TRIGGER update_merchant_wallets_updated_at
    BEFORE UPDATE ON merchant_wallets
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- 6. MIGRATION NOTES
-- =============================================================================

-- After running this migration:
-- 1. Existing payment sessions retain backward compatibility via amount_usdc field
-- 2. New sessions should use token, chain, and amount_token fields
-- 3. Merchants need to add wallets for each chain they want to accept payments on
-- 4. The tokens table can be extended with additional tokens as needed

-- To rollback (if needed):
-- DROP TABLE IF EXISTS payment_events;
-- DROP TABLE IF EXISTS merchant_wallets;
-- DROP TABLE IF EXISTS tokens;
-- ALTER TABLE payment_sessions DROP COLUMN IF EXISTS token;
-- ALTER TABLE payment_sessions DROP COLUMN IF EXISTS chain;
-- ALTER TABLE payment_sessions DROP COLUMN IF EXISTS amount_token;
-- ALTER TABLE payment_sessions DROP COLUMN IF EXISTS accepted_tokens;
-- ALTER TABLE payment_sessions DROP COLUMN IF EXISTS accepted_chains;
-- ALTER TABLE payment_sessions DROP COLUMN IF EXISTS merchant_wallet;
-- ALTER TABLE payment_sessions DROP COLUMN IF EXISTS deposit_address;
-- ALTER TABLE payment_sessions DROP COLUMN IF EXISTS block_number;
-- ALTER TABLE payment_sessions DROP COLUMN IF EXISTS confirmations;
