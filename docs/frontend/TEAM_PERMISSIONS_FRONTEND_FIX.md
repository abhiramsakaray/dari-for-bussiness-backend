# Team Permissions Frontend Fix

## Issue

The Permissions tab shows an error message saying "Permission Management Unavailable" even when logged in as a merchant (Owner), who should have full access to manage team permissions.

## Root Cause

The frontend is incorrectly checking authentication type and blocking merchants from accessing permission management features. Merchants (especially Owners) should be able to:
- View all role permissions
- Manage team member permissions
- Assign roles to team members

## Solution

### 1. Update Permission Check Logic

The issue is in the permission management component that's checking `isMerchant` and blocking access. Merchants should have access to team management features.

**File: `src/components/team/PermissionManager.tsx` (or similar)**

#### Current Code (WRONG):
```typescript
// ❌ This blocks merchants from managing permissions
if (isMerchant && error?.response?.status === 401) {
  return (
    <div className="permission-error">
      <p>⚠️ Permission Management Unavailable</p>
      <p>Permission management is only available when logged in as a team member...</p>
    </div>
  );
}
```

#### Fixed Code (CORRECT):
```typescript
// ✅ Allow merchants (especially Owners) to manage permissions
// Only show error if there's an actual permission denial
if (error?.response?.status === 403) {
  return (
    <div className="permission-error">
      <p>⚠️ Access Denied</p>
      <p>You don't have permission to manage team permissions.</p>
      <p>Contact your account owner for access.</p>
    </div>
  );
}

// Handle 401 (authentication) errors
if (error?.response?.status === 401) {
  return (
    <div className="permission-error">
      <p>⚠️ Authentication Required</p>
      <p>Please log in to manage permissions.</p>
    </div>
  );
}
```

### 2. Fix API Hook Configuration

**File: `src/hooks/usePermissions.ts` (or similar)**

#### Current Code (WRONG):
```typescript
// ❌ This prevents merchants from fetching permissions
const { data, isLoading, error } = useQuery({
  queryKey: ['permissions'],
  queryFn: () => api.get('/api/v1/team/roles/permissions'),
  enabled: !isMerchant,  // ❌ WRONG - blocks merchants
  retry: false,
});
```

#### Fixed Code (CORRECT):
```typescript
// ✅ Allow both merchants and team members to fetch permissions
const { data, isLoading, error } = useQuery({
  queryKey: ['permissions'],
  queryFn: () => api.get('/api/v1/team/roles/permissions'),
  enabled: true,  // ✅ Allow all authenticated users
  retry: false,
});
```

### 3. Update Permission Management UI

**File: `src/components/team/PermissionManager.tsx`**

```typescript
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';

export function PermissionManager() {
  // Fetch role permissions
  const { data: permissions, isLoading, error } = useQuery({
    queryKey: ['team', 'roles', 'permissions'],
    queryFn: async () => {
      const response = await api.get('/api/v1/team/roles/permissions');
      return response.data;
    },
    retry: false,
  });

  // Handle loading state
  if (isLoading) {
    return <div className="loading">Loading permissions...</div>;
  }

  // Handle errors
  if (error) {
    const status = error.response?.status;
    
    if (status === 403) {
      return (
        <div className="error-state">
          <h3>⚠️ Access Denied</h3>
          <p>You don't have permission to manage team permissions.</p>
          <p>Contact your account owner for access.</p>
        </div>
      );
    }
    
    if (status === 401) {
      return (
        <div className="error-state">
          <h3>⚠️ Authentication Required</h3>
          <p>Please log in to manage permissions.</p>
        </div>
      );
    }
    
    return (
      <div className="error-state">
        <h3>⚠️ Error Loading Permissions</h3>
        <p>Failed to load permission data. Please try again.</p>
        <button onClick={() => window.location.reload()}>Retry</button>
      </div>
    );
  }

  // Render permissions UI
  return (
    <div className="permission-manager">
      <h2>Role Permissions</h2>
      
      {permissions?.roles?.map((role) => (
        <div key={role.role} className="role-card">
          <h3>{role.role}</h3>
          <p>{role.description}</p>
          
          <div className="permissions-list">
            <h4>Permissions:</h4>
            <ul>
              {role.permissions.map((perm) => (
                <li key={perm}>
                  <span className="permission-badge">{perm}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      ))}
    </div>
  );
}
```

### 4. Remove Merchant Blocking Logic

Search your codebase for these patterns and remove them:

```typescript
// ❌ REMOVE these checks
if (isMerchant) {
  return <ErrorMessage />;
}

if (userType === 'merchant') {
  return <AccessDenied />;
}

enabled: !isMerchant  // ❌ REMOVE this
```

Replace with proper permission checks:

```typescript
// ✅ Use proper permission checks instead
if (!hasPermission('team.manage')) {
  return <AccessDenied />;
}

// ✅ Or check user role
if (userRole !== 'owner' && userRole !== 'admin') {
  return <AccessDenied />;
}
```

## Backend API Endpoint

The backend endpoint is correct and accessible to merchants:

```
GET /api/v1/team/roles/permissions
```

**Response:**
```json
{
  "roles": [
    {
      "role": "owner",
      "permissions": ["all:read", "all:write", "team:manage", "settings:manage", "billing:manage"],
      "description": "Full access to everything"
    },
    {
      "role": "admin",
      "permissions": ["all:read", "all:write", "team:manage", "settings:read"],
      "description": "Full access except billing"
    },
    {
      "role": "developer",
      "permissions": ["payments:read", "payments:write", "webhooks:manage", "api_keys:manage", "analytics:read"],
      "description": "API, webhooks, payments"
    },
    {
      "role": "finance",
      "permissions": ["payments:read", "invoices:read", "invoices:write", "analytics:read", "refunds:read", "refunds:write", "subscriptions:read"],
      "description": "Invoices, refunds, analytics"
    },
    {
      "role": "viewer",
      "permissions": ["payments:read", "invoices:read", "analytics:read"],
      "description": "Read-only access"
    }
  ]
}
```

## Testing

### Test Case 1: Merchant Access
1. Log in as merchant (Owner)
2. Navigate to Team → Permissions tab
3. Should see: List of all roles and their permissions
4. Should NOT see: "Permission Management Unavailable" error

### Test Case 2: Admin Access
1. Log in as team member with Admin role
2. Navigate to Team → Permissions tab
3. Should see: List of all roles and their permissions

### Test Case 3: Viewer Access
1. Log in as team member with Viewer role
2. Navigate to Team → Permissions tab
3. Should see: "Access Denied" message (403 error)

## Files to Update

1. **Permission Manager Component**
   - Remove `isMerchant` checks
   - Update error handling
   - Allow all authenticated users

2. **Permission Hooks**
   - Remove `enabled: !isMerchant`
   - Update API endpoint to `/api/v1/team/roles/permissions`
   - Add proper error handling

3. **Team Management Page**
   - Remove merchant blocking logic
   - Use role-based access control instead

## Quick Fix Checklist

- [ ] Remove all `if (isMerchant)` blocks that prevent access
- [ ] Update API endpoint to `/api/v1/team/roles/permissions`
- [ ] Remove `enabled: !isMerchant` from useQuery
- [ ] Update error handling to check 403 (not merchant type)
- [ ] Test with merchant account
- [ ] Test with admin account
- [ ] Test with viewer account

## Summary

The issue is that the frontend is incorrectly blocking merchants from accessing permission management. Merchants (especially Owners) should have full access to manage team permissions. The fix is to:

1. Remove merchant-type checks
2. Use proper permission-based access control
3. Allow API calls for all authenticated users
4. Handle 403 errors for insufficient permissions

---

**Status:** Ready to implement  
**Priority:** HIGH  
**Impact:** Merchants cannot manage team permissions  
**Estimated Time:** 15-30 minutes
