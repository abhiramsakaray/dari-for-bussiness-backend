# Team Login Redirect Fix

## Issue
After team member login, the frontend redirects to the home page instead of the dashboard.

## Root Cause
The frontend login handler doesn't distinguish between:
- Merchant owner login (via `/auth/login`) → should go to home/landing
- Team member login (via `/auth/team/login`) → should go to dashboard

## Solution

### Backend Response Structure

The team login endpoint returns:
```json
{
  "access_token": "eyJhbGc...",
  "refresh_token": "eyJhbGc...",
  "token_type": "bearer",
  "expires_in": 3600,
  "team_member": {
    "id": "uuid",
    "email": "user@example.com",
    "name": "User Name",
    "role": "developer",
    "merchant_id": "uuid"
  }
}
```

### Frontend Fix

Update your login handler to check for the `team_member` field and redirect accordingly:

```typescript
// Login handler
const handleTeamLogin = async (email: string, password: string) => {
  try {
    const response = await axios.post('/auth/team/login', {
      email,
      password,
    });

    const { access_token, refresh_token, team_member } = response.data;

    // Store tokens
    localStorage.setItem('access_token', access_token);
    localStorage.setItem('refresh_token', refresh_token);
    
    // Store user info
    localStorage.setItem('user', JSON.stringify(team_member));
    localStorage.setItem('user_type', 'team_member'); // Important!

    // Redirect to dashboard (not home page)
    navigate('/dashboard');
    
  } catch (error) {
    console.error('Login failed:', error);
    // Handle error
  }
};
```

### Unified Login Component

If you have a single login component that handles both merchant and team member login:

```typescript
const handleLogin = async (email: string, password: string, loginType: 'merchant' | 'team') => {
  try {
    const endpoint = loginType === 'team' ? '/auth/team/login' : '/auth/login';
    
    const response = await axios.post(endpoint, {
      email,
      password,
    });

    const { access_token, refresh_token } = response.data;

    // Store tokens
    localStorage.setItem('access_token', access_token);
    localStorage.setItem('refresh_token', refresh_token);
    
    // Store user type and info
    if (loginType === 'team') {
      const { team_member } = response.data;
      localStorage.setItem('user', JSON.stringify(team_member));
      localStorage.setItem('user_type', 'team_member');
      navigate('/dashboard'); // Team members go to dashboard
    } else {
      const { merchant } = response.data;
      localStorage.setItem('user', JSON.stringify(merchant));
      localStorage.setItem('user_type', 'merchant');
      navigate('/'); // Merchants go to home
    }
    
  } catch (error) {
    console.error('Login failed:', error);
  }
};
```

### Auto-Detect User Type from Token

Alternatively, decode the JWT token to determine user type:

```typescript
import jwt_decode from 'jwt-decode';

interface DecodedToken {
  sub: string; // user_id or team_member_id
  role?: string; // Only present for team members
  merchant_id?: string; // Only present for team members
  exp: number;
}

const handleLoginRedirect = (access_token: string) => {
  const decoded = jwt_decode<DecodedToken>(access_token);
  
  // If token has 'role' field, it's a team member
  if (decoded.role) {
    localStorage.setItem('user_type', 'team_member');
    navigate('/dashboard');
  } else {
    localStorage.setItem('user_type', 'merchant');
    navigate('/');
  }
};
```

### Protected Route Component

Update your protected routes to handle both user types:

```typescript
import { Navigate } from 'react-router-dom';

const ProtectedRoute = ({ children }: { children: React.ReactNode }) => {
  const token = localStorage.getItem('access_token');
  const userType = localStorage.getItem('user_type');

  if (!token) {
    return <Navigate to="/login" />;
  }

  // Team members should always be on dashboard routes
  if (userType === 'team_member' && window.location.pathname === '/') {
    return <Navigate to="/dashboard" />;
  }

  return <>{children}</>;
};
```

### Login Page with Tab Selection

If you have a login page with tabs for merchant vs team member:

```typescript
const LoginPage = () => {
  const [loginType, setLoginType] = useState<'merchant' | 'team'>('merchant');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    try {
      const endpoint = loginType === 'team' 
        ? '/auth/team/login' 
        : '/auth/login';
      
      const response = await axios.post(endpoint, { email, password });
      
      // Store tokens
      localStorage.setItem('access_token', response.data.access_token);
      localStorage.setItem('refresh_token', response.data.refresh_token);
      
      // Redirect based on login type
      if (loginType === 'team') {
        localStorage.setItem('user', JSON.stringify(response.data.team_member));
        navigate('/dashboard');
      } else {
        localStorage.setItem('user', JSON.stringify(response.data.merchant));
        navigate('/');
      }
      
    } catch (error) {
      console.error('Login failed:', error);
    }
  };

  return (
    <div>
      <div className="tabs">
        <button 
          className={loginType === 'merchant' ? 'active' : ''}
          onClick={() => setLoginType('merchant')}
        >
          Merchant Login
        </button>
        <button 
          className={loginType === 'team' ? 'active' : ''}
          onClick={() => setLoginType('team')}
        >
          Team Member Login
        </button>
      </div>
      
      <form onSubmit={handleSubmit}>
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="Email"
          required
        />
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Password"
          required
        />
        <button type="submit">
          {loginType === 'team' ? 'Login as Team Member' : 'Login as Merchant'}
        </button>
      </form>
    </div>
  );
};
```

## Summary

The key changes needed:

1. **Detect user type** from the login response or JWT token
2. **Store user type** in localStorage (`'team_member'` or `'merchant'`)
3. **Redirect accordingly**:
   - Team members → `/dashboard`
   - Merchants → `/` (home)
4. **Update protected routes** to enforce correct paths for each user type

## Quick Fix

If you just want a quick fix, add this after successful team login:

```typescript
// After storing tokens from /auth/team/login response
localStorage.setItem('user_type', 'team_member');
window.location.href = '/dashboard'; // Force redirect to dashboard
```
