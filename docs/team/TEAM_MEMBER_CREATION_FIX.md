# Team Member Creation Fix

## Critical Fixes Applied

### Fix 1: 404 Error - Missing API Routes
**Issue:** Frontend was inconsistent in API calls - some used `/team`, others used `/api/v1/team`

**Solution:** Registered all team endpoints with BOTH prefixes for backward compatibility

### Fix 2: 401 Unauthorized - Authentication Mismatch  
**Issue:** The `POST /api/v1/team/members` endpoint required team member authentication (`get_current_team_member`), but merchants logging in for the first time don't have a `MerchantUser` record yet - they only have a `Merchant` record.

**Root Cause:** 
- Merchants authenticate as `Merchant` (owner of the business)
- Team members authenticate as `MerchantUser` (employees/team)
- The create endpoint required `MerchantUser` auth, blocking merchant owners

**Solution:**
Changed `create_team_member` endpoint to accept regular merchant authentication (`require_merchant`) like the invite endpoint does. The endpoint now:
1. Accepts merchant owner authentication
2. Checks if an owner `MerchantUser` exists for permission validation
3. If no owner exists, grants implicit permission (backward compatibility)
4. Creates team members under the merchant's account

### Fix 3: Deleted Members Still Showing in List
**Issue:** When a team member is deleted via `DELETE /team/{member_id}`, they still appear in the `GET /team` list.

**Root Cause:** 
- Team member deletion is a soft delete (sets `is_active = False`)
- The list endpoint was returning ALL members without filtering by `is_active`

**Solution:**
Updated `list_team_members` endpoint to filter out inactive members:
```python
# Only show active members (exclude soft-deleted ones)
query = db.query(MerchantUser).filter(MerchantUser.is_active == True)
```

### Result
All team endpoints now work correctly for both:
- ✅ Merchant owners (first-time setup, no MerchantUser yet)
- ✅ Team members with proper RBAC permissions

---

## Important: Team Member Login

Team members must use the TEAM login endpoint, not the regular merchant login:

### Wrong (will fail with 401):
```bash
POST /auth/login
{
  "email": "payments@dariorganization.com",
  "password": "YourPassword123"
}
```

### Correct (both work):
```bash
# Legacy format
POST /auth/team/login
{
  "email": "payments@dariorganization.com", 
  "password": "YourPassword123"
}

# API v1 format
POST /api/v1/auth/team/login
{
  "email": "payments@dariorganization.com",
  "password": "YourPassword123"
}
```

### Why?
- `/auth/login` is for merchant owners (Merchant table)
- `/auth/team/login` is for team members (MerchantUser table)
- They use different authentication systems and JWT tokens

### All Team Endpoints Now Support Both Formats

After the fix, ALL team-related endpoints work with both URL patterns:

**Authentication:**
- ✅ `POST /auth/team/login` or `POST /api/v1/auth/team/login`
- ✅ `POST /auth/team/logout` or `POST /api/v1/auth/team/logout`
- ✅ `POST /auth/team/refresh` or `POST /api/v1/auth/team/refresh`

**Team Management:**
- ✅ `GET /team` or `GET /api/v1/team` - List members
- ✅ `POST /team/members` or `POST /api/v1/team/members` - Create member
- ✅ `POST /team/invite` or `POST /api/v1/team/invite` - Send invitation

**Permissions:**
- ✅ `GET /team/permissions` or `GET /api/v1/team/permissions`
- ✅ `GET /team/members/{id}/permissions` or `GET /api/v1/team/members/{id}/permissions`

**Activity Logs:**
- ✅ `GET /team/activity-logs` or `GET /api/v1/team/activity-logs`

---

## What Was Fixed

The backend now properly distinguishes between:
1. **Direct Account Creation** (with password) - Shows "Account created successfully!"
2. **Invitation Flow** (no password) - Shows "Invitation sent"

---

## Changes Made

### 1. Updated Response Messages

**Before:**
- Always said "Team member created successfully" regardless of method

**After:**
- With password: "Account created successfully! User can login immediately."
- Without password: "Invitation sent. User must accept invitation to set password."

### 2. Added Validation

The `/team/members` endpoint now **requires** either:
- `auto_generate_password: true` OR
- `password: "YourPassword123!"`

If neither is provided, returns error:
```json
{
  "detail": "Must provide either 'password' or set 'auto_generate_password=true'. Use POST /team/invite for invitation flow."
}
```

### 3. Fixed invite_token Logic

- `invite_token` is now `null` when password is provided
- `invite_token` is only generated when NO password is set

---

## Testing the Fix

### Test 1: Create Account with Auto-Generated Password

**Request:**
```bash
curl -X POST http://localhost:8000/api/v1/team/members \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "name": "Test User",
    "role": "developer",
    "auto_generate_password": true
  }'
```

**Expected Response:**
```json
{
  "id": "uuid",
  "email": "test@example.com",
  "name": "Test User",
  "role": "developer",
  "invite_token": null,
  "temporary_password": "AutoGen123!@#",
  "message": "Account created successfully! User can login immediately."
}
```

✅ **Message says "Account created"**  
✅ **temporary_password is provided**  
✅ **invite_token is null**

---

### Test 2: Create Account with Custom Password

**Request:**
```bash
curl -X POST http://localhost:8000/api/v1/team/members \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test2@example.com",
    "name": "Test User 2",
    "role": "developer",
    "password": "CustomP@ss123"
  }'
```

**Expected Response:**
```json
{
  "id": "uuid",
  "email": "test2@example.com",
  "name": "Test User 2",
  "role": "developer",
  "invite_token": null,
  "temporary_password": null,
  "message": "Account created successfully! User can login immediately."
}
```

✅ **Message says "Account created"**  
✅ **temporary_password is null (admin set it)**  
✅ **invite_token is null**

---

### Test 3: Try to Create Without Password (Should Fail)

**Request:**
```bash
curl -X POST http://localhost:8000/api/v1/team/members \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test3@example.com",
    "name": "Test User 3",
    "role": "developer"
  }'
```

**Expected Response (400 Error):**
```json
{
  "detail": "Must provide either 'password' or set 'auto_generate_password=true'. Use POST /team/invite for invitation flow."
}
```

✅ **Returns error**  
✅ **Tells user to use /team/invite for invitation flow**

---

## Frontend Integration

### Updated API Call

```typescript
const createTeamMember = async (data: {
  email: string;
  name: string;
  role: string;
  autoGenerate?: boolean;
  customPassword?: string;
}) => {
  const payload: any = {
    email: data.email,
    name: data.name,
    role: data.role,
  };

  // IMPORTANT: Must provide one of these
  if (data.autoGenerate) {
    payload.auto_generate_password = true;
  } else if (data.customPassword) {
    payload.password = data.customPassword;
  } else {
    throw new Error('Must provide password or enable auto-generate');
  }

  const response = await axios.post(
    '/api/v1/team/members',
    payload,
    {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    }
  );

  return response.data;
};
```

### Check Response Message

```typescript
const result = await createTeamMember({
  email: 'user@example.com',
  name: 'User Name',
  role: 'developer',
  autoGenerate: true,
});

console.log(result.message);
// Output: "Account created successfully! User can login immediately."

if (result.temporary_password) {
  console.log('Temporary password:', result.temporary_password);
  // Show this to admin to share with user
}
```

---

## Summary

| Scenario | invite_token | temporary_password | Message |
|----------|--------------|-------------------|---------|
| Auto-generate password | `null` | `"AutoGen123!@#"` | "Account created successfully!" |
| Custom password | `null` | `null` | "Account created successfully!" |
| No password (error) | N/A | N/A | Error: "Must provide password..." |

---

## Migration Notes

If you have existing frontend code calling `/team/members`:

1. ✅ **No changes needed** if you're already passing `auto_generate_password: true` or `password`
2. ⚠️ **Update required** if you're calling without password (will now return 400 error)
3. ✅ **Response message** now clearly indicates account was created vs invitation sent

---

## Logs

The backend now logs:
```
Team member created: user@example.com by admin@example.com (password_set=True)
```

This helps distinguish between direct creation and invitation flow in logs.

---

**Fixed in:** `app/routes/team.py`  
**Date:** April 12, 2026  
**Status:** ✅ Complete
