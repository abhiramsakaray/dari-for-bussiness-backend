# Team Member Onboarding Guide

## Two Ways to Add Team Members

Your system supports two methods for adding team members:

### Method 1: Invitation Flow (Email-Based)
User receives an email invitation and sets their own password.

### Method 2: Direct Account Creation (Admin-Created)
Admin creates the account with a password immediately.

---

## Method 1: Invitation Flow

### Step 1: Admin Sends Invitation

**Endpoint**: `POST /api/v1/team/invite`

**Request**:
```json
{
  "email": "newmember@example.com",
  "name": "John Doe",
  "role": "developer"
}
```

**Response**:
```json
{
  "id": "uuid",
  "email": "newmember@example.com",
  "name": "John Doe",
  "role": "developer",
  "is_active": true,
  "invite_pending": true,
  "invite_token": "secure_token_here"
}
```

### Step 2: User Receives Email

The user receives an email with:
- Invitation link: `https://yourapp.com/accept-invite?token=secure_token_here`
- Link expires in 7 days

### Step 3: User Accepts Invitation

**Frontend Page**: `/accept-invite?token=...`

User fills out form:
- Password (required)
- Confirm password
- Name (optional, can update)

**Endpoint**: `POST /api/v1/team/accept-invite`

**Request**:
```json
{
  "token": "secure_token_from_url",
  "password": "SecureP@ss123",
  "name": "John Doe"
}
```

**Response**:
```json
{
  "message": "Account created successfully",
  "email": "newmember@example.com"
}
```

### Step 4: User Logs In

User can now login at `/login` with:
- Email: `newmember@example.com`
- Password: `SecureP@ss123`

---

## Method 2: Direct Account Creation

### Admin Creates Account with Password

**Endpoint**: `POST /api/v1/team/members`

**Headers**: `Authorization: Bearer <admin_token>`

**Option A: Auto-Generate Password**
```json
{
  "email": "newmember@example.com",
  "name": "John Doe",
  "role": "developer",
  "auto_generate_password": true
}
```

**Response**:
```json
{
  "id": "uuid",
  "email": "newmember@example.com",
  "name": "John Doe",
  "role": "developer",
  "temporary_password": "AutoGen123!@#",
  "message": "Team member created successfully"
}
```

**Option B: Set Custom Password**
```json
{
  "email": "newmember@example.com",
  "name": "John Doe",
  "role": "developer",
  "password": "CustomP@ss123"
}
```

**Response**:
```json
{
  "id": "uuid",
  "email": "newmember@example.com",
  "name": "John Doe",
  "role": "developer",
  "message": "Team member created successfully"
}
```

### User Can Login Immediately

No invitation acceptance needed! User logs in with:
- Email: `newmember@example.com`
- Password: `AutoGen123!@#` or `CustomP@ss123`

---

## Frontend Implementation

### 1. Admin Dashboard - Add Team Member Form

```typescript
import React, { useState } from 'react';
import axios from 'axios';

export const AddTeamMemberForm: React.FC = () => {
  const [method, setMethod] = useState<'invite' | 'direct'>('direct');
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [role, setRole] = useState('developer');
  const [autoGenerate, setAutoGenerate] = useState(true);
  const [customPassword, setCustomPassword] = useState('');
  const [result, setResult] = useState<any>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    try {
      if (method === 'invite') {
        // Method 1: Send invitation
        const response = await axios.post('/api/v1/team/invite', {
          email,
          name,
          role,
        });
        setResult({
          success: true,
          message: `Invitation sent to ${email}`,
          data: response.data,
        });
      } else {
        // Method 2: Create account directly
        const payload: any = {
          email,
          name,
          role,
        };

        if (autoGenerate) {
          payload.auto_generate_password = true;
        } else {
          payload.password = customPassword;
        }

        const response = await axios.post('/api/v1/team/members', payload, {
          headers: {
            Authorization: `Bearer ${localStorage.getItem('access_token')}`,
          },
        });

        setResult({
          success: true,
          message: 'Account created successfully',
          data: response.data,
        });
      }
    } catch (error: any) {
      setResult({
        success: false,
        message: error.response?.data?.detail || 'Failed to add team member',
      });
    }
  };

  return (
    <div className="add-team-member-form">
      <h2>Add Team Member</h2>

      {/* Method Selection */}
      <div className="method-selection">
        <label>
          <input
            type="radio"
            value="direct"
            checked={method === 'direct'}
            onChange={(e) => setMethod('direct')}
          />
          Create Account Directly (Recommended)
        </label>
        <label>
          <input
            type="radio"
            value="invite"
            checked={method === 'invite'}
            onChange={(e) => setMethod('invite')}
          />
          Send Email Invitation
        </label>
      </div>

      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label>Email</label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>

        <div className="form-group">
          <label>Name</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
        </div>

        <div className="form-group">
          <label>Role</label>
          <select value={role} onChange={(e) => setRole(e.target.value)}>
            <option value="admin">Admin</option>
            <option value="developer">Developer</option>
            <option value="finance">Finance</option>
            <option value="viewer">Viewer</option>
          </select>
        </div>

        {method === 'direct' && (
          <>
            <div className="form-group">
              <label>
                <input
                  type="checkbox"
                  checked={autoGenerate}
                  onChange={(e) => setAutoGenerate(e.target.checked)}
                />
                Auto-generate secure password
              </label>
            </div>

            {!autoGenerate && (
              <div className="form-group">
                <label>Password</label>
                <input
                  type="password"
                  value={customPassword}
                  onChange={(e) => setCustomPassword(e.target.value)}
                  required={!autoGenerate}
                  placeholder="Min 8 chars, uppercase, lowercase, number, special"
                />
              </div>
            )}
          </>
        )}

        <button type="submit">
          {method === 'invite' ? 'Send Invitation' : 'Create Account'}
        </button>
      </form>

      {result && (
        <div className={`result ${result.success ? 'success' : 'error'}`}>
          <p>{result.message}</p>
          {result.success && result.data?.temporary_password && (
            <div className="temporary-password">
              <strong>Temporary Password:</strong>
              <code>{result.data.temporary_password}</code>
              <p className="warning">
                ⚠️ Save this password! Share it securely with the team member.
              </p>
            </div>
          )}
          {result.success && result.data?.invite_token && (
            <div className="invite-info">
              <p>✅ Invitation email sent to {result.data.email}</p>
              <p>The invitation expires in 7 days.</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
```

### 2. Accept Invitation Page

```typescript
import React, { useState, useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import axios from 'axios';

export const AcceptInvitePage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const token = searchParams.get('token');

  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [name, setName] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  if (!token) {
    return <div>Invalid invitation link</div>;
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (password !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }

    if (password.length < 8) {
      setError('Password must be at least 8 characters');
      return;
    }

    setLoading(true);

    try {
      await axios.post('/api/v1/team/accept-invite', {
        token,
        password,
        name: name || undefined,
      });

      alert('Account created successfully! You can now log in.');
      navigate('/login');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to accept invitation');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="accept-invite-page">
      <h2>Accept Team Invitation</h2>
      <p>Set up your account to join the team.</p>

      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label>Name (Optional)</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Your full name"
          />
        </div>

        <div className="form-group">
          <label>Password</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            placeholder="Min 8 characters"
          />
        </div>

        <div className="form-group">
          <label>Confirm Password</label>
          <input
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            required
          />
        </div>

        {error && <div className="error-message">{error}</div>}

        <button type="submit" disabled={loading}>
          {loading ? 'Creating Account...' : 'Create Account'}
        </button>
      </form>
    </div>
  );
};
```

---

## Comparison: Which Method to Use?

| Feature | Invitation Flow | Direct Creation |
|---------|----------------|-----------------|
| **Setup Time** | Slower (user must accept) | Instant |
| **User Control** | User sets own password | Admin sets password |
| **Security** | More secure (user-chosen) | Less secure (shared password) |
| **Best For** | External team members | Internal team, urgent access |
| **Email Required** | Yes | No |
| **Expiry** | 7 days | No expiry |

### Recommendations

**Use Invitation Flow When:**
- Adding external contractors or consultants
- User should choose their own password
- Not urgent (can wait for user to accept)
- Email system is configured

**Use Direct Creation When:**
- Adding internal team members
- Need immediate access
- Admin wants full control
- Email system not configured
- Urgent onboarding needed

---

## Security Best Practices

### For Invitation Flow
1. ✅ Tokens expire in 7 days
2. ✅ One-time use (cleared after acceptance)
3. ✅ User chooses their own password
4. ✅ Send invitation link via secure email

### For Direct Creation
1. ⚠️ Share temporary password securely (not via email)
2. ✅ Use auto-generate for strong passwords
3. ✅ Force password change on first login (optional)
4. ✅ Revoke temporary password after first use (optional)

### Password Requirements (Both Methods)
- Minimum 8 characters
- At least 1 uppercase letter
- At least 1 lowercase letter
- At least 1 digit
- At least 1 special character

---

## Resending Invitations

If an invitation expires or is lost:

**Endpoint**: `POST /api/v1/team/{member_id}/resend-invite`

```typescript
const resendInvite = async (memberId: string) => {
  await axios.post(`/api/v1/team/${memberId}/resend-invite`, {}, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
  alert('Invitation resent!');
};
```

---

## Troubleshooting

### Issue: "Invitation has expired"
**Solution**: Admin resends invitation via `/team/{member_id}/resend-invite`

### Issue: "Invitation has already been accepted"
**Solution**: User should login directly, not accept invitation again

### Issue: "Invalid invitation token"
**Solution**: Check URL is correct, or request new invitation

### Issue: "User is already a team member"
**Solution**: User already exists, use login instead

### Issue: "Password too weak"
**Solution**: Ensure password meets all requirements

---

## Complete Flow Diagram

```
INVITATION FLOW:
Admin → Send Invite → Email Sent → User Clicks Link → 
User Sets Password → Account Created → User Logs In

DIRECT CREATION FLOW:
Admin → Create Account → Password Generated/Set → 
Admin Shares Password → User Logs In
```

---

## API Summary

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| `/team/invite` | POST | Merchant | Send invitation |
| `/team/accept-invite` | POST | None | Accept invitation |
| `/team/members` | POST | Team Member | Create account directly |
| `/team/{id}/resend-invite` | POST | Merchant | Resend invitation |

---

**Last Updated**: April 12, 2026  
**Version**: 1.0.0
