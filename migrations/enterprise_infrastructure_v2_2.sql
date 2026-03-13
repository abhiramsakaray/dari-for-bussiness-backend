-- ============================================================
-- Migration: v2.2.0 Enterprise Infrastructure Upgrade
-- ============================================================
-- Adds:
--   1. PROCESSING / CONFIRMED status to payment_sessions
--   2. ledger_entries table (immutable double-entry ledger)
--   3. payment_state_transitions table (state machine audit)
--   4. compliance_screenings table (AML/OFAC audit)
--   5. Indexes for new tables
-- ============================================================

-- 1. Payment status: add PROCESSING and CONFIRMED values ----
-- PostgreSQL enums need ALTER TYPE; SQLite ignores this.
DO $$
BEGIN
    -- Add 'processing' if not exists
    IF NOT EXISTS (
        SELECT 1 FROM pg_enum
        WHERE enumlabel = 'processing'
          AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'paymentstatus')
    ) THEN
        ALTER TYPE paymentstatus ADD VALUE 'processing';
    END IF;

    -- Add 'confirmed' if not exists
    IF NOT EXISTS (
        SELECT 1 FROM pg_enum
        WHERE enumlabel = 'confirmed'
          AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'paymentstatus')
    ) THEN
        ALTER TYPE paymentstatus ADD VALUE 'confirmed';
    END IF;
END $$;


-- 2. Ledger Entries -----------------------------------------
CREATE TABLE IF NOT EXISTS ledger_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id UUID NOT NULL REFERENCES merchants(id),
    session_id VARCHAR REFERENCES payment_sessions(id),

    entry_type VARCHAR(30) NOT NULL,  -- debit, credit, conversion, settlement, fee, refund_debit, refund_credit
    amount NUMERIC(20, 8) NOT NULL,
    currency VARCHAR(10) NOT NULL,
    direction VARCHAR(6) NOT NULL,    -- debit or credit

    counter_amount NUMERIC(20, 8),
    counter_currency VARCHAR(10),
    exchange_rate NUMERIC(18, 8),

    reference_type VARCHAR(50),
    reference_id VARCHAR,
    description VARCHAR(500),

    balance_after NUMERIC(20, 8),

    entry_hash VARCHAR(64) NOT NULL,
    prev_hash VARCHAR(64),

    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_ledger_merchant ON ledger_entries(merchant_id);
CREATE INDEX IF NOT EXISTS ix_ledger_session ON ledger_entries(session_id);
CREATE INDEX IF NOT EXISTS ix_ledger_type ON ledger_entries(entry_type);
CREATE INDEX IF NOT EXISTS ix_ledger_created ON ledger_entries(created_at);


-- 3. Payment State Transitions ------------------------------
CREATE TABLE IF NOT EXISTS payment_state_transitions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id VARCHAR NOT NULL REFERENCES payment_sessions(id),
    from_state VARCHAR(30) NOT NULL,
    to_state VARCHAR(30) NOT NULL,
    trigger VARCHAR(100),
    actor VARCHAR(200),
    metadata JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_transitions_session ON payment_state_transitions(session_id);
CREATE INDEX IF NOT EXISTS ix_transitions_created ON payment_state_transitions(created_at);


-- 4. Compliance Screenings ----------------------------------
CREATE TABLE IF NOT EXISTS compliance_screenings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id VARCHAR REFERENCES payment_sessions(id),
    merchant_id UUID REFERENCES merchants(id),

    screening_type VARCHAR(50) NOT NULL,  -- ofac, jurisdiction, threshold, velocity
    result VARCHAR(20) NOT NULL,          -- pass, flag, block
    risk_level VARCHAR(20),               -- low, medium, high, critical

    entity_type VARCHAR(50),
    entity_value VARCHAR(255),
    country VARCHAR(100),

    details JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_compliance_session ON compliance_screenings(session_id);
CREATE INDEX IF NOT EXISTS ix_compliance_result ON compliance_screenings(result);
CREATE INDEX IF NOT EXISTS ix_compliance_created ON compliance_screenings(created_at);


-- 5. Add ledger entry type enum (for strict PG type safety) --
-- Not strictly required since we use VARCHAR, but good practice.
-- DO $$
-- BEGIN
--     CREATE TYPE ledger_entry_type AS ENUM (
--         'debit', 'credit', 'conversion', 'settlement', 'fee', 'refund_debit', 'refund_credit'
--     );
-- EXCEPTION
--     WHEN duplicate_object THEN NULL;
-- END $$;
