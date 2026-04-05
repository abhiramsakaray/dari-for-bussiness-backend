# Windows Quick Start Guide - Fix Recurring Payments

## Current Status

✅ Database migration applied  
✅ Code changes applied  
❌ Application not running  
⚠️ 1 subscription stuck in PAST_DUE (overdue by 5+ days)

---

## Quick Fix (3 Steps)

### Step 1: Fix Stuck Subscriptions

Double-click: **`fix_subscriptions.bat`**

This will:
1. Show you what needs to be fixed (dry run)
2. Ask for confirmation
3. Apply the fixes

Expected output:
```
📋 Found 1 subscription(s) stuck in PENDING_PAYMENT > 1h
📋 Found 1 ACTIVE subscription(s) overdue > 1h

🔧 Fix: Set to PAST_DUE (payment overdue)
✅ Fixed 1 subscription(s)
```

---

### Step 2: Start Application with Scheduler

Double-click: **`start_with_scheduler.bat`**

This will:
1. Verify Web3 subscriptions are enabled
2. Start the FastAPI application
3. Automatically start the scheduler

Expected output:
```
✅ Web3 subscriptions enabled
Starting application...
✅ Web3 subscription scheduler started (interval=60s, batch=100)
```

**Keep this window open!** The application runs here.

---

### Step 3: Monitor Scheduler (Optional)

In a NEW PowerShell window, double-click: **`monitor_scheduler.bat`**

This will show:
- Scheduler status
- Payment execution count
- Recent activity

---

## Manual Commands (PowerShell)

If you prefer manual control:

### Check Subscription Status
```powershell
python scripts/diagnose_subscriptions.py
```

### Fix Stuck Subscriptions
```powershell
# Preview changes
python scripts/fix_stuck_subscriptions.py --dry-run

# Apply fixes
python scripts/fix_stuck_subscriptions.py
```

### Start Application
```powershell
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Check Scheduler Status
```powershell
curl http://localhost:8000/api/v1/web3-subscriptions/scheduler/status
```

### View Recent Logs (if log file exists)
```powershell
Get-Content dari_payments.log -Tail 50 | Select-String "Scheduler"
```

---

## Understanding Your Current Subscription

From the diagnostic output:

```
Subscription ID: 3825ca3d-3310-485c-93a3-3a5ab0e32768
Status: past_due
Overdue By: 124.8 hours (5+ days)
Total Payments: 2
Failed Count: 1
On-Chain: Active, Payment Due
```

**What this means:**
- Subscription has successfully executed 2 payments ✅
- Currently overdue by 5+ days ⚠️
- On-chain contract is ready for next payment ✅
- Scheduler needs to process it ⚠️

**Why it's stuck:**
- Grace period (72 hours) exceeded
- Should have been PAUSED but wasn't (old bug)
- Scheduler wasn't running to process it

**What will happen after fix:**
1. Status will be updated correctly
2. Scheduler will pick it up
3. Payment will execute within 60 seconds
4. Status will change to ACTIVE
5. Next payment scheduled for 24 hours later

---

## Verification Steps

### 1. Check Application is Running
```powershell
curl http://localhost:8000/health
```

Expected:
```json
{
  "status": "healthy",
  "version": "2.2.0",
  "network": "testnet"
}
```

### 2. Check Scheduler Status
```powershell
curl http://localhost:8000/api/v1/web3-subscriptions/scheduler/status
```

Expected:
```json
{
  "is_running": true,
  "interval_seconds": 60,
  "total_cycles": 5,
  "total_payments_executed": 1
}
```

### 3. Check Subscription After 2 Minutes
```powershell
python scripts/diagnose_subscriptions.py --subscription-id 3825ca3d-3310-485c-93a3-3a5ab0e32768
```

Expected:
```
Status: active
Total Payments: 3
✅ No issues detected
```

---

## Troubleshooting

### Application Won't Start

**Error:** `Address already in use`
```powershell
# Find process using port 8000
netstat -ano | findstr :8000

# Kill the process (replace PID with actual number)
taskkill /PID <PID> /F
```

**Error:** `Module not found`
```powershell
# Install dependencies
pip install -r requirements.txt
```

---

### Scheduler Not Running

**Check .env file:**
```powershell
findstr "WEB3_SUBSCRIPTIONS_ENABLED" .env
```

Should show:
```
WEB3_SUBSCRIPTIONS_ENABLED=true
```

If not, edit `.env` and add/change this line.

---

### Payment Not Executing

**Check relayer balance:**
```powershell
curl http://localhost:8000/api/v1/web3-subscriptions/relayer/balance
```

Should show balance > 0.1 MATIC on Polygon.

**Check subscriber balance:**
- Go to PolygonScan (testnet): https://amoy.polygonscan.com/
- Search for subscriber address: `0x05e0555a49faea2e16cf4f3520db0e4a774aa4fe`
- Verify USDC balance > 100
- Check token approval for contract: `0xf6dE451A98764a5f08389e72F83AC7594E4e3045`

---

### Still Having Issues?

**Run full diagnostics:**
```powershell
python scripts/diagnose_subscriptions.py --all
```

**Check specific subscription:**
```powershell
python scripts/diagnose_subscriptions.py --subscription-id 3825ca3d-3310-485c-93a3-3a5ab0e32768
```

**Check all past_due:**
```powershell
python scripts/diagnose_subscriptions.py --status past_due
```

---

## Expected Timeline

**T+0 (Now):**
- Run `fix_subscriptions.bat`
- Start application with `start_with_scheduler.bat`

**T+1 minute:**
- Scheduler completes first cycle
- Picks up overdue subscription
- Executes payment on-chain

**T+2 minutes:**
- Payment confirmed
- Status changes to ACTIVE
- Next payment scheduled

**T+24 hours:**
- Next recurring payment executes automatically

---

## Success Indicators

✅ Application starts without errors  
✅ Scheduler log shows: "Web3 subscription scheduler started"  
✅ Scheduler cycles every 60 seconds  
✅ Past_due subscription transitions to ACTIVE  
✅ Payment count increases  
✅ No "PaymentNotDue()" errors in logs  

---

## Next Steps After Fix

1. **Monitor for 24 hours** - Ensure next payment executes
2. **Create test subscription** - Verify new subscriptions work
3. **Set up monitoring** - Use `monitor_scheduler.bat`
4. **Document any issues** - Report edge cases

---

## Quick Reference

| Task | Command |
|------|---------|
| Fix stuck subscriptions | `fix_subscriptions.bat` |
| Start application | `start_with_scheduler.bat` |
| Monitor scheduler | `monitor_scheduler.bat` |
| Check status | `python scripts/diagnose_subscriptions.py` |
| Check scheduler API | `curl http://localhost:8000/api/v1/web3-subscriptions/scheduler/status` |

---

## Support Files Created

- ✅ `fix_subscriptions.bat` - Fix stuck subscriptions
- ✅ `start_with_scheduler.bat` - Start app with scheduler
- ✅ `monitor_scheduler.bat` - Monitor scheduler activity
- ✅ `scripts/diagnose_subscriptions.py` - Diagnostic tool
- ✅ `scripts/fix_stuck_subscriptions.py` - Automated fixer
- ✅ `SUBSCRIPTION_FIX_SUMMARY.md` - Full technical docs
- ✅ `QUICK_FIX_GUIDE.md` - Quick reference guide

---

**Ready to fix?** Double-click `fix_subscriptions.bat` to start! 🚀
