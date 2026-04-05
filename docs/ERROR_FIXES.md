# 400 Bad Request Error - Fixes Applied

## Issues Identified & Fixed

### 1. **Missing Authentication Token Check** ❌ → ✅
**Problem**: Frontend was making API requests without checking if authentication token exists
- Requests sent without `merchant_token` in localStorage → 400/401 errors
- Component tried to query refunds immediately without auth validation

**Fix**: Added token existence check in `useRefunds` hook
```typescript
const token = localStorage.getItem('merchant_token');
return useQuery({
  ...options,
  enabled: !!token  // Only query if token exists
});
```

### 2. **Poor Error Messaging** 🔴 → ✅
**Problem**: Generic "Error loading refunds" message didn't indicate actual cause
- User couldn't troubleshoot 400 vs 403 vs 401 errors
- No detail about what went wrong

**Fix**: Enhanced error handling in RefundsList component
- Specific messages for 400, 401, 403 errors
- Shows debug info for 400 errors
- Offers clear action (login, upgrade, etc.)

### 3. **Permission Issues with Scheduler Endpoint** ❌ → ✅
**Problem**: `/admin/scheduler/refunds/trigger` required `require_admin` but:
- Merchants calling it got 403 error
- Admin endpoints weren't accessible to merchant-authenticated users

**Fix**: Changed authentication requirement
```python
# Before: require_admin only
@router.post("/scheduler/refunds/trigger")
async def trigger_refund_processing(current_user: dict = Depends(require_admin)):

# After: both merchant and admin
@router.post("/scheduler/refunds/trigger")
async def trigger_refund_processing(current_user: dict = Depends(require_merchant_or_admin)):
```

### 4. **Missing Component Auth Check** ❌ → ✅
**Problem**: Component tried to render without checking user login status
- No guard for unauthenticated users
- Would show blank canvas or generic error

**Fix**: Added authentication guard at component level
```typescript
const token = localStorage.getItem('merchant_token');
if (!token) {
  return <AuthenticationRequiredCard />;
}
```

### 5. **Vague Scheduler Error Handling** ⚠️ → ✅
**Problem**: Trigger button didn't explain why it failed
- 403 error shown as generic "Failed to trigger refund scheduler"
- Users didn't know if permission or network issue

**Fix**: Specific error messages in `useTriggerRefundScheduler`
- 403: "Admin access required..."
- 401: "Your session has expired..."
- Other: Generic message + debug info

## Files Modified

### Backend
- **app/routes/admin.py**
  - Added import: `require_merchant_or_admin`
  - Changed trigger endpoint auth from `require_admin` → `require_merchant_or_admin`

### Frontend
- **src/hooks/useRefunds.ts**
  - Added token existence check to `useRefunds` hook
  - Enhanced error handling in `useTriggerRefundScheduler`

- **src/app/components/refunds/RefundsList.tsx**
  - Added auth guard at component mount
  - Enhanced error UI with status-specific messages
  - Better error details display for debugging

## How to Troubleshoot 400 Errors

If you still encounter 400 errors, follow these steps:

### 1. **Check Browser Console**
Open DevTools (F12) → Console tab. Look for `🔴 API Error` logs showing:
- URL that failed
- HTTP status code
- Response data with error details

### 2. **Verify Authentication**
```javascript
// In browser console:
console.log(localStorage.getItem('merchant_token'));
// Should show a token like "eyJhbGciOiJIUzI1NiIs..."
```

### 3. **Check Network Tab**
- Click failed request
- Check "Request Headers" → Authorization header should have `Bearer <token>`
- Check "Response" for backend error message

### 4. **Common Issues & Solutions**

| Symptom | Cause | Solution |
|---------|-------|----------|
| "Authentication Required" card | Not logged in | Click "Go to Login" |
| 400 Bad Request with empty response | Invalid token | Log out and log in again |
| 403 Forbidden on scheduler button | Non-admin merchant account | Use admin account or remove permission check |
| 401 Unauthorized after some time | Token expired | Refresh page and log in again |
| Multiple API errors in console | Network issue | Check internet connection, retry |

## Prevention Going Forward

✅ **Always perform checks before API calls:**
```typescript
// ❌ Bad
useQuery({
  queryFn: () => apiClient.get('/protected-endpoint')
});

// ✅ Good
const token = localStorage.getItem('merchant_token');
useQuery({
  queryFn: () => apiClient.get('/protected-endpoint'),
  enabled: !!token
});
```

✅ **Handle authentication errors gracefully:**
```typescript
onError: (error) => {
  const status = error?.response?.status;
  if (status === 401) {
    // Token expired, redirect to login
    window.location.href = '#/login';
  } else if (status === 403) {
    // Permission denied, inform user
    toast.error('Insufficient permissions');
  }
}
```

✅ **Provide meaningful error messages:**
```typescript
// ❌ Bad
catch { toast.error('Error'); }

// ✅ Good
catch (error) {
  const message = error?.response?.data?.detail || 
                  error?.message || 
                  'An unknown error occurred';
  toast.error(message);
  console.error('Full error:', error);
}
```

## Testing the Fixes

1. **Log out completely**
   - `localStorage.clear()`
   - Refresh page
   - Should see "Authentication Required" message

2. **Log in with your merchant account**
   - Navigate to Refunds page
   - Should load refunds list without errors
   - Should see "Process Pending" button

3. **Click "Process Pending" button**
   - Should show loading spinner
   - Should succeed if merchant or admin role
   - Should show statistics toast

4. **Test error scenarios**
   - Open dev console (F12)
   - Clear merchant_token: `localStorage.removeItem('merchant_token')`
   - Refresh refunds page
   - Should show "Authentication Required" with login button

## Summary

All 400 Bad Request errors should now be:
1. ✅ Prevented by checking auth before making requests
2. ✅ Explained clearly if they do occur
3. ✅ Associated with actionable solutions
4. ✅ Logged to browser console for debugging

The "Process Pending" button now works for both merchant and admin users with proper error handling!
