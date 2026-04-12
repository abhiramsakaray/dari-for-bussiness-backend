# Team RBAC Frontend Integration Guide

## Complete End-to-End Implementation

This comprehensive guide covers everything needed to integrate the Team RBAC system into your frontend application.

---

## Table of Contents

1. [Overview](#overview)
2. [Authentication Flow](#authentication-flow)
3. [API Endpoints Reference](#api-endpoints-reference)
4. [Complete React/TypeScript Implementation](#complete-reacttypescript-implementation)
5. [Permission System](#permission-system)
6. [Session Management](#session-management)
7. [Error Handling](#error-handling)
8. [Security Best Practices](#security-best-practices)
9. [Testing](#testing)
10. [Deployment Checklist](#deployment-checklist)

---

## Overview

### What's Included

The Team RBAC backend provides:
- JWT-based authentication (access + refresh tokens)
- Role-based permissions with custom overrides
- Session tracking and management
- Activity logging for audit trails
- Account security (lockout, password reset)

### Key Features

- **5 Roles**: Owner, Admin, Developer, Finance, Viewer
- **40+ Permissions**: Granular control across 12 categories
- **Wildcard Support**: `*` (all), `category.*` (category-wide)
- **Session Management**: Track and revoke active sessions
- **Activity Logs**: Complete audit trail

---

## Authentication Flow

### 1. Login Process

```
User → Frontend → POST /auth/team/login → Backend
                                        ↓
                                   Validates credentials
                                   Checks account status
                                   Creates session
                                        ↓
Backend → Frontend ← Returns tokens + user info
         ↓
    Store tokens
    Redirect to dashboard
```

### 2. Token Refresh Process

```
API Request → 401 Unauthorized
     ↓
Check if refresh token exists
     ↓
POST /auth/team/refresh with refresh_token
     ↓
Receive new access_token
     ↓
Retry original request
```

### 3. Logout Process

```
User clicks logout
     ↓
POST /auth/team/logout (revokes session)
     ↓
Clear local tokens
     ↓
Redirect to login
```

---

## API Endpoints Reference

### Base URL
```
Production: https://api.yourapp.com/api/v1
Development: http://localhost:8000/api/v1
```


### Authentication Endpoints

#### 1. Login
**POST** `/auth/team/login`

Request:
```json
{
  "email": "john@example.com",
  "password": "SecureP@ss123"
}
```

Response (200):
```json
{
  "access_token": "eyJhbGc...",
  "refresh_token": "eyJhbGc...",
  "token_type": "bearer",
  "expires_in": 3600,
  "team_member": {
    "id": "uuid",
    "email": "john@example.com",
    "name": "John Doe",
    "role": "admin",
    "merchant_id": "uuid"
  }
}
```

Errors:
- 401: Invalid credentials
- 423: Account locked

#### 2. Logout
**POST** `/auth/team/logout`

Headers: `Authorization: Bearer <token>`

Response (200):
```json
{ "message": "Logged out successfully" }
```

#### 3. Refresh Token
**POST** `/auth/team/refresh`

Request:
```json
{ "refresh_token": "eyJhbGc..." }
```

Response (200):
```json
{
  "access_token": "eyJhbGc...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

#### 4. Forgot Password
**POST** `/auth/team/forgot-password`

Request:
```json
{ "email": "john@example.com" }
```

Response (200):
```json
{ "message": "If an account exists, reset link sent" }
```

#### 5. Reset Password
**POST** `/auth/team/reset-password`

Request:
```json
{
  "token": "reset_token",
  "new_password": "NewP@ss123"
}
```

#### 6. Change Password
**POST** `/auth/team/change-password`

Headers: `Authorization: Bearer <token>`

Request:
```json
{
  "current_password": "OldP@ss123",
  "new_password": "NewP@ss123"
}
```


### Permission Endpoints

#### 1. Get All Permissions
**GET** `/team/permissions`

Response (200):
```json
{
  "permissions": [
    {
      "code": "payments.view",
      "name": "View payment transactions",
      "description": "View payment transactions",
      "category": "payments"
    }
  ]
}
```

#### 2. Get Role Permissions
**GET** `/team/roles/{role}/permissions`

Response (200):
```json
{
  "role": "admin",
  "permissions": [
    { "code": "payments.*", "name": "All payment permissions", "category": "payments" }
  ]
}
```

#### 3. Get Member Permissions
**GET** `/team/members/{id}/permissions`

Headers: `Authorization: Bearer <token>`

Response (200):
```json
{
  "member_id": "uuid",
  "role": "developer",
  "role_permissions": ["payments.view", "api_keys.*"],
  "custom_granted": ["payments.refund"],
  "custom_revoked": ["api_keys.manage"],
  "effective_permissions": ["payments.view", "payments.refund", "api_keys.view"]
}
```

#### 4. Update Member Permissions
**POST** `/team/members/{id}/permissions`

Headers: `Authorization: Bearer <token>`

Request:
```json
{
  "grant": ["payments.refund"],
  "revoke": ["api_keys.manage"]
}
```

### Session Endpoints

#### 1. Get Active Sessions
**GET** `/team/members/{id}/sessions`

Headers: `Authorization: Bearer <token>`

Response (200):
```json
{
  "sessions": [
    {
      "id": "uuid",
      "ip_address": "192.168.1.1",
      "user_agent": "Mozilla/5.0...",
      "last_activity": "2026-04-12T10:30:00Z",
      "expires_at": "2026-04-13T09:00:00Z",
      "is_current": true
    }
  ]
}
```

#### 2. Revoke All Sessions
**POST** `/team/members/{id}/revoke-sessions`

Headers: `Authorization: Bearer <token>`

Response (200):
```json
{
  "message": "All sessions revoked",
  "sessions_revoked": 3
}
```

### Activity Log Endpoints

#### Get Activity Logs
**GET** `/team/activity-logs`

Headers: `Authorization: Bearer <token>`

Query Parameters:
- `page` (int): Page number
- `page_size` (int): Items per page
- `team_member_id` (uuid): Filter by member
- `action` (string): Filter by action
- `start_date`, `end_date` (datetime): Date range

Response (200):
```json
{
  "items": [
    {
      "id": "uuid",
      "team_member": { "id": "uuid", "email": "john@example.com", "name": "John Doe" },
      "action": "team.login",
      "details": { "email": "john@example.com", "role": "admin" },
      "ip_address": "192.168.1.1",
      "created_at": "2026-04-12T10:00:00Z"
    }
  ],
  "total": 150,
  "page": 1,
  "page_size": 50
}
```


---

## Complete React/TypeScript Implementation

### Project Structure

```
src/
├── services/
│   └── teamAuth.ts          # Authentication service
├── hooks/
│   └── usePermissions.ts    # Permission hook
├── components/
│   ├── TeamLogin.tsx        # Login component
│   ├── ProtectedRoute.tsx   # Route guard
│   ├── PermissionGate.tsx   # Permission-based rendering
│   └── SessionManager.tsx   # Session management UI
├── utils/
│   └── errorHandler.ts      # Error handling utilities
└── App.tsx                  # Main app with routes
```

### 1. Authentication Service (teamAuth.ts)

```typescript
import axios, { AxiosInstance, AxiosError } from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000/api/v1';

interface LoginCredentials {
  email: string;
  password: string;
}

interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  team_member: {
    id: string;
    email: string;
    name: string;
    role: string;
    merchant_id: string;
  };
}

interface RefreshResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

class TeamAuthService {
  private api: AxiosInstance;

  constructor() {
    this.api = axios.create({ baseURL: API_BASE_URL });

    // Request interceptor: Add access token
    this.api.interceptors.request.use(
      (config) => {
        const token = this.getAccessToken();
        if (token) {
          config.headers.Authorization = `Bearer ${token}`;
        }
        return config;
      },
      (error) => Promise.reject(error)
    );

    // Response interceptor: Handle token refresh
    this.api.interceptors.response.use(
      (response) => response,
      async (error: AxiosError) => {
        const originalRequest: any = error.config;

        if (error.response?.status === 401 && !originalRequest._retry) {
          originalRequest._retry = true;

          try {
            const newToken = await this.refreshAccessToken();
            originalRequest.headers.Authorization = `Bearer ${newToken}`;
            return this.api(originalRequest);
          } catch (refreshError) {
            this.logout();
            window.location.href = '/login';
            return Promise.reject(refreshError);
          }
        }

        return Promise.reject(error);
      }
    );
  }

  async login(credentials: LoginCredentials): Promise<LoginResponse> {
    const response = await this.api.post<LoginResponse>('/auth/team/login', credentials);
    
    localStorage.setItem('access_token', response.data.access_token);
    localStorage.setItem('refresh_token', response.data.refresh_token);
    localStorage.setItem('team_member', JSON.stringify(response.data.team_member));
    
    return response.data;
  }

  async logout(): Promise<void> {
    try {
      await this.api.post('/auth/team/logout');
    } catch (error) {
      console.error('Logout error:', error);
    } finally {
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      localStorage.removeItem('team_member');
    }
  }

  async refreshAccessToken(): Promise<string> {
    const refreshToken = this.getRefreshToken();
    if (!refreshToken) throw new Error('No refresh token');

    const response = await axios.post<RefreshResponse>(
      `${API_BASE_URL}/auth/team/refresh`,
      { refresh_token: refreshToken }
    );

    const newAccessToken = response.data.access_token;
    localStorage.setItem('access_token', newAccessToken);
    return newAccessToken;
  }

  async forgotPassword(email: string): Promise<void> {
    await this.api.post('/auth/team/forgot-password', { email });
  }

  async resetPassword(token: string, newPassword: string): Promise<void> {
    await this.api.post('/auth/team/reset-password', {
      token,
      new_password: newPassword,
    });
  }

  async changePassword(currentPassword: string, newPassword: string): Promise<void> {
    await this.api.post('/auth/team/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    });
  }

  getAccessToken(): string | null {
    return localStorage.getItem('access_token');
  }

  getRefreshToken(): string | null {
    return localStorage.getItem('refresh_token');
  }

  getCurrentUser(): any | null {
    const userStr = localStorage.getItem('team_member');
    return userStr ? JSON.parse(userStr) : null;
  }

  isAuthenticated(): boolean {
    return !!this.getAccessToken();
  }
}

export const teamAuthService = new TeamAuthService();
export default teamAuthService;
```


### 2. Permission Hook (usePermissions.ts)

```typescript
import { useState, useEffect } from 'react';
import axios from 'axios';
import teamAuthService from '../services/teamAuth';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000/api/v1';

export const usePermissions = () => {
  const [permissions, setPermissions] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchPermissions = async () => {
      try {
        const user = teamAuthService.getCurrentUser();
        if (!user) {
          setLoading(false);
          return;
        }

        const response = await axios.get(
          `${API_BASE_URL}/team/members/${user.id}/permissions`,
          {
            headers: {
              Authorization: `Bearer ${teamAuthService.getAccessToken()}`,
            },
          }
        );

        setPermissions(response.data.effective_permissions);
      } catch (error) {
        console.error('Failed to fetch permissions:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchPermissions();
  }, []);

  const hasPermission = (required: string): boolean => {
    if (permissions.includes('*')) return true;
    if (permissions.includes(required)) return true;
    
    const category = required.split('.')[0];
    if (permissions.includes(`${category}.*`)) return true;
    
    return false;
  };

  const hasAnyPermission = (requiredPermissions: string[]): boolean => {
    return requiredPermissions.some((perm) => hasPermission(perm));
  };

  const hasAllPermissions = (requiredPermissions: string[]): boolean => {
    return requiredPermissions.every((perm) => hasPermission(perm));
  };

  return {
    permissions,
    loading,
    hasPermission,
    hasAnyPermission,
    hasAllPermissions,
  };
};
```

### 3. Login Component (TeamLogin.tsx)

```typescript
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import teamAuthService from '../services/teamAuth';

export const TeamLogin: React.FC = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      await teamAuthService.login({ email, password });
      navigate('/dashboard');
    } catch (err: any) {
      if (err.response?.status === 423) {
        setError(`Account locked: ${err.response.data.detail.message}`);
      } else if (err.response?.status === 401) {
        setError('Invalid email or password');
      } else {
        setError('Login failed. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-container">
      <h2>Team Member Login</h2>
      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label htmlFor="email">Email</label>
          <input
            type="email"
            id="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            disabled={loading}
          />
        </div>
        
        <div className="form-group">
          <label htmlFor="password">Password</label>
          <input
            type="password"
            id="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            disabled={loading}
          />
        </div>

        {error && <div className="error-message">{error}</div>}

        <button type="submit" disabled={loading}>
          {loading ? 'Logging in...' : 'Login'}
        </button>
      </form>

      <div className="forgot-password">
        <a href="/forgot-password">Forgot password?</a>
      </div>
    </div>
  );
};
```


### 4. Protected Route Component (ProtectedRoute.tsx)

```typescript
import React from 'react';
import { Navigate } from 'react-router-dom';
import teamAuthService from '../services/teamAuth';
import { usePermissions } from '../hooks/usePermissions';

interface ProtectedRouteProps {
  children: React.ReactNode;
  requiredPermissions?: string[];
  requireAll?: boolean;
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({
  children,
  requiredPermissions = [],
  requireAll = false,
}) => {
  const { hasAnyPermission, hasAllPermissions, loading } = usePermissions();

  if (!teamAuthService.isAuthenticated()) {
    return <Navigate to="/login" replace />;
  }

  if (loading) {
    return <div>Loading...</div>;
  }

  if (requiredPermissions.length > 0) {
    const hasAccess = requireAll
      ? hasAllPermissions(requiredPermissions)
      : hasAnyPermission(requiredPermissions);

    if (!hasAccess) {
      return <Navigate to="/unauthorized" replace />;
    }
  }

  return <>{children}</>;
};
```

### 5. Permission Gate Component (PermissionGate.tsx)

```typescript
import React from 'react';
import { usePermissions } from '../hooks/usePermissions';

interface PermissionGateProps {
  children: React.ReactNode;
  requiredPermissions: string[];
  requireAll?: boolean;
  fallback?: React.ReactNode;
}

export const PermissionGate: React.FC<PermissionGateProps> = ({
  children,
  requiredPermissions,
  requireAll = false,
  fallback = null,
}) => {
  const { hasAnyPermission, hasAllPermissions, loading } = usePermissions();

  if (loading) return null;

  const hasAccess = requireAll
    ? hasAllPermissions(requiredPermissions)
    : hasAnyPermission(requiredPermissions);

  return hasAccess ? <>{children}</> : <>{fallback}</>;
};
```

### 6. Session Manager Component (SessionManager.tsx)

```typescript
import React, { useState, useEffect } from 'react';
import axios from 'axios';
import teamAuthService from '../services/teamAuth';

interface Session {
  id: string;
  ip_address: string;
  user_agent: string;
  last_activity: string;
  expires_at: string;
  is_current: boolean;
}

export const SessionManager: React.FC = () => {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchSessions();
  }, []);

  const fetchSessions = async () => {
    try {
      const user = teamAuthService.getCurrentUser();
      const response = await axios.get(
        `${process.env.REACT_APP_API_URL}/api/v1/team/members/${user.id}/sessions`,
        {
          headers: {
            Authorization: `Bearer ${teamAuthService.getAccessToken()}`,
          },
        }
      );
      setSessions(response.data.sessions);
    } catch (error) {
      console.error('Failed to fetch sessions:', error);
    } finally {
      setLoading(false);
    }
  };

  const revokeAllSessions = async () => {
    if (!confirm('Revoke all sessions? You will be logged out.')) return;

    try {
      const user = teamAuthService.getCurrentUser();
      await axios.post(
        `${process.env.REACT_APP_API_URL}/api/v1/team/members/${user.id}/revoke-sessions`,
        {},
        {
          headers: {
            Authorization: `Bearer ${teamAuthService.getAccessToken()}`,
          },
        }
      );
      
      teamAuthService.logout();
      window.location.href = '/login';
    } catch (error) {
      console.error('Failed to revoke sessions:', error);
    }
  };

  if (loading) return <div>Loading sessions...</div>;

  return (
    <div className="session-manager">
      <h2>Active Sessions</h2>
      
      <button onClick={revokeAllSessions} className="btn-danger">
        Revoke All Sessions
      </button>

      <div className="sessions-list">
        {sessions.map((session) => (
          <div key={session.id} className={`session-item ${session.is_current ? 'current' : ''}`}>
            <strong>{session.is_current ? 'Current Session' : 'Other Session'}</strong>
            <p>IP: {session.ip_address}</p>
            <p>Device: {session.user_agent}</p>
            <p>Last Activity: {new Date(session.last_activity).toLocaleString()}</p>
            <p>Expires: {new Date(session.expires_at).toLocaleString()}</p>
          </div>
        ))}
      </div>
    </div>
  );
};
```


### 7. Error Handler Utility (errorHandler.ts)

```typescript
import { AxiosError } from 'axios';

export interface ApiError {
  message: string;
  error_code?: string;
  required_permission?: string;
  user_permissions?: string[];
}

export const handleApiError = (error: unknown): string => {
  if (axios.isAxiosError(error)) {
    const axiosError = error as AxiosError<ApiError>;

    switch (axiosError.response?.status) {
      case 401:
        return 'Authentication failed. Please log in again.';
      
      case 403:
        const detail = axiosError.response.data;
        if (detail.error_code === 'PERMISSION_DENIED') {
          return `Access denied. Required: ${detail.required_permission}`;
        }
        return 'You do not have permission to perform this action.';
      
      case 423:
        return 'Account is locked. Please try again later.';
      
      case 400:
        return axiosError.response.data.message || 'Invalid request.';
      
      case 404:
        return 'Resource not found.';
      
      case 500:
        return 'Server error. Please try again later.';
      
      default:
        return 'An unexpected error occurred.';
    }
  }

  return 'An unexpected error occurred.';
};
```

### 8. Main App with Routes (App.tsx)

```typescript
import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { TeamLogin } from './components/TeamLogin';
import { Dashboard } from './components/Dashboard';
import { ProtectedRoute } from './components/ProtectedRoute';
import { SessionManager } from './components/SessionManager';
import { Unauthorized } from './components/Unauthorized';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<TeamLogin />} />
        <Route path="/unauthorized" element={<Unauthorized />} />
        
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              <Dashboard />
            </ProtectedRoute>
          }
        />
        
        <Route
          path="/sessions"
          element={
            <ProtectedRoute>
              <SessionManager />
            </ProtectedRoute>
          }
        />
        
        <Route
          path="/payments"
          element={
            <ProtectedRoute requiredPermissions={['payments.view']}>
              <PaymentsPage />
            </ProtectedRoute>
          }
        />
        
        <Route
          path="/team"
          element={
            <ProtectedRoute requiredPermissions={['team.view']}>
              <TeamManagementPage />
            </ProtectedRoute>
          }
        />
        
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
```

### 9. Dashboard with Permission-Based UI

```typescript
import React from 'react';
import { PermissionGate } from '../components/PermissionGate';
import { usePermissions } from '../hooks/usePermissions';

export const Dashboard: React.FC = () => {
  const { hasPermission } = usePermissions();

  return (
    <div className="dashboard">
      <h1>Dashboard</h1>

      <PermissionGate requiredPermissions={['payments.view']}>
        <section className="payments-section">
          <h2>Payments</h2>
          
          <PermissionGate requiredPermissions={['payments.create']}>
            <button>Create Payment</button>
          </PermissionGate>

          <div className="payment-list">
            {/* Payment list */}
          </div>
        </section>
      </PermissionGate>

      <PermissionGate requiredPermissions={['team.view']}>
        <section className="team-section">
          <h2>Team Members</h2>
          {/* Team management */}
        </section>
      </PermissionGate>

      <PermissionGate requiredPermissions={['analytics.view']}>
        <section className="analytics-section">
          <h2>Analytics</h2>
          {/* Analytics dashboard */}
        </section>
      </PermissionGate>
    </div>
  );
};
```


---

## Permission System

### Available Permissions

#### Payments
- `payments.view` - View payment transactions
- `payments.create` - Create payment sessions
- `payments.refund` - Process refunds
- `payments.export` - Export payment data

#### Invoices
- `invoices.view` - View invoices
- `invoices.create` - Create invoices
- `invoices.update` - Update invoices
- `invoices.delete` - Delete invoices
- `invoices.send` - Send invoices to customers

#### Payment Links
- `payment_links.view` - View payment links
- `payment_links.create` - Create payment links
- `payment_links.update` - Update payment links
- `payment_links.delete` - Delete payment links

#### Subscriptions
- `subscriptions.view` - View subscriptions
- `subscriptions.create` - Create subscription plans
- `subscriptions.update` - Update subscriptions
- `subscriptions.cancel` - Cancel subscriptions

#### Withdrawals
- `withdrawals.view` - View withdrawals
- `withdrawals.create` - Create withdrawal requests
- `withdrawals.approve` - Approve withdrawals

#### Coupons
- `coupons.view` - View coupons
- `coupons.create` - Create coupons
- `coupons.update` - Update coupons
- `coupons.delete` - Delete coupons

#### Team Management
- `team.view` - View team members
- `team.create` - Add team members
- `team.update` - Update team members
- `team.delete` - Remove team members
- `team.view_logs` - View activity logs

#### API & Integrations
- `api_keys.view` - View API keys
- `api_keys.manage` - Create/delete API keys
- `webhooks.view` - View webhooks
- `webhooks.manage` - Manage webhooks

#### Analytics
- `analytics.view` - View analytics dashboard
- `analytics.export` - Export analytics data

#### Settings
- `settings.view` - View settings
- `settings.update` - Update settings
- `settings.billing` - Manage billing and plans

#### Wallets
- `wallets.view` - View wallet addresses
- `wallets.manage` - Add/remove wallets

### Role Permissions

#### Owner
- Permissions: `*` (all permissions)
- Full system access

#### Admin
- Permissions: `payments.*`, `invoices.*`, `payment_links.*`, `subscriptions.*`, `withdrawals.view`, `withdrawals.create`, `coupons.*`, `team.*`, `api_keys.view`, `webhooks.view`, `analytics.*`, `settings.view`, `settings.update`, `wallets.view`
- Full access to most resources, limited withdrawals

#### Developer
- Permissions: `payments.view`, `invoices.view`, `payment_links.view`, `subscriptions.view`, `api_keys.*`, `webhooks.*`, `analytics.view`, `settings.view`
- API/webhook management, view-only for business data

#### Finance
- Permissions: `payments.*`, `invoices.*`, `payment_links.view`, `subscriptions.view`, `withdrawals.*`, `coupons.view`, `analytics.*`, `settings.view`
- Full payment/invoice/withdrawal access, view-only for others

#### Viewer
- Permissions: `payments.view`, `invoices.view`, `payment_links.view`, `subscriptions.view`, `withdrawals.view`, `coupons.view`, `analytics.view`, `settings.view`
- View-only access to all resources

### Wildcard Permissions

- `*` - Grants all permissions (Owner role)
- `category.*` - Grants all permissions in a category (e.g., `payments.*`)
- Exact match - Specific permission (e.g., `payments.view`)

### Permission Checking Examples

```typescript
// Check single permission
if (hasPermission('payments.create')) {
  // Show create button
}

// Check any of multiple permissions
if (hasAnyPermission(['payments.create', 'invoices.create'])) {
  // Show create menu
}

// Check all permissions required
if (hasAllPermissions(['payments.view', 'payments.export'])) {
  // Show export button
}

// Wildcard check (automatic)
// User with "payments.*" will pass hasPermission('payments.view')
```


---

## Session Management

### Session Lifecycle

1. **Creation**: Session created on successful login
2. **Tracking**: Last activity updated on each API request
3. **Expiry**: Sessions expire after 24 hours
4. **Revocation**: Can be manually revoked by user or admin

### Session Information

Each session includes:
- Session ID
- IP address
- User agent (browser/device info)
- Last activity timestamp
- Expiry timestamp
- Current session flag

### Managing Sessions

```typescript
// Get all active sessions
const sessions = await axios.get(
  `/api/v1/team/members/${userId}/sessions`,
  { headers: { Authorization: `Bearer ${token}` } }
);

// Revoke all sessions (logout everywhere)
await axios.post(
  `/api/v1/team/members/${userId}/revoke-sessions`,
  {},
  { headers: { Authorization: `Bearer ${token}` } }
);
```

### Security Features

- **Session Tracking**: Monitor active sessions across devices
- **Remote Logout**: Revoke sessions from other devices
- **Automatic Cleanup**: Expired sessions cleaned up automatically
- **Activity Monitoring**: Track last activity for each session

---

## Error Handling

### Common Error Codes

| Status | Error Code | Meaning | Action |
|--------|------------|---------|--------|
| 401 | - | Unauthorized | Redirect to login |
| 403 | PERMISSION_DENIED | Insufficient permissions | Show error message |
| 423 | - | Account locked | Show lockout message |
| 400 | - | Bad request | Show validation errors |
| 404 | - | Not found | Show not found message |
| 500 | - | Server error | Show generic error |

### Error Response Format

```json
{
  "detail": {
    "message": "Missing required permission: payments.create",
    "error_code": "PERMISSION_DENIED",
    "required_permission": "payments.create",
    "user_permissions": ["payments.view", "invoices.view"]
  }
}
```

### Handling Errors in Components

```typescript
try {
  await someApiCall();
} catch (error) {
  const errorMessage = handleApiError(error);
  setError(errorMessage);
  
  // Log for debugging
  console.error('API Error:', error);
  
  // Show user-friendly message
  toast.error(errorMessage);
}
```

### Global Error Boundary

```typescript
import React, { Component, ErrorInfo, ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Uncaught error:', error, errorInfo);
  }

  public render() {
    if (this.state.hasError) {
      return (
        <div className="error-boundary">
          <h1>Something went wrong</h1>
          <p>Please refresh the page or contact support.</p>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
```

---

## Security Best Practices

### 1. Token Storage

**Development (localStorage):**
```typescript
localStorage.setItem('access_token', token);
```

**Production (httpOnly cookies - recommended):**
```typescript
// Backend sets cookie
res.cookie('access_token', token, {
  httpOnly: true,
  secure: true,
  sameSite: 'strict',
  maxAge: 3600000
});

// Frontend automatically sends cookie
// No manual token management needed
```

### 2. HTTPS Only

Always use HTTPS in production:
```typescript
const API_BASE_URL = process.env.NODE_ENV === 'production'
  ? 'https://api.yourapp.com/api/v1'
  : 'http://localhost:8000/api/v1';
```

### 3. Token Refresh Strategy

```typescript
// Refresh token before expiry (e.g., at 50 minutes for 1-hour token)
useEffect(() => {
  const refreshInterval = setInterval(async () => {
    try {
      await teamAuthService.refreshAccessToken();
    } catch (error) {
      console.error('Token refresh failed:', error);
      teamAuthService.logout();
      window.location.href = '/login';
    }
  }, 50 * 60 * 1000); // 50 minutes

  return () => clearInterval(refreshInterval);
}, []);
```

### 4. Permission Checks

**Always check on both frontend and backend:**
- Frontend: For UX (hide/show UI elements)
- Backend: For security (enforce access control)

```typescript
// Frontend check (UX only)
<PermissionGate requiredPermissions={['payments.create']}>
  <button onClick={createPayment}>Create Payment</button>
</PermissionGate>

// Backend still validates permission on API call
```

### 5. Sensitive Data

Never expose sensitive data:
```typescript
// ❌ Bad
console.log('Token:', accessToken);
console.log('User:', user);

// ✅ Good
console.log('User logged in');
```

### 6. Session Timeout Warning

```typescript
const SessionTimeoutWarning: React.FC = () => {
  const [showWarning, setShowWarning] = useState(false);

  useEffect(() => {
    // Show warning 5 minutes before expiry
    const warningTimeout = setTimeout(() => {
      setShowWarning(true);
    }, 55 * 60 * 1000); // 55 minutes

    return () => clearTimeout(warningTimeout);
  }, []);

  if (!showWarning) return null;

  return (
    <div className="session-warning">
      <p>Your session will expire soon. Continue working?</p>
      <button onClick={() => {
        teamAuthService.refreshAccessToken();
        setShowWarning(false);
      }}>
        Continue
      </button>
    </div>
  );
};
```

### 7. XSS Protection

```typescript
// Sanitize user input
import DOMPurify from 'dompurify';

const sanitizedInput = DOMPurify.sanitize(userInput);
```

### 8. CSRF Protection

```typescript
// Include CSRF token in requests
axios.defaults.headers.common['X-CSRF-Token'] = csrfToken;
```


---

## Testing

### Unit Tests

#### Testing Authentication Service

```typescript
import { teamAuthService } from '../services/teamAuth';
import axios from 'axios';

jest.mock('axios');
const mockedAxios = axios as jest.Mocked<typeof axios>;

describe('TeamAuthService', () => {
  beforeEach(() => {
    localStorage.clear();
    jest.clearAllMocks();
  });

  it('should login successfully', async () => {
    const mockResponse = {
      data: {
        access_token: 'token123',
        refresh_token: 'refresh123',
        token_type: 'bearer',
        expires_in: 3600,
        team_member: {
          id: '1',
          email: 'test@example.com',
          name: 'Test User',
          role: 'admin',
          merchant_id: '1',
        },
      },
    };

    mockedAxios.post.mockResolvedValue(mockResponse);

    const result = await teamAuthService.login({
      email: 'test@example.com',
      password: 'password123',
    });

    expect(result).toEqual(mockResponse.data);
    expect(localStorage.getItem('access_token')).toBe('token123');
    expect(localStorage.getItem('refresh_token')).toBe('refresh123');
  });

  it('should handle login failure', async () => {
    mockedAxios.post.mockRejectedValue({
      response: { status: 401, data: { detail: 'Invalid credentials' } },
    });

    await expect(
      teamAuthService.login({
        email: 'test@example.com',
        password: 'wrong',
      })
    ).rejects.toThrow();
  });
});
```

#### Testing Permission Hook

```typescript
import { renderHook, waitFor } from '@testing-library/react';
import { usePermissions } from '../hooks/usePermissions';
import axios from 'axios';

jest.mock('axios');
const mockedAxios = axios as jest.Mocked<typeof axios>;

describe('usePermissions', () => {
  it('should fetch and check permissions', async () => {
    mockedAxios.get.mockResolvedValue({
      data: {
        effective_permissions: ['payments.view', 'payments.create', 'invoices.*'],
      },
    });

    const { result } = renderHook(() => usePermissions());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.hasPermission('payments.view')).toBe(true);
    expect(result.current.hasPermission('payments.create')).toBe(true);
    expect(result.current.hasPermission('invoices.view')).toBe(true); // wildcard
    expect(result.current.hasPermission('team.view')).toBe(false);
  });
});
```

### Integration Tests

```typescript
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { TeamLogin } from '../components/TeamLogin';
import teamAuthService from '../services/teamAuth';

jest.mock('../services/teamAuth');

describe('TeamLogin Integration', () => {
  it('should complete login flow', async () => {
    const mockLogin = jest.spyOn(teamAuthService, 'login').mockResolvedValue({
      access_token: 'token',
      refresh_token: 'refresh',
      token_type: 'bearer',
      expires_in: 3600,
      team_member: {
        id: '1',
        email: 'test@example.com',
        name: 'Test User',
        role: 'admin',
        merchant_id: '1',
      },
    });

    render(
      <BrowserRouter>
        <TeamLogin />
      </BrowserRouter>
    );

    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: 'test@example.com' },
    });
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: 'password123' },
    });
    fireEvent.click(screen.getByRole('button', { name: /login/i }));

    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalledWith({
        email: 'test@example.com',
        password: 'password123',
      });
    });
  });
});
```

### E2E Tests (Cypress)

```typescript
describe('Team RBAC E2E', () => {
  it('should login and access dashboard', () => {
    cy.visit('/login');
    
    cy.get('input[type="email"]').type('admin@example.com');
    cy.get('input[type="password"]').type('password123');
    cy.get('button[type="submit"]').click();
    
    cy.url().should('include', '/dashboard');
    cy.contains('Dashboard').should('be.visible');
  });

  it('should enforce permissions', () => {
    cy.login('viewer@example.com', 'password123');
    
    cy.visit('/dashboard');
    cy.get('button').contains('Create Payment').should('not.exist');
  });

  it('should handle session expiry', () => {
    cy.login('admin@example.com', 'password123');
    
    // Simulate token expiry
    cy.window().then((win) => {
      win.localStorage.removeItem('access_token');
    });
    
    cy.visit('/payments');
    cy.url().should('include', '/login');
  });
});
```

---

## Deployment Checklist

### Environment Variables

```bash
# .env.production
REACT_APP_API_URL=https://api.yourapp.com/api/v1
REACT_APP_ENV=production
```

### Build Configuration

```json
{
  "scripts": {
    "build": "react-scripts build",
    "build:staging": "REACT_APP_ENV=staging react-scripts build",
    "build:production": "REACT_APP_ENV=production react-scripts build"
  }
}
```

### Pre-Deployment Checks

- [ ] All environment variables configured
- [ ] HTTPS enabled
- [ ] CORS configured correctly
- [ ] Token refresh working
- [ ] Permission checks functional
- [ ] Error handling tested
- [ ] Session management working
- [ ] Activity logging verified
- [ ] All tests passing
- [ ] Security headers configured

### Security Headers

```nginx
# nginx.conf
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-XSS-Protection "1; mode=block" always;
add_header Referrer-Policy "no-referrer-when-downgrade" always;
add_header Content-Security-Policy "default-src 'self' https:; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline';" always;
```

### Monitoring

```typescript
// Setup error tracking (e.g., Sentry)
import * as Sentry from '@sentry/react';

Sentry.init({
  dsn: process.env.REACT_APP_SENTRY_DSN,
  environment: process.env.REACT_APP_ENV,
  beforeSend(event, hint) {
    // Don't send auth tokens
    if (event.request?.headers) {
      delete event.request.headers.Authorization;
    }
    return event;
  },
});
```

---

## Troubleshooting

### Common Issues

#### 1. Token Refresh Loop

**Problem**: Infinite token refresh attempts

**Solution**:
```typescript
// Add retry flag to prevent loops
if (error.response?.status === 401 && !originalRequest._retry) {
  originalRequest._retry = true;
  // ... refresh logic
}
```

#### 2. Permission Check Fails

**Problem**: User has permission but check fails

**Solution**: Verify wildcard matching
```typescript
// Check if wildcard logic is correct
const category = required.split('.')[0];
if (permissions.includes(`${category}.*`)) return true;
```

#### 3. Session Not Found

**Problem**: Session validation fails after login

**Solution**: Ensure session is created before validation
```typescript
// Create session after successful login
const sessionId = await create_session(...);
// Then validate
```

#### 4. CORS Errors

**Problem**: API requests blocked by CORS

**Solution**: Configure backend CORS
```python
# Backend (FastAPI)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://yourfrontend.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## Support and Resources

### API Documentation
- Swagger UI: `https://api.yourapp.com/api/v1/docs`
- ReDoc: `https://api.yourapp.com/api/v1/redoc`

### Backend Logs
- Check activity logs for debugging: `GET /api/v1/team/activity-logs`
- Filter by action, team member, date range

### Contact
- Backend Team: backend@yourapp.com
- Security Issues: security@yourapp.com

---

**Last Updated**: April 12, 2026  
**Version**: 1.0.0  
**Backend API Version**: v1
