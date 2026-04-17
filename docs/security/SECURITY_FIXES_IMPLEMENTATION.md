# Security Fixes Implementation Plan

## Status: IN PROGRESS
**Date:** April 16, 2026
**Priority:** CRITICAL - Production Blocker

---

## COMPLETED FIXES ✅

### 1. JWT Secret Validation (CRITICAL #2)
**File:** `app/core/config.py`
- ✅ Added validation to reject weak/default JWT secrets
- ✅ Enforced minimum 32-character length
- ✅ Blocks production deployment with default secrets
- ✅ Warns in development mode

### 2. CORS Wildcard Protection (HIGH #6)
**File:** `app/core/config.py`
- ✅ Blocks wildcard CORS in production
- ✅ Requires explicit origin list
- ✅ Validates at startup

### 3. Admin Password Validation (HIGH #9)
**File:** `app/core/config.py`
- ✅ Rejects weak default passwords
- ✅ Enforces strong password policy
- ✅ Blocks production with defaults

### 4. Password Policy Enforcement (MEDIUM #18)
**File:** `app/routes/auth.py`
- ✅ Minimum 12 characters
- ✅ Requires uppercase, lowercase, digit, special char
- ✅ Applied to registration

### 5. Google OAuth Token Validation (MEDIUM #19)
**File:** `app/routes/auth.py`
- ✅ Always validates audience claim
- ✅ Removed development bypass
- ✅ Enforces client_id check

### 6. Request Body Size Limit (MEDIUM #20)
**File:** `app/main.py`
- ✅ 10MB maximum request size
- ✅ DoS protection middleware
- ✅ Returns 413 for oversized requests

### 7. Foreign Key Enforcement (MEDIUM #21)
**File:** `app/core/database.py`
- ✅ Enabled SQLite foreign key constraints
- ✅ Prevents orphaned records
- ✅ Data integrity protection

### 8. Connection Pooling (MEDIUM #26)
**File:** `app/core/database.py`
- ✅ Pool size: 20 connections
- ✅ Max overflow: 40
- ✅ Pool pre-ping enabled
- ✅ Connection recycling (1 hour)

### 9. Redis Production Requirement (MEDIUM #27)
**File:** `app/core/config.py`
- ✅ Warns if Redis disabled in production
- ✅ Prevents cache stampede issues

### 10. PII Encryption Warning (HIGH #6)
**File:** `app/core/config.py`
- ✅ Warns if PII_ENCRYPTION_KEY not set
- ✅ Provides generation instructions

---

## REMAINING CRITICAL FIXES 🔴

### 1. Race Condition in Refund Processing (CRITICAL #1)
**File:** `app/routes/refunds.py` (Lines 400-450, 768-780)
**Status:** ⚠️ PARTIALLY FIXED - Needs completion
**Issue:** Balance deduction not atomic, allows negative balances

**Current Code (Line 768-780):**
```python
# VULNERABLE: Non-atomic balance check and deduction
balance = _get_merchant_balance(merchant, refund.token)
if available < Decimal(str(refund.amount)):
    raise HTTPException(...)

# Time passes - concurrent request possible!
col = BALANCE_COLUMNS.get(refund.token.upper())
if col:
    current_bal = Decimal(str(getattr(merchant, col, 0) or 0))
    setattr(merchant, col, current_bal - Decimal(str(refund.amount)))
```

**Fix Required:**
```python
# Use atomic SQL UPDATE with WHERE guard
from sqlalchemy import update

col = BALANCE_COLUMNS.get(refund.token.upper())
if col:
    balance_column = getattr(Merchant, col)
    result = db.execute(
        update(Merchant)
        .where(
            Merchant.id == merchant_uuid,
            balance_column >= Decimal(str(refund.amount))
        )
        .values(**{col: balance_column - Decimal(str(refund.amount))})
    )
    if result.rowcount == 0:
        db.rollback()
        raise HTTPException(400, "Insufficient funds (concurrent modification)")
```

### 2. IDOR in Payment Session Access (CRITICAL #4)
**File:** `app/routes/checkout.py` (Line 50)
**Status:** 🔴 NOT FIXED
**Issue:** No merchant ownership verification on checkout page

**Current Code:**
```python
@router.get("/{session_id}", response_class=HTMLResponse)
async def checkout_page(
    request: Request,
    session_id: str,
    db: Session = Depends(get_db)
):
    session = db.query(PaymentSession).filter(
        PaymentSession.id == session_id
    ).first()
    # NO OWNERSHIP CHECK!
```

**Fix Required:**
- Checkout pages are PUBLIC (customers access them)
- But admin/merchant endpoints need protection
- Add merchant verification to `/api/{session_id}` endpoint
- Keep public checkout accessible

### 3. Rate Limiting on Authentication (HIGH #10)
**File:** `app/routes/auth.py`
**Status:** ⚠️ PARTIALLY IMPLEMENTED
**Issue:** Per-email lockout exists, but no IP-based rate limiting

**Current Implementation:**
- Account lockout per email (in security_utils)
- IP tracking added to login endpoint
- Missing: Global rate limiter middleware

**Fix Required:**
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.post("/login")
@limiter.limit("5/minute")  # 5 attempts per minute per IP
async def login_merchant(...):
    ...
```

### 4. Missing Database Indexes (HIGH #12)
**File:** `app/models/models.py`
**Status:** 🔴 NOT FIXED
**Issue:** O(n) table scans on critical queries

**Fix Required:**
```python
class PaymentSession(Base):
    __table_args__ = (
        Index('idx_payment_merchant_status', 'merchant_id', 'status'),
        Index('idx_payment_created_at', 'created_at'),
        Index('idx_payment_merchant_created', 'merchant_id', 'created_at'),
    )

class Refund(Base):
    __table_args__ = (
        Index('idx_refund_merchant_status', 'merchant_id', 'status'),
        Index('idx_refund_payment_session', 'payment_session_id'),
    )
```

### 5. N+1 Query Problem (HIGH #13)
**File:** `app/routes/refunds.py` (Lines 600-650)
**Status:** 🔴 NOT FIXED
**Issue:** 100 refunds = 201 database queries

**Fix Required:**
```python
from sqlalchemy.orm import joinedload

refunds = query.options(
    joinedload(Refund.payment_session),
    joinedload(Refund.merchant)
).order_by(Refund.created_at.desc()).all()
```

### 6. Missing CSRF Protection (MEDIUM #17)
**File:** `app/main.py`
**Status:** 🔴 NOT FIXED
**Issue:** No CSRF tokens for state-changing operations

**Fix Required:**
```python
from fastapi_csrf_protect import CsrfProtect

@app.post("/api/sensitive-operation")
async def operation(csrf_protect: CsrfProtect = Depends()):
    await csrf_protect.validate_csrf(request)
    ...
```

### 7. Session Fixation (MEDIUM #16)
**File:** `app/core/sessions.py`
**Status:** 🔴 NOT FIXED
**Issue:** Session IDs not regenerated after login

**Fix Required:**
- Regenerate session ID after authentication
- Invalidate old session
- Create new session with same data

### 8. Audit Logging (MEDIUM #29)
**File:** Multiple
**Status:** 🔴 NOT FIXED
**Issue:** No immutable audit trail

**Fix Required:**
```python
class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    actor_id = Column(UUID, nullable=False)
    action = Column(String, nullable=False)
    resource_type = Column(String)
    resource_id = Column(String)
    ip_address = Column(String)
    user_agent = Column(String)
    request_id = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
```

### 9. Health Check Improvements (MEDIUM #33)
**File:** `app/main.py`
**Status:** ⚠️ PARTIALLY IMPLEMENTED
**Issue:** Always returns healthy, doesn't check dependencies

**Current Implementation:**
- Database check exists
- Redis check conditional
- Missing: Blockchain RPC checks

**Fix Required:**
```python
@app.get("/health")
async def health_check():
    checks = {
        "database": await check_database(),
        "redis": await check_redis() if settings.REDIS_ENABLED else True,
        "blockchain_rpc": await check_blockchain_rpc(),
    }
    if not all(checks.values()):
        raise HTTPException(503, detail=checks)
    return {"status": "healthy", "checks": checks}
```

### 10. Circuit Breaker Pattern (MEDIUM #32)
**File:** Multiple blockchain service files
**Status:** 🔴 NOT FIXED
**Issue:** No circuit breaker for external service calls

**Fix Required:**
```python
from circuitbreaker import circuit

@circuit(failure_threshold=5, recovery_timeout=60)
async def call_blockchain_rpc(url, method, params):
    ...
```

---

## IMPLEMENTATION PRIORITY

### Phase 1: IMMEDIATE (Today)
1. ✅ JWT Secret Validation
2. ✅ CORS Wildcard Protection
3. ✅ Password Policy
4. ✅ Request Size Limits
5. ✅ Foreign Key Constraints
6. ✅ Connection Pooling
7. 🔴 Fix Refund Race Condition (CRITICAL)
8. 🔴 Add Database Indexes (HIGH)

### Phase 2: THIS WEEK
9. 🔴 Rate Limiting Middleware
10. 🔴 Fix N+1 Queries
11. 🔴 CSRF Protection
12. 🔴 Audit Logging
13. 🔴 Health Check Improvements

### Phase 3: NEXT WEEK
14. 🔴 Session Fixation Fix
15. 🔴 Circuit Breaker Implementation
16. 🔴 PII Encryption (if not already done)
17. 🔴 GDPR Data Deletion

---

## TESTING REQUIREMENTS

### Security Testing
- [ ] Penetration testing for race conditions
- [ ] IDOR testing on all endpoints
- [ ] Rate limit bypass attempts
- [ ] SQL injection testing
- [ ] Authentication bypass testing

### Performance Testing
- [ ] Load testing with indexes
- [ ] Concurrent refund stress test
- [ ] N+1 query verification
- [ ] Connection pool saturation test

### Compliance Testing
- [ ] GDPR compliance audit
- [ ] PCI-DSS assessment
- [ ] Audit log completeness

---

## NOTES

- All CRITICAL fixes must be completed before production deployment
- HIGH priority fixes should be completed within 1 week
- MEDIUM priority fixes within 2 weeks
- Comprehensive testing required after each phase

---

**Last Updated:** April 16, 2026
**Next Review:** April 17, 2026
