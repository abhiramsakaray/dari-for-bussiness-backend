# Team Permissions Route Issue - RESOLVED ✅

## Error

```
invalid input syntax for type uuid: "permissions"
WHERE merchant_users.id = 'permissions'::UUID
```

## Root Cause

Two issues identified:

1. **Wrong API Endpoint:** Frontend was calling `/api/v1/team/permissions` instead of `/api/v1/team/roles/permissions`
2. **Authentication Issue:** Merchant tokens don't have permission to access team member endpoints (401 Unauthorized)

FastAPI was matching `/api/v1/team/permissions` to the generic `GET /api/v1/team/{member_id}` route, treating "permissions" as a UUID.

## Issues Found

### Issue 1: Wrong Endpoint
- ❌ Frontend called: `GET /api/v1/team/permissions`
- ✅ Correct endpoint: `GET /api/v1/team/roles/permissions`

### Issue 2: Authentication
- `/api/v1/team/roles/permissions` requires team member authentication
- Merchant tokens get 401 Unauthorized
- Frontend needs to handle this gracefully

## Solution Implemented (Frontend)

### 1. Fixed API Endpoint

Updated `useAllPermissions()` hook:

```typescript
// ❌ Before
const { data } = useQuery({
  queryKey: ['permissions'],
  queryFn: () => api.get('/api/v1/team/permissions')
});

// ✅ After
const { data } = useQuery({
  queryKey: ['permissions'],
  queryFn: () => api.get('/api/v1/team/roles/permissions')
});
```

### 2. Added Authentication Check

Prevent fetching when using merchant token:

```typescript
const { data, isLoading, error } = useQuery({
  queryKey: ['permissions'],
  queryFn: () => api.get('/api/v1/team/roles/permissions'),
  enabled: !isMerchant,  // Only fetch for team members
  retry: false,          // Don't retry 401 errors
});
```

### 3. Graceful Error Handling

Added fallback UI in `PermissionManager`:

```typescript
if (isMerchant && error?.response?.status === 401) {
  return (
    <div className="permission-error">
      <p>Permission management requires team member authentication.</p>
      <p>Please log in as a team member to manage permissions.</p>
    </div>
  );
}
```

## Changes Made

### Frontend Files Updated

1. **useAllPermissions() hook**
   - Fixed endpoint: `/api/v1/team/permissions` → `/api/v1/team/roles/permissions`
   - Added `enabled: !isMerchant` to prevent merchant token usage
   - Added `retry: false` to avoid retrying 401 errors

2. **useMemberPermissions() hook**
   - Fetch member details and construct permissions from role
   - Handle merchant token gracefully

3. **PermissionManager component**
   - Added fallback UI for 401 errors
   - Show helpful message when merchant tries to access
   - Prevent UUID parsing errors

## Results

✅ **Fixed:** Correct API endpoint called  
✅ **Fixed:** No more UUID parsing errors  
✅ **Fixed:** Graceful handling of 401 errors  
✅ **Fixed:** Better UX with helpful error messages  
✅ **Fixed:** No retry loops on failed requests  

## Backend Routes (No Changes Needed)

Current backend routes are correct:
- ✅ `GET /api/v1/team/roles/permissions` - List all role permissions (requires team member auth)
- ✅ `GET /api/v1/team/{member_id}` - Get team member details

## Alternative Backend Solution (Optional)

If you want merchants to access role permissions, add this to `app/routes/team.py`:

```python
# Add BEFORE the /{member_id} route to avoid conflicts
@router.get("/permissions")
@router_v1.get("/permissions")
async def get_permissions_alias(
    current_user: dict = Depends(require_merchant)  # Allow merchant auth
):
    """
    Alias for /roles/permissions.
    Allows merchants to view available role permissions.
    """
    return {
        "roles": [
            {
                "role": role.value,
                "permissions": perms,
                "description": get_role_description(role)
            }
            for role, perms in ROLE_PERMISSIONS.items()
        ]
    }
```

This would allow merchants to call `/api/v1/team/permissions` directly.

## Testing

### Test Case 1: Team Member Access
```bash
# With team member token
curl -H "Authorization: Bearer TEAM_MEMBER_TOKEN" \
  http://localhost:8000/api/v1/team/roles/permissions

# Expected: 200 OK with permissions list
```

### Test Case 2: Merchant Access
```bash
# With merchant token
curl -H "Authorization: Bearer MERCHANT_TOKEN" \
  http://localhost:8000/api/v1/team/roles/permissions

# Expected: 401 Unauthorized (handled gracefully in frontend)
```

### Test Case 3: Frontend Behavior
1. Log in as merchant
2. Navigate to Team → Permissions tab
3. Should see: "Permission management requires team member authentication"
4. No UUID parsing errors in console

## Summary

The issue has been resolved with frontend changes:
- Fixed API endpoint path
- Added authentication checks
- Graceful error handling
- Better user experience

No backend changes required, though an optional alias endpoint could improve merchant UX.

---

**Status:** ✅ RESOLVED (Frontend)  
**Priority:** Medium  
**Impact:** Team permissions page now works correctly  
**Related To:** Billing currency fix (unrelated - both issues now resolved)
