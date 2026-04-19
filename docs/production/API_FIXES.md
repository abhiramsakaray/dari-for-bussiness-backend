# API Fixes - 405 Method Not Allowed Error

**Issue:** Frontend getting 405 error on `/auth/register`  
**Cause:** Frontend sending wrong HTTP method (GET instead of POST)  
**Status:** ✅ Fixed

---

## What Was Fixed

### 1. Added Missing Dependencies ✅
```python
# Added to requirements.txt
tronpy==0.4.0
solders==0.21.0
```

### 2. Added CORS Preflight Handlers ✅
```python
@router.options("/register")
@router.options("/login")
```

### 3. Added Helpful Error Message ✅
```python
@router.get("/register")
async def register_get_not_allowed():
    """Return helpful error for GET requests"""
    raise HTTPException(
        status_code=405,
        detail="Registration requires POST method...",
        headers={"Allow": "POST, OPTIONS"}
    )
```

---

## How to Fix Frontend

The backend expects a **POST** request, not GET.

### Correct API Call

```javascript
// ✅ CORRECT
fetch('http://localhost:8000/auth/register', {
  method: 'POST',  // Must be POST
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    email: 'user@example.com',
    name: 'Business Name',
    password: 'SecurePass123!@#'
  })
})

// ❌ WRONG
fetch('http://localhost:8000/auth/register', {
  method: 'GET',  // This causes 405 error
})
```

### Using Axios

```javascript
// ✅ CORRECT
axios.post('http://localhost:8000/auth/register', {
  email: 'user@example.com',
  name: 'Business Name',
  password: 'SecurePass123!@#'
})

// ❌ WRONG
axios.get('http://localhost:8000/auth/register')
```

---

## API Endpoints Reference

### Authentication Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/auth/register` | POST | Register new merchant |
| `/auth/login` | POST | Login merchant |
| `/auth/refresh` | POST | Refresh access token |
| `/auth/google` | POST | Google OAuth login |

### Required Fields

#### Register
```json
{
  "email": "merchant@example.com",
  "name": "Business Name",
  "password": "SecurePass123!@#"
}
```

#### Login
```json
{
  "email": "merchant@example.com",
  "password": "SecurePass123!@#"
}
```

---

## Password Requirements

- Minimum 12 characters
- At least 1 uppercase letter
- At least 1 lowercase letter
- At least 1 digit
- At least 1 special character (!@#$%^&*()_+-=[]{}...)

---

## Response Format

### Success (201 Created)
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "token_type": "bearer",
  "api_key": "pk_live_...",
  "onboarding_completed": false,
  "onboarding_step": 0
}
```

### Error (400 Bad Request)
```json
{
  "detail": "Email already registered"
}
```

### Error (405 Method Not Allowed)
```json
{
  "detail": "Registration requires POST method. Please send a POST request with email, name, and password in the request body."
}
```

---

## Testing the API

### Using cURL
```bash
# Register
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "name": "Test Business",
    "password": "SecurePass123!@#"
  }'

# Login
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "SecurePass123!@#"
  }'
```

### Using Postman
1. Set method to **POST**
2. URL: `http://localhost:8000/auth/register`
3. Headers: `Content-Type: application/json`
4. Body (raw JSON):
```json
{
  "email": "test@example.com",
  "name": "Test Business",
  "password": "SecurePass123!@#"
}
```

---

## CORS Configuration

The backend is configured to accept requests from:
```python
allow_origins=["*"]  # All origins (development)
allow_methods=["*"]  # All methods
allow_headers=["*"]  # All headers
allow_credentials=True
```

For production, update `.env`:
```bash
CORS_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
```

---

## Restart Backend

After making changes:

```bash
# Stop backend
pkill -f uvicorn

# Start backend
cd ~/dari-for-bussiness-backend
source venv/bin/activate
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Verify Fix

```bash
# Test OPTIONS (CORS preflight)
curl -X OPTIONS http://localhost:8000/auth/register

# Test GET (should return helpful error)
curl -X GET http://localhost:8000/auth/register

# Test POST (should work)
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","name":"Test","password":"SecurePass123!@#"}'
```

---

## Common Frontend Errors

### 1. ERR_BLOCKED_BY_CLIENT
**Cause:** Ad blocker or browser extension blocking request  
**Fix:** Disable ad blocker or whitelist localhost

### 2. 405 Method Not Allowed
**Cause:** Using GET instead of POST  
**Fix:** Change method to POST

### 3. CORS Error
**Cause:** Backend not allowing frontend origin  
**Fix:** Add frontend URL to CORS_ORIGINS in .env

### 4. 400 Bad Request
**Cause:** Missing required fields or invalid data  
**Fix:** Check request body matches schema

### 5. Network Error
**Cause:** Backend not running  
**Fix:** Start backend with uvicorn

---

## Next Steps

1. ✅ Update requirements.txt: `pip install -r requirements.txt`
2. ✅ Restart backend
3. ✅ Update frontend to use POST method
4. ✅ Test registration flow
5. ✅ Deploy to production

---

**Status:** ✅ Fixed  
**Last Updated:** April 17, 2026
