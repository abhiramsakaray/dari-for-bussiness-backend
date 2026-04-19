-- Migration: Add encrypted PII columns to payer_info for GDPR compliance
-- Date: 2026-04-19
-- These columns store Fernet-encrypted versions of email, name, phone

ALTER TABLE payer_info ADD COLUMN IF NOT EXISTS email_encrypted BYTEA;
ALTER TABLE payer_info ADD COLUMN IF NOT EXISTS name_encrypted BYTEA;
ALTER TABLE payer_info ADD COLUMN IF NOT EXISTS phone_encrypted BYTEA;
