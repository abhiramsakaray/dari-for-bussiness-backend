"""
Check database for merchant data
"""
import sqlite3
from datetime import datetime

# Connect to database
conn = sqlite3.connect('payment_gateway.db')
cursor = conn.cursor()

print("=" * 60)
print("DATABASE INSPECTION")
print("=" * 60)

# Get merchant ID from the logs
merchant_id = "27dd5606-f87f-4b93-ad64-33b95646d57f"
print(f"\nChecking data for merchant: {merchant_id}")

# Check if merchant exists
print("\n" + "=" * 60)
print("MERCHANT INFO")
print("=" * 60)
cursor.execute("SELECT id, name, email, created_at FROM merchants WHERE id = ?", (merchant_id,))
merchant = cursor.fetchone()
if merchant:
    print(f"ID: {merchant[0]}")
    print(f"Name: {merchant[1]}")
    print(f"Email: {merchant[2]}")
    print(f"Created: {merchant[3]}")
else:
    print("❌ Merchant not found!")
    print("\nLet me check all merchants:")
    cursor.execute("SELECT id, name, email FROM merchants")
    all_merchants = cursor.fetchall()
    for m in all_merchants:
        print(f"  - {m[0]} | {m[1]} | {m[2]}")

# Check wallets for this merchant
print("\n" + "=" * 60)
print("MERCHANT WALLETS")
print("=" * 60)
cursor.execute("""
    SELECT id, chain, wallet_address, is_active, created_at 
    FROM merchant_wallets 
    WHERE merchant_id = ?
""", (merchant_id,))
wallets = cursor.fetchall()
if wallets:
    print(f"Found {len(wallets)} wallet(s):")
    for w in wallets:
        print(f"  - Chain: {w[1]} | Address: {w[2]} | Active: {w[3]}")
else:
    print("❌ No wallets found!")
    print("\nChecking if merchant_wallets table exists:")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='merchant_wallets'")
    if cursor.fetchone():
        print("✓ Table exists")
        cursor.execute("SELECT COUNT(*) FROM merchant_wallets")
        total = cursor.fetchone()[0]
        print(f"  Total wallets in DB: {total}")
        if total > 0:
            cursor.execute("SELECT DISTINCT merchant_id FROM merchant_wallets LIMIT 5")
            print("  Sample merchant IDs with wallets:")
            for row in cursor.fetchall():
                print(f"    - {row[0]}")
    else:
        print("❌ Table doesn't exist!")

# Check payment sessions
print("\n" + "=" * 60)
print("PAYMENT SESSIONS")
print("=" * 60)
cursor.execute("""
    SELECT id, amount_fiat, fiat_currency, status, created_at, paid_at
    FROM payment_sessions 
    WHERE merchant_id = ?
    ORDER BY created_at DESC
    LIMIT 10
""", (merchant_id,))
payments = cursor.fetchall()
if payments:
    print(f"Found {len(payments)} payment(s) (showing last 10):")
    for p in payments:
        print(f"  - ID: {p[0]} | Amount: {p[1]} {p[2]} | Status: {p[3]} | Created: {p[4]}")
else:
    print("❌ No payment sessions found!")
    print("\nChecking payment_sessions table:")
    cursor.execute("SELECT COUNT(*) FROM payment_sessions")
    total = cursor.fetchone()[0]
    print(f"  Total payments in DB: {total}")
    if total > 0:
        cursor.execute("SELECT DISTINCT merchant_id FROM payment_sessions LIMIT 5")
        print("  Sample merchant IDs with payments:")
        for row in cursor.fetchall():
            print(f"    - {row[0]}")

# Check refunds
print("\n" + "=" * 60)
print("REFUNDS")
print("=" * 60)
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='refunds'")
if cursor.fetchone():
    cursor.execute("""
        SELECT id, amount, status, created_at
        FROM refunds 
        WHERE merchant_id = ?
    """, (merchant_id,))
    refunds = cursor.fetchall()
    if refunds:
        print(f"Found {len(refunds)} refund(s):")
        for r in refunds:
            print(f"  - ID: {r[0]} | Amount: {r[1]} | Status: {r[2]}")
    else:
        print("❌ No refunds found!")
else:
    print("❌ Refunds table doesn't exist!")

print("\n" + "=" * 60)
print("DATABASE TABLES")
print("=" * 60)
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print(f"Found {len(tables)} tables:")
for t in tables:
    cursor.execute(f"SELECT COUNT(*) FROM {t[0]}")
    count = cursor.fetchone()[0]
    print(f"  - {t[0]}: {count} rows")

conn.close()
print("\n" + "=" * 60)
