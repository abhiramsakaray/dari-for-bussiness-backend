-- ============================================================
-- DARI FOR BUSINESS - COMPLETE DATABASE SCHEMA
-- Multi-Chain Payment Gateway - Full Database Setup
-- Version: 2.2.0
-- Date: April 17, 2026
-- ============================================================
-- This file contains ALL migrations combined in the correct order
-- Run this file on a fresh PostgreSQL database to set up everything
-- ============================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================
-- ENUMS
-- ============================================================

-- Payment Status
CREATE TYPE paymentstatus AS ENUM (
    'CREATED',
    'PENDING',
    'PROCESSING',
    'CONFIRMED',
    'PAID',
    'EXPIRED',
    'FAILED',
    'REFUNDED',
    'PARTIALLY_REFUNDED'
);

-- Blockchain Networks
CREATE TYPE blockchainnetwork AS ENUM (
    'stellar',
    'ethereum',
    'polygon',
    'base',
    'bsc',
    'arbitrum',
    'avalanche',
    'tron',
    'solana',
    'soroban'
);

-- Token Symbols
CREATE TYPE tokensymbol AS ENUM ('USDC', 'USDT', 'PYUSD');

-- Invoice Status
CREATE TYPE invoicestatus AS ENUM ('draft', 'sent', 'viewed', 'paid', 'overdue', 'cancelled');

-- Subscription Status
CREATE TYPE subscriptionstatus AS ENUM (
    'ACTIVE',
    'PENDING_PAYMENT',
    'PAUSED',
    'CANCELLED',
    'PAST_DUE',
    'TRIALING'
);

-- Subscription Interval
CREATE TYPE subscriptioninterval AS ENUM ('daily', 'weekly', 'monthly', 'quarterly', 'yearly');

-- Refund Status
CREATE TYPE refundstatus AS ENUM (
    'PENDING',
    'PROCESSING',
    'COMPLETED',
    'FAILED',
    'QUEUED',
    'INSUFFICIENT_FUNDS'
);

-- Withdrawal Status
CREATE TYPE withdrawalstatus AS ENUM ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', 'CANCELLED');

-- Merchant Category
CREATE TYPE merchantcategory AS ENUM ('individual', 'startup', 'small_business', 'enterprise', 'ngo');

-- Merchant Role
CREATE TYPE merchantrole AS ENUM ('owner', 'admin', 'developer', 'finance', 'viewer');

-- ============================================================
-- CORE TABLES
-- ============================================================

-- Merchants Table
CREATE TABLE merchants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    business_name VARCHAR(255) NOT NULL,
    country VARCHAR(100),
    base_currency VARCHAR(10) DEFAULT 'USD',
    currency_preference VARCHAR(10) DEFAULT 'USD' NOT NULL,
    currency_locale VARCHAR(10) DEFAULT 'en_US' NOT NULL,
    currency_decimal_places INTEGER DEFAULT 2 NOT NULL,
    api_key VARCHAR(255) UNIQUE,
    webhook_url VARCHAR(500),
    webhook_secret VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    is_verified BOOLEAN DEFAULT FALSE NOT NULL,
    onboarding_completed BOOLEAN DEFAULT FALSE NOT NULL,
    balance_usdc NUMERIC(20, 8) DEFAULT 0 NOT NULL,
    balance_usdt NUMERIC(20, 8) DEFAULT 0 NOT NULL,
    balance_pyusd NUMERIC(20, 8) DEFAULT 0 NOT NULL,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL
);
