# Team RBAC Quick Reference Card

## 🚀 Quick Start

### Login Flow
```typescript
import teamAuthService from './services/teamAuth';

// Login
const response = await teamAuthService.login({
  email: 'user@example.com',
  password: 'password123'
});

// Access token stored automatically
// User info: teamAuthService.getCurrentUser()
```

### Check Permissions
```typescript
import { usePermissions } from './hooks/usePermissions';

const { hasPermission } = usePermissions();

if (hasPermission('payments.create')) {
  // Show create button
}
```

### Protect Routes
```typescript
<ProtectedRoute requiredPermissions={['payments.view']}>
  <PaymentsPage />
</ProtectedRoute>
```

### Conditional Rendering
```typescript
<PermissionGate requiredPermissions={['payments.create']}>
  <button>Create Payment</button>
</PermissionGate>
```

---

## 📡 API Endpoints Cheat Sheet

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/auth/team/login` | Login |
| POST | `/auth/team/logout` | Logout |
| POST | `/auth/team/refresh` | Refresh token |
| GET | `/team/permissions` | List permissions |
| GET | `/team/members/{id}/permissions` | Get member permissions |
| GET | `/team/members/{id}/sessions` | Get active sessions |
| GET | `/team/activity-logs` | Query logs |

---

## 🔑 Permission Codes

### Common Permissions
```
payments.view          # View payments
payments.create        # Create payments
payments.refund        # Process refunds
invoices.view          # View invoices
invoices.create        # Create invoices
team.view              # View team members
team.create            # Add team members
analytics.view         # View analytics
settings.update        # Update settings
```

### Wildcards
```
*                      # All permissions (Owner)
payments.*             # All payment permissions
invoices.*             # All invoice permissions
```

---

## 👥 Roles

| Role | Permissions | Use Case |
|------|-------------|----------|
| Owner | `*` | Full system access |
| Admin | Most resources | Day-to-day management |
| Developer | API/webhooks | Technical integrations |
| Finance | Payments/invoices | Financial operations |
| Viewer | View-only | Read-only access |

---

## 🔒 Security

### Token Expiry
- Access Token: 1 hour
- Refresh Token: 7 days
- Session: 24 hours

### Account Lockout
- 5 attempts → 15 min lock
- 10 attempts → 1 hour lock
- 20 attempts → Admin unlock required

### Password Requirements
- Minimum 8 characters
- 1 uppercase letter
- 1 lowercase letter
- 1 digit
- 1 special character

---

## 🛠️ Common Code Snippets

### Login Component
```typescript
const handleLogin = async (email: string, password: string) => {
  try {
    await teamAuthService.login({ email, password });
    navigate('/dashboard');
  } catch (error) {
    setError(handleApiError(error));
  }
};
```

### Logout
```typescript
const handleLogout = async () => {
  await teamAuthService.logout();
  navigate('/login');
};
```

### Check Multiple Permissions
```typescript
const { hasAnyPermission, hasAllPermissions } = usePermissions();

// Any of these
if (hasAnyPermission(['payments.create', 'invoices.create'])) {
  // Show create menu
}

// All of these
if (hasAllPermissions(['payments.view', 'payments.export'])) {
  // Show export button
}
```

### Fetch with Auth
```typescript
const response = await axios.get('/api/v1/payments', {
  headers: {
    Authorization: `Bearer ${teamAuthService.getAccessToken()}`
  }
});
```

---

## 🐛 Error Handling

### Status Codes
```typescript
401 → Redirect to login
403 → Show "Access Denied"
423 → Show "Account Locked"
400 → Show validation errors
500 → Show "Server Error"
```

### Error Handler
```typescript
import { handleApiError } from './utils/errorHandler';

try {
  await apiCall();
} catch (error) {
  const message = handleApiError(error);
  toast.error(message);
}
```

---

## 📊 Activity Logging

### Logged Actions
```
team.login             # Successful login
team.logout            # Logout
team.login_failed      # Failed login
team.password_reset    # Password reset
team.permission_granted # Permission granted
team.permission_revoked # Permission revoked
team.session_revoked   # Session revoked
```

### Query Logs
```typescript
const logs = await axios.get('/api/v1/team/activity-logs', {
  params: {
    page: 1,
    page_size: 50,
    team_member_id: userId,
    action: 'team.login',
    start_date: '2026-04-01',
    end_date: '2026-04-30'
  }
});
```

---

## 🔄 Session Management

### View Sessions
```typescript
const sessions = await axios.get(
  `/api/v1/team/members/${userId}/sessions`
);
```

### Revoke All Sessions
```typescript
await axios.post(
  `/api/v1/team/members/${userId}/revoke-sessions`
);
```

---

## ✅ Testing

### Mock Login
```typescript
jest.mock('./services/teamAuth');

teamAuthService.login = jest.fn().mockResolvedValue({
  access_token: 'token',
  team_member: { id: '1', role: 'admin' }
});
```

### Test Permission Check
```typescript
const { result } = renderHook(() => usePermissions());

await waitFor(() => {
  expect(result.current.hasPermission('payments.view')).toBe(true);
});
```

---

## 📦 Environment Variables

```bash
REACT_APP_API_URL=http://localhost:8000/api/v1
REACT_APP_ENV=development
```

---

## 🚨 Common Issues

### Token Refresh Loop
```typescript
// Add retry flag
if (error.response?.status === 401 && !originalRequest._retry) {
  originalRequest._retry = true;
  // refresh logic
}
```

### Permission Not Working
```typescript
// Check wildcard matching
const category = required.split('.')[0];
if (permissions.includes(`${category}.*`)) return true;
```

### CORS Error
```python
# Backend: Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True
)
```

---

## 📚 Resources

- **Full Guide**: `TEAM_RBAC_FRONTEND_GUIDE.md`
- **API Docs**: `/api/v1/docs`
- **Implementation Summary**: `TEAM_RBAC_IMPLEMENTATION_SUMMARY.md`

---

**Version**: 1.0.0  
**Last Updated**: April 12, 2026
