-- Normalize legacy uppercase subscription status values to lowercase values expected by ORM.
-- Safe to run multiple times.

ALTER TYPE subscription_status ADD VALUE IF NOT EXISTS 'pending_payment';
ALTER TYPE subscription_status ADD VALUE IF NOT EXISTS 'PENDING_PAYMENT';

UPDATE subscriptions
SET status = CASE status::text
    WHEN 'ACTIVE' THEN 'active'::subscription_status
    WHEN 'PAUSED' THEN 'paused'::subscription_status
    WHEN 'CANCELLED' THEN 'cancelled'::subscription_status
    WHEN 'PAST_DUE' THEN 'past_due'::subscription_status
    WHEN 'TRIALING' THEN 'trialing'::subscription_status
    WHEN 'PENDING_PAYMENT' THEN 'pending_payment'::subscription_status
    ELSE status
END
WHERE status::text IN (
    'ACTIVE', 'PAUSED', 'CANCELLED', 'PAST_DUE', 'TRIALING', 'PENDING_PAYMENT'
);
