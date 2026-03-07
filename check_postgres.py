"""
Check PostgreSQL database for merchant data
"""
import psycopg2
from psycopg2.extras import RealDictCursor

# Connect to PostgreSQL database
try:
    conn = psycopg2.connect(
        host="localhost",
        port=5432,
        database="chainpe",
        user="dariwallettest",
        password="Mummydaddy143"
    )
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    print("=" * 60)
    print("POSTGRESQL DATABASE INSPECTION")
    print("=" * 60)
    
    # Get merchant ID from the logs
    merchant_id = "27dd5606-f87f-4b93-ad64-33b95646d57f"
    print(f"\nChecking data for merchant: {merchant_id}")
    
    # Check if merchant exists
    print("\n" + "=" * 60)
    print("MERCHANT INFO")
    print("=" * 60)
    cursor.execute("SELECT id, name, email, created_at FROM merchants WHERE id = %s", (merchant_id,))
    merchant = cursor.fetchone()
    if merchant:
        print(f"✓ Merchant found:")
        print(f"  ID: {merchant['id']}")
        print(f"  Name: {merchant['name']}")
        print(f"  Email: {merchant['email']}")
        print(f"  Created: {merchant['created_at']}")
    else:
        print("❌ Merchant not found!")
        print("\nLet me check all merchants:")
        cursor.execute("SELECT id, name, email FROM merchants ORDER BY created_at DESC LIMIT 5")
        all_merchants = cursor.fetchall()
        print(f"Found {len(all_merchants)} recent merchants:")
        for m in all_merchants:
            print(f"  - {m['id']} | {m['name']} | {m['email']}")
    
    # Check wallets for this merchant
    print("\n" + "=" * 60)
    print("MERCHANT WALLETS")
    print("=" * 60)
    cursor.execute("""
        SELECT id, chain, wallet_address, is_active, created_at 
        FROM merchant_wallets 
        WHERE merchant_id = %s
    """, (merchant_id,))
    wallets = cursor.fetchall()
    if wallets:
        print(f"✓ Found {len(wallets)} wallet(s):")
        for w in wallets:
            print(f"  - Chain: {w['chain']} | Address: {w['wallet_address']} | Active: {w['is_active']}")
    else:
        print("❌ No wallets found for this merchant!")
        cursor.execute("SELECT COUNT(*) as count FROM merchant_wallets")
        total = cursor.fetchone()['count']
        print(f"  Total wallets in DB: {total}")
        if total > 0:
            cursor.execute("SELECT DISTINCT merchant_id FROM merchant_wallets LIMIT 5")
            print("  Sample merchant IDs with wallets:")
            for row in cursor.fetchall():
                print(f"    - {row['merchant_id']}")
    
    # Check payment sessions
    print("\n" + "=" * 60)
    print("PAYMENT SESSIONS")
    print("=" * 60)
    cursor.execute("""
        SELECT id, amount_fiat, fiat_currency, status, created_at, paid_at
        FROM payment_sessions 
        WHERE merchant_id = %s
        ORDER BY created_at DESC
        LIMIT 10
    """, (merchant_id,))
    payments = cursor.fetchall()
    if payments:
        print(f"✓ Found {len(payments)} payment(s) (showing last 10):")
        for p in payments:
            print(f"  - ID: {p['id']} | Amount: {p['amount_fiat']} {p['fiat_currency']} | Status: {p['status']}")
    else:
        print("❌ No payment sessions found for this merchant!")
        cursor.execute("SELECT COUNT(*) as count FROM payment_sessions")
        total = cursor.fetchone()['count']
        print(f"  Total payments in DB: {total}")
        if total > 0:
            cursor.execute("SELECT DISTINCT merchant_id FROM payment_sessions LIMIT 5")
            print("  Sample merchant IDs with payments:")
            for row in cursor.fetchall():
                print(f"    - {row['merchant_id']}")
    
    # Check refunds
    print("\n" + "=" * 60)
    print("REFUNDS")
    print("=" * 60)
    try:
        cursor.execute("""
            SELECT id, amount, status, created_at
            FROM refunds 
            WHERE merchant_id = %s
        """, (merchant_id,))
        refunds = cursor.fetchall()
        if refunds:
            print(f"✓ Found {len(refunds)} refund(s):")
            for r in refunds:
                print(f"  - ID: {r['id']} | Amount: {r['amount']} | Status: {r['status']}")
        else:
            print("❌ No refunds found for this merchant!")
    except psycopg2.errors.UndefinedTable:
        print("❌ Refunds table doesn't exist!")
    
    print("\n" + "=" * 60)
    print("DATABASE TABLES")
    print("=" * 60)
    cursor.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public'
        ORDER BY table_name
    """)
    tables = cursor.fetchall()
    print(f"Found {len(tables)} tables:")
    for t in tables:
        cursor.execute(f"SELECT COUNT(*) as count FROM {t['table_name']}")
        count = cursor.fetchone()['count']
        print(f"  - {t['table_name']}: {count} rows")
    
    cursor.close()
    conn.close()
    print("\n" + "=" * 60)
    
except psycopg2.Error as e:
    print(f"❌ Database connection error: {e}")
except Exception as e:
    print(f"❌ Error: {e}")
