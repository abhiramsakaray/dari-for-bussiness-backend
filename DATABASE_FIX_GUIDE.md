# 🔧 Database Fix Guide - Critical Issues

## ✅ Good News First!

Your migration was **90% successful**! Most tables, indexes, and permissions are now in place.

## ⚠️ 3 Critical Issues to Fix

### Issue 1: Missing 'stellar' in enum
**Error:** `invalid input value for enum blockchainnetwork: "stellar"`  
**Impact:** Cannot create payments on Stellar network  
**Fix:** Add 'stellar' to the enum

### Issue 2: Missing DEFAULT on merchant_subscriptions.id
**Error:** `null value in column "id" violates not-null constraint`  
**Impact:** Cannot create merchant subscriptions  
**Fix:** Add DEFAULT gen_random_uuid()

### Issue 3: Missing DEFAULT on withdrawal_limits.id
**Error:** `null value in column "id" violates not-null constraint`  
**Impact:** Cannot insert withdrawal limits  
**Fix:** Add DEFAULT gen_random_uuid()

---

## 🚀 Quick Fix (1 Command)

Run this on your server:

```bash
psql "postgresql://dariwallettest:Mummydaddy143@localhost:5432/chainpe" -f ~/FIX_DATABASE_ISSUES.sql
```

---

## 📋 Manual Fix (If Needed)

If you prefer to run commands manually:

### Step 1: Connect to Database
```bash
psql "postgresql://dariwallettest:Mummydaddy143@localhost:5432/chainpe"
```

### Step 2: Add 'stellar' to enum
```sql
ALTER TYPE blockchainnetwork ADD VALUE IF NOT EXISTS 'stellar';
```

### Step 3: Fix merchant_subscriptions
```sql
ALTER TABLE merchant_subscriptions 
ALTER COLUMN id SET DEFAULT gen_random_uuid();
```

### Step 4: Fix withdrawal_limits
```sql
ALTER TABLE withdrawal_limits 
ALTER COLUMN id SET DEFAULT gen_random_uuid();
```

### Step 5: Insert missing data
```sql
-- Insert merchant subscriptions for existing merchants
INSERT INTO merchant_subscriptions (
    id, merchant_id, tier, status, transaction_fee_percent,
    monthly_fee, monthly_transaction_limit, api_rate_limit_per_minute,
    max_team_members, max_api_keys, started_at
)
SELECT 
    gen_random_uuid(), id, 'free', 'active', 0.00, 1.50, 1000.00, 2, 5, 1, NOW()
FROM merchants
WHERE id NOT IN (SELECT merchant_id FROM merchant_subscriptions)
ON CONFLICT (merchant_id) DO NOTHING;

-- Insert withdrawal limits
INSERT INTO withdrawal_limits (
    id, tier, daily_limit_usdc, min_withdrawal_usdc, max_withdrawal_usdc,
    fee_percent, fee_fixed_usdc, processing_time_hours, requires_kyc
) VALUES (
    gen_random_uuid(), 'free', 100.00, 5.00, 50.00, 1.00, 1.00, 60, false
)
ON CONFLICT (tier) DO NOTHING;
```

### Step 6: Exit
```sql
\q
```

---

## ✅ Verify Fixes

After running the fix, verify everything is working:

```bash
psql "postgresql://dariwallettest:Mummydaddy143@localhost:5432/chainpe" -c "
SELECT 'merchant_subscriptions' as table_name, COUNT(*) as count 
FROM merchant_subscriptions
UNION ALL
SELECT 'withdrawal_limits', COUNT(*) FROM withdrawal_limits;
"
```

Expected output:
```
       table_name        | count 
-------------------------+-------
 merchant_subscriptions  |     1
 withdrawal_limits       |     1
```

Check enum values:
```bash
psql "postgresql://dariwallettest:Mummydaddy143@localhost:5432/chainpe" -c "
SELECT enumlabel FROM pg_enum 
WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname = 'blockchainnetwork')
ORDER BY enumlabel;
"
```

Should include: `stellar`

---

## 🔄 Restart Backend

After fixing the database, restart your backend:

### If using systemd:
```bash
sudo systemctl restart dari-api
sudo systemctl status dari-api
```

### If using screen/tmux:
```bash
# Find the process
ps aux | grep uvicorn

# Kill it
kill <PID>

# Start again
cd ~/dari-for-bussiness-backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### If using PM2:
```bash
pm2 restart dari-api
pm2 logs dari-api
```

---

## 🧪 Test Your API

After restarting, test the API:

```bash
# Health check
curl http://localhost:8000/docs

# Create a test payment on Stellar (should work now)
curl -X POST http://localhost:8000/payments/create \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": "10.00",
    "currency": "USD",
    "chain": "stellar",
    "token": "USDC"
  }'
```

---

## 📊 What Was Fixed

### ✅ Tables Created (90+ tables)
- merchants, payment_sessions, subscriptions
- refunds, invoices, payment_links
- webhooks, analytics, compliance
- permissions, role_permissions, activity_logs
- And many more...

### ✅ Indexes Created (100+ indexes)
- All performance-critical indexes in place
- Foreign key indexes
- Search indexes

### ✅ Permissions Seeded
- 40 permissions defined
- 5 roles configured (owner, admin, developer, finance, viewer)
- Role-permission mappings complete

### ⚠️ Minor Issues (Safe to Ignore)
- Some "already exists" warnings (expected on existing DB)
- One syntax error in comment block (doesn't affect functionality)
- Duplicate enum creation attempts (handled gracefully)

---

## 🎯 Next Steps

1. ✅ Run the fix script
2. ✅ Restart backend
3. ✅ Test API endpoints
4. ✅ Deploy smart contracts (follow DEPLOY_NOW.md)
5. ✅ Test payment flow end-to-end

---

## 🆘 Troubleshooting

### Backend won't start after fix
```bash
# Check logs
journalctl -u dari-api -n 50

# Or if using screen
screen -r dari-api
```

### Still getting enum errors
```bash
# Verify stellar was added
psql "postgresql://dariwallettest:Mummydaddy143@localhost:5432/chainpe" -c "
SELECT enumlabel FROM pg_enum 
WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname = 'blockchainnetwork');
"
```

### Still getting ID constraint errors
```bash
# Verify defaults were set
psql "postgresql://dariwallettest:Mummydaddy143@localhost:5432/chainpe" -c "
SELECT column_name, column_default 
FROM information_schema.columns 
WHERE table_name IN ('merchant_subscriptions', 'withdrawal_limits') 
AND column_name = 'id';
"
```

---

## ✅ Success Criteria

Your database is ready when:
- [ ] Fix script runs without errors
- [ ] Backend starts successfully
- [ ] API docs accessible at http://localhost:8000/docs
- [ ] Can create payments on all chains (including stellar)
- [ ] No constraint violation errors in logs

---

**Run the fix now:**
```bash
psql "postgresql://dariwallettest:Mummydaddy143@localhost:5432/chainpe" -f ~/FIX_DATABASE_ISSUES.sql
```

Then restart your backend and you're good to go! 🚀
