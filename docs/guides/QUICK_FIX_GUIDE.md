# Quick Fix Guide - Recurring Payments Not Working

## TL;DR - The Problem

Subscriptions are stuck in `PENDING_PAYMENT` or `PAST_DUE` status and never execute recurring payments.

**Root Cause:** Race condition in first payment + incorrect grace period tracking.

---

## Quick Fix (5 minutes)

### Step 1: Apply Database Migration
```bash
psql -U dariwallettest -d chainpe -f migrations/add_first_failed_at_column.sql
```

### Step 2: Restart Application
```bash
# The code changes are already applied
# Just restart to pick them up
pkill -f "uvicorn app.main:app"
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Step 3: Fix Stuck Subscriptions
```bash
# Preview what will be fixed
python scripts/fix_stuck_subscriptions.py --dry-run

# Apply fixes
python scripts/fix_stuck_subscriptions.py
```

### Step 4: Verify
```bash
# Check scheduler is running
curl http://localhost:8000/health

# Check logs
tail -f dari_payments.log | grep "Scheduler cycle"

# Diagnose subscriptions
python scripts/diagnose_subscriptions.py
```

---

## What Was Fixed

### 1. Timestamp Synchronization
**Before:** DB used `utcnow() + 60s`, contract used `block.timestamp + 5s`  
**After:** DB uses actual on-chain `startTime` from relayer

### 2. Grace Period Tracking
**Before:** Calculated from `next_payment_at` (wrong)  
**After:** Calculated from `first_failed_at` (correct)

### 3. Failure State Management
**Before:** No tracking of when failures started  
**After:** New `first_failed_at` column tracks failure timeline

### 4. First Payment Timing
**Before:** Hardcoded 5s minimum wait  
**After:** Dynamic wait based on actual on-chain timestamp

---

## Verify It's Working

### Check Scheduler Status
```bash
curl http://localhost:8000/api/v1/web3-subscriptions/scheduler/status
```

Expected output:
```json
{
  "is_running": true,
  "interval_seconds": 60,
  "batch_size": 100,
  "total_cycles": 42,
  "total_payments_executed": 15,
  "total_payments_failed": 2,
  "last_run": "2026-03-29T10:30:00"
}
```

### Check Subscription State
```bash
python scripts/diagnose_subscriptions.py --subscription-id <your-sub-id>
```

Expected output:
```
✅ Status matches
✅ Payment count matches
✅ No issues detected
```

### Monitor Logs
```bash
tail -f dari_payments.log | grep -E "Scheduler cycle|Payment.*executed|Payment failed"
```

Expected logs:
```
📋 Scheduler cycle #42: found 3 due subscription(s)
✅ Payment #5 executed for sub abc123 | tx=0x1234...
```

---

## Common Issues After Fix

### Issue: Scheduler Not Running
**Check:**
```bash
grep "subscription scheduler" dari_payments.log
```

**Expected:**
```
✅ Web3 subscription scheduler started (interval=60s, batch=100)
```

**Fix:**
Ensure `WEB3_SUBSCRIPTIONS_ENABLED=true` in `.env`

---

### Issue: No Payments Executing
**Check:**
```bash
python scripts/diagnose_subscriptions.py --status active
```

**Possible Causes:**
1. No subscriptions due yet
2. Relayer out of gas
3. RPC endpoint down

**Fix:**
```bash
# Check relayer balance
curl http://localhost:8000/api/v1/web3-subscriptions/relayer/balance

# Should show > 0.1 ETH/MATIC
```

---

### Issue: High Failure Rate
**Check:**
```bash
python scripts/diagnose_subscriptions.py --status past_due
```

**Possible Causes:**
1. Subscribers out of funds
2. Token allowance not set
3. Gas price too high

**Fix:**
- Notify subscribers to top up
- Check token approvals on block explorer
- Adjust `RELAYER_MAX_GAS_PRICE_GWEI` in `.env`

---

## Testing New Subscriptions

### Create Test Subscription
```bash
curl -X POST http://localhost:8000/api/v1/web3-subscriptions \
  -H "Content-Type: application/json" \
  -d '{
    "signature": "0x...",
    "subscriber_address": "0x...",
    "merchant_id": "...",
    "token_symbol": "USDC",
    "amount": 10,
    "interval": "monthly",
    "chain": "polygon"
  }'
```

### Monitor First Payment
```bash
# Should see within 10 seconds:
tail -f dari_payments.log | grep "First payment"

# Expected:
✅ First payment confirmed for sub abc123 | tx=0x1234... | status→ACTIVE
```

### Verify Status Transition
```bash
python scripts/diagnose_subscriptions.py --subscription-id <new-sub-id>

# Should show:
Status: active
Total Payments: 1
✅ No issues detected
```

---

## Rollback Plan (If Needed)

### Step 1: Stop Application
```bash
pkill -f "uvicorn app.main:app"
```

### Step 2: Revert Database Migration
```bash
psql -U dariwallettest -d chainpe -c "ALTER TABLE web3_subscriptions DROP COLUMN IF EXISTS first_failed_at;"
```

### Step 3: Revert Code Changes
```bash
git checkout HEAD~1 app/services/subscription_scheduler.py
git checkout HEAD~1 app/services/web3_subscription_service.py
git checkout HEAD~1 app/models/models.py
```

### Step 4: Restart
```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

## Production Checklist

- [ ] Database migration applied
- [ ] Application restarted
- [ ] Scheduler running (check logs)
- [ ] Stuck subscriptions fixed
- [ ] Test subscription created and executed
- [ ] Monitoring alerts configured
- [ ] Team notified of changes
- [ ] Documentation updated

---

## Support Commands

```bash
# Check all subscriptions
python scripts/diagnose_subscriptions.py --all

# Check by merchant
python scripts/diagnose_subscriptions.py --merchant-id <uuid>

# Check by status
python scripts/diagnose_subscriptions.py --status pending_payment

# Fix stuck subscriptions (dry run)
python scripts/fix_stuck_subscriptions.py --dry-run

# Fix stuck subscriptions (live)
python scripts/fix_stuck_subscriptions.py

# Monitor scheduler
tail -f dari_payments.log | grep "Scheduler"

# Check relayer balance
curl http://localhost:8000/api/v1/web3-subscriptions/relayer/balance
```

---

## Success Criteria

✅ Scheduler running every 60 seconds  
✅ New subscriptions transition PENDING_PAYMENT → ACTIVE within 1 minute  
✅ Recurring payments execute on schedule  
✅ Failed payments retry every 12 hours  
✅ Grace period calculated correctly  
✅ Subscriptions pause after grace period  
✅ No `PaymentNotDue()` reverts in logs  

---

## Next Steps

1. Monitor for 24 hours
2. Check payment success rate (target: >95%)
3. Verify no new stuck subscriptions
4. Document any edge cases
5. Update monitoring dashboards

---

**Need Help?**
- Check full documentation: `SUBSCRIPTION_FIX_SUMMARY.md`
- Run diagnostics: `python scripts/diagnose_subscriptions.py`
- Review logs: `tail -f dari_payments.log`
