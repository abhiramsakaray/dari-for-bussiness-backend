-- Seed Permission Data
-- Inserts all permission definitions and role-permission mappings

-- ============================================
-- 1. INSERT PERMISSION DEFINITIONS
-- ============================================

-- Payments permissions
INSERT INTO permissions (code, name, description, category) VALUES
('payments.view', 'View Payments', 'View payment transactions and details', 'payments'),
('payments.create', 'Create Payments', 'Create new payment sessions', 'payments'),
('payments.refund', 'Process Refunds', 'Initiate and process refunds', 'payments'),
('payments.export', 'Export Payments', 'Export payment data to CSV/Excel', 'payments')
ON CONFLICT (code) DO NOTHING;

-- Invoices permissions
INSERT INTO permissions (code, name, description, category) VALUES
('invoices.view', 'View Invoices', 'View invoice details', 'invoices'),
('invoices.create', 'Create Invoices', 'Create new invoices', 'invoices'),
('invoices.update', 'Update Invoices', 'Edit existing invoices', 'invoices'),
('invoices.delete', 'Delete Invoices', 'Delete invoices', 'invoices'),
('invoices.send', 'Send Invoices', 'Send invoices to customers', 'invoices')
ON CONFLICT (code) DO NOTHING;

-- Payment Links permissions
INSERT INTO permissions (code, name, description, category) VALUES
('payment_links.view', 'View Payment Links', 'View payment link details', 'payment_links'),
('payment_links.create', 'Create Payment Links', 'Create new payment links', 'payment_links'),
('payment_links.update', 'Update Payment Links', 'Edit existing payment links', 'payment_links'),
('payment_links.delete', 'Delete Payment Links', 'Delete payment links', 'payment_links')
ON CONFLICT (code) DO NOTHING;

-- Subscriptions permissions
INSERT INTO permissions (code, name, description, category) VALUES
('subscriptions.view', 'View Subscriptions', 'View subscription details', 'subscriptions'),
('subscriptions.create', 'Create Subscriptions', 'Create subscription plans', 'subscriptions'),
('subscriptions.update', 'Update Subscriptions', 'Edit subscription plans', 'subscriptions'),
('subscriptions.cancel', 'Cancel Subscriptions', 'Cancel active subscriptions', 'subscriptions')
ON CONFLICT (code) DO NOTHING;

-- Withdrawals permissions
INSERT INTO permissions (code, name, description, category) VALUES
('withdrawals.view', 'View Withdrawals', 'View withdrawal requests', 'withdrawals'),
('withdrawals.create', 'Create Withdrawals', 'Create withdrawal requests', 'withdrawals'),
('withdrawals.approve', 'Approve Withdrawals', 'Approve pending withdrawals', 'withdrawals')
ON CONFLICT (code) DO NOTHING;

-- Coupons permissions
INSERT INTO permissions (code, name, description, category) VALUES
('coupons.view', 'View Coupons', 'View coupon details', 'coupons'),
('coupons.create', 'Create Coupons', 'Create new coupons', 'coupons'),
('coupons.update', 'Update Coupons', 'Edit existing coupons', 'coupons'),
('coupons.delete', 'Delete Coupons', 'Delete coupons', 'coupons')
ON CONFLICT (code) DO NOTHING;

-- Team Management permissions
INSERT INTO permissions (code, name, description, category) VALUES
('team.view', 'View Team Members', 'View team member list and details', 'team'),
('team.create', 'Add Team Members', 'Invite and create team member accounts', 'team'),
('team.update', 'Update Team Members', 'Edit team member roles and permissions', 'team'),
('team.delete', 'Remove Team Members', 'Remove team members from account', 'team'),
('team.view_logs', 'View Activity Logs', 'View team member activity logs', 'team')
ON CONFLICT (code) DO NOTHING;

-- API & Integrations permissions
INSERT INTO permissions (code, name, description, category) VALUES
('api_keys.view', 'View API Keys', 'View API key details', 'integrations'),
('api_keys.manage', 'Manage API Keys', 'Create and delete API keys', 'integrations'),
('webhooks.view', 'View Webhooks', 'View webhook configurations', 'integrations'),
('webhooks.manage', 'Manage Webhooks', 'Create, update, and delete webhooks', 'integrations')
ON CONFLICT (code) DO NOTHING;

-- Analytics permissions
INSERT INTO permissions (code, name, description, category) VALUES
('analytics.view', 'View Analytics', 'View analytics dashboard and reports', 'analytics'),
('analytics.export', 'Export Analytics', 'Export analytics data', 'analytics')
ON CONFLICT (code) DO NOTHING;

-- Settings permissions
INSERT INTO permissions (code, name, description, category) VALUES
('settings.view', 'View Settings', 'View account settings', 'settings'),
('settings.update', 'Update Settings', 'Update account settings', 'settings'),
('settings.billing', 'Manage Billing', 'Manage billing and subscription plans', 'settings')
ON CONFLICT (code) DO NOTHING;

-- Wallets permissions
INSERT INTO permissions (code, name, description, category) VALUES
('wallets.view', 'View Wallets', 'View wallet addresses and balances', 'wallets'),
('wallets.manage', 'Manage Wallets', 'Add and remove wallet addresses', 'wallets')
ON CONFLICT (code) DO NOTHING;

-- ============================================
-- 2. INSERT ROLE-PERMISSION MAPPINGS
-- ============================================

-- OWNER role: All permissions (using wildcard in code, but explicit here for clarity)
INSERT INTO role_permissions (role, permission_id)
SELECT 'owner', id FROM permissions
ON CONFLICT (role, permission_id) DO NOTHING;

-- ADMIN role: Full access except billing
INSERT INTO role_permissions (role, permission_id)
SELECT 'admin', id FROM permissions WHERE code IN (
    -- Payments
    'payments.view', 'payments.create', 'payments.refund', 'payments.export',
    -- Invoices
    'invoices.view', 'invoices.create', 'invoices.update', 'invoices.delete', 'invoices.send',
    -- Payment Links
    'payment_links.view', 'payment_links.create', 'payment_links.update', 'payment_links.delete',
    -- Subscriptions
    'subscriptions.view', 'subscriptions.create', 'subscriptions.update', 'subscriptions.cancel',
    -- Withdrawals
    'withdrawals.view', 'withdrawals.create',
    -- Coupons
    'coupons.view', 'coupons.create', 'coupons.update', 'coupons.delete',
    -- Team
    'team.view', 'team.create', 'team.update', 'team.delete', 'team.view_logs',
    -- Integrations
    'api_keys.view', 'webhooks.view',
    -- Analytics
    'analytics.view', 'analytics.export',
    -- Settings
    'settings.view', 'settings.update',
    -- Wallets
    'wallets.view'
)
ON CONFLICT (role, permission_id) DO NOTHING;

-- DEVELOPER role: API, webhooks, payments view
INSERT INTO role_permissions (role, permission_id)
SELECT 'developer', id FROM permissions WHERE code IN (
    'payments.view',
    'invoices.view',
    'payment_links.view',
    'subscriptions.view',
    'api_keys.view', 'api_keys.manage',
    'webhooks.view', 'webhooks.manage',
    'analytics.view',
    'settings.view'
)
ON CONFLICT (role, permission_id) DO NOTHING;

-- FINANCE role: Payments, invoices, refunds, analytics
INSERT INTO role_permissions (role, permission_id)
SELECT 'finance', id FROM permissions WHERE code IN (
    -- Payments
    'payments.view', 'payments.create', 'payments.refund', 'payments.export',
    -- Invoices
    'invoices.view', 'invoices.create', 'invoices.update', 'invoices.delete', 'invoices.send',
    -- Payment Links
    'payment_links.view',
    -- Subscriptions
    'subscriptions.view',
    -- Withdrawals
    'withdrawals.view', 'withdrawals.create', 'withdrawals.approve',
    -- Coupons
    'coupons.view',
    -- Analytics
    'analytics.view', 'analytics.export',
    -- Settings
    'settings.view'
)
ON CONFLICT (role, permission_id) DO NOTHING;

-- VIEWER role: Read-only access
INSERT INTO role_permissions (role, permission_id)
SELECT 'viewer', id FROM permissions WHERE code IN (
    'payments.view',
    'invoices.view',
    'payment_links.view',
    'subscriptions.view',
    'withdrawals.view',
    'coupons.view',
    'analytics.view',
    'settings.view'
)
ON CONFLICT (role, permission_id) DO NOTHING;

-- ============================================
-- 3. VERIFICATION QUERIES
-- ============================================

-- Count permissions per role
SELECT 
    role,
    COUNT(*) as permission_count
FROM role_permissions
GROUP BY role
ORDER BY role;

-- Show all permissions
SELECT 
    category,
    COUNT(*) as permission_count
FROM permissions
GROUP BY category
ORDER BY category;
