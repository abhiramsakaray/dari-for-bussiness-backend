-- Team RBAC Database Migration
-- Creates tables and columns for role-based access control system

-- ============================================
-- 1. CREATE NEW TABLES
-- ============================================

-- Permissions table: Defines all available permissions
CREATE TABLE IF NOT EXISTS permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(100) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    category VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_permissions_code ON permissions(code);
CREATE INDEX idx_permissions_category ON permissions(category);

-- Role permissions table: Maps permissions to roles
CREATE TABLE IF NOT EXISTS role_permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role VARCHAR(50) NOT NULL,
    permission_id UUID NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(role, permission_id)
);

CREATE INDEX idx_role_permissions_role ON role_permissions(role);
CREATE INDEX idx_role_permissions_permission ON role_permissions(permission_id);

-- Team member permissions table: Custom permission grants/revokes per team member
CREATE TABLE IF NOT EXISTS team_member_permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_member_id UUID NOT NULL REFERENCES merchant_users(id) ON DELETE CASCADE,
    permission_id UUID NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    granted BOOLEAN DEFAULT true NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    created_by UUID REFERENCES merchant_users(id),
    UNIQUE(team_member_id, permission_id)
);

CREATE INDEX idx_member_permissions_member ON team_member_permissions(team_member_id);
CREATE INDEX idx_member_permissions_permission ON team_member_permissions(permission_id);
CREATE INDEX idx_member_permissions_granted ON team_member_permissions(granted);

-- Activity logs table: Audit trail for all team member actions
CREATE TABLE IF NOT EXISTS activity_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id UUID NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
    team_member_id UUID REFERENCES merchant_users(id) ON DELETE SET NULL,
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50),
    resource_id VARCHAR(255),
    details JSONB,
    ip_address VARCHAR(45),
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_activity_logs_merchant ON activity_logs(merchant_id);
CREATE INDEX idx_activity_logs_member ON activity_logs(team_member_id);
CREATE INDEX idx_activity_logs_action ON activity_logs(action);
CREATE INDEX idx_activity_logs_created ON activity_logs(created_at);
CREATE INDEX idx_activity_logs_merchant_member ON activity_logs(merchant_id, team_member_id);
CREATE INDEX idx_activity_logs_action_created ON activity_logs(action, created_at);

-- Team member sessions table: Track active sessions
CREATE TABLE IF NOT EXISTS team_member_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_member_id UUID NOT NULL REFERENCES merchant_users(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) NOT NULL,
    ip_address VARCHAR(45),
    user_agent TEXT,
    expires_at TIMESTAMP NOT NULL,
    last_activity TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW(),
    revoked_at TIMESTAMP
);

CREATE INDEX idx_sessions_member ON team_member_sessions(team_member_id);
CREATE INDEX idx_sessions_token ON team_member_sessions(token_hash);
CREATE INDEX idx_sessions_expires ON team_member_sessions(expires_at);
CREATE INDEX idx_sessions_member_active ON team_member_sessions(team_member_id, revoked_at);

-- ============================================
-- 2. ADD COLUMNS TO EXISTING TABLES
-- ============================================

-- Add password reset and security columns to merchant_users
ALTER TABLE merchant_users 
ADD COLUMN IF NOT EXISTS password_reset_token VARCHAR(255),
ADD COLUMN IF NOT EXISTS password_reset_expires_at TIMESTAMP,
ADD COLUMN IF NOT EXISTS failed_login_attempts INT DEFAULT 0 NOT NULL,
ADD COLUMN IF NOT EXISTS locked_until TIMESTAMP,
ADD COLUMN IF NOT EXISTS created_by UUID REFERENCES merchant_users(id);

-- Add index for password reset token lookups
CREATE INDEX IF NOT EXISTS idx_merchant_users_reset_token ON merchant_users(password_reset_token);

-- ============================================
-- 3. COMMENTS FOR DOCUMENTATION
-- ============================================

COMMENT ON TABLE permissions IS 'Defines all available permissions in the system';
COMMENT ON TABLE role_permissions IS 'Maps default permissions to each role';
COMMENT ON TABLE team_member_permissions IS 'Custom permission grants/revokes per team member';
COMMENT ON TABLE activity_logs IS 'Audit trail for all team member actions';
COMMENT ON TABLE team_member_sessions IS 'Tracks active team member sessions';

COMMENT ON COLUMN team_member_permissions.granted IS 'true = grant permission, false = revoke permission';
COMMENT ON COLUMN merchant_users.failed_login_attempts IS 'Counter for failed login attempts (resets on successful login)';
COMMENT ON COLUMN merchant_users.locked_until IS 'Account locked until this timestamp (null = not locked)';
COMMENT ON COLUMN merchant_users.created_by IS 'Team member who created this account';
