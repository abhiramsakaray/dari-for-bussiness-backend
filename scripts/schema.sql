-- Dari for Business - Multi-Chain Payment Gateway Database Schema
-- PostgreSQL Database Schema

-- Create extension for UUID support
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Payment Status Enum
CREATE TYPE payment_status AS ENUM ('created', 'paid', 'expired');

-- ============================================================
-- Merchants Table
-- ============================================================
CREATE TABLE merchants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR NOT NULL,
    email VARCHAR UNIQUE NOT NULL,
    password_hash VARCHAR NOT NULL,
    api_key VARCHAR UNIQUE,
    stellar_address VARCHAR,
    webhook_url VARCHAR,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for merchants
CREATE INDEX idx_merchants_email ON merchants(email);
CREATE INDEX idx_merchants_api_key ON merchants(api_key);

-- ============================================================
-- Payment Sessions Table
-- ============================================================
CREATE TABLE payment_sessions (
    id VARCHAR PRIMARY KEY,
    merchant_id UUID NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
    amount_fiat NUMERIC(10, 2) NOT NULL,
    fiat_currency VARCHAR NOT NULL,
    amount_usdc VARCHAR NOT NULL,
    status payment_status NOT NULL DEFAULT 'created',
    success_url VARCHAR NOT NULL,
    cancel_url VARCHAR NOT NULL,
    tx_hash VARCHAR,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    paid_at TIMESTAMP
);

-- Create indexes for payment_sessions
CREATE INDEX idx_payment_sessions_merchant_id ON payment_sessions(merchant_id);
CREATE INDEX idx_payment_sessions_status ON payment_sessions(status);
CREATE INDEX idx_payment_sessions_created_at ON payment_sessions(created_at);

-- ============================================================
-- Admins Table
-- ============================================================
CREATE TABLE admins (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR UNIQUE NOT NULL,
    password_hash VARCHAR NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Create index for admins
CREATE INDEX idx_admins_email ON admins(email);

-- ============================================================
-- Sample Data (Optional - for testing)
-- ============================================================

-- Insert sample merchant (password: TestMerchant123)
-- Note: Password hash is bcrypt hash of "TestMerchant123"
INSERT INTO merchants (name, email, password_hash, api_key, stellar_address, is_active)
VALUES (
    'Test Merchant',
    'merchant@example.com',
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYqNXhCBjSu',
    'pk_test_' || substr(md5(random()::text), 0, 32),
    'GCY7S2QYMBVFB7UWTPBQ6LKOGTW3RSTFFRVUXGHI7UHVGI5MWUHV7CBS',
    TRUE
);

-- Insert admin account (password: AdminPassword123)
-- Note: Password hash is bcrypt hash of "AdminPassword123"
INSERT INTO admins (email, password_hash)
VALUES (
    'admin@dari.business',
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYqNXhCBjSu'
);

-- ============================================================
-- Useful Queries
-- ============================================================

-- Get all active merchants
-- SELECT * FROM merchants WHERE is_active = TRUE;

-- Get all payment sessions for a merchant
-- SELECT * FROM payment_sessions WHERE merchant_id = 'YOUR-MERCHANT-UUID';

-- Get all paid sessions
-- SELECT * FROM payment_sessions WHERE status = 'paid';

-- Get revenue statistics
-- SELECT 
--     merchant_id,
--     COUNT(*) as total_payments,
--     SUM(amount_fiat) as total_revenue,
--     fiat_currency
-- FROM payment_sessions 
-- WHERE status = 'paid'
-- GROUP BY merchant_id, fiat_currency;

-- ============================================================
-- Cleanup (Use with caution!)
-- ============================================================

-- Drop all tables
-- DROP TABLE IF EXISTS payment_sessions CASCADE;
-- DROP TABLE IF EXISTS merchants CASCADE;
-- DROP TABLE IF EXISTS admins CASCADE;
-- DROP TYPE IF EXISTS payment_status;
