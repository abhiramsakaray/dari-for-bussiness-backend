"""
Create test wallets and payment for the current merchant
"""
import psycopg2
from psycopg2.extras import RealDictCursor
import uuid
from datetime import datetime

merchant_id = "27dd5606-f87f-4b93-ad64-33b95646d57f"  # abhiram@dariorganization.com

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
    print("CREATING TEST DATA")
    print("=" * 60)
    
    # Create wallets for different chains
    wallets = [
        ("STELLAR", "GBXYZ123STELLAR456WALLET789ADDRESS"),
        ("ETHEREUM", "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb"),
        ("POLYGON", "0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063"),
        ("BASE", "0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb"),
        ("TRON", "TRXAbc123456789Wallet0123456789"),
    ]
    
    print("\n📝 Creating wallets...")
    for chain, address in wallets:
        wallet_id = str(uuid.uuid4())
        cursor.execute("""
            INSERT INTO merchant_wallets (id, merchant_id, chain, wallet_address, is_active, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """, (wallet_id, merchant_id, chain, address, True, datetime.utcnow()))
        print(f"  ✓ {chain}: {address[:20]}...")
    
    # Create test payment sessions
    print("\n💰 Creating test payment sessions...")
    
    payment_data = [
        ("pay_test_" + str(uuid.uuid4())[:8], 50.00, "USD", "paid"),
        ("pay_test_" + str(uuid.uuid4())[:8], 100.00, "USD", "paid"),
        ("pay_test_" + str(uuid.uuid4())[:8], 25.50, "USD", "created"),
    ]
    
    for session_id, amount, currency, status in payment_data:
        cursor.execute("""
            INSERT INTO payment_sessions 
            (id, merchant_id, amount_fiat, fiat_currency, amount_usdc, status, 
             success_url, cancel_url, created_at, paid_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """, (
            session_id, merchant_id, amount, currency, str(amount),
            status, 
            "http://localhost:3000/success", 
            "http://localhost:3000/cancel",
            datetime.utcnow(),
            datetime.utcnow() if status == "paid" else None
        ))
        print(f"  ✓ {session_id}: ${amount} {currency} ({status})")
    
    conn.commit()
    
    # Verify
    print("\n✅ Verifying data...")
    cursor.execute("SELECT COUNT(*) as count FROM merchant_wallets WHERE merchant_id = %s", (merchant_id,))
    wallet_count = cursor.fetchone()['count']
    cursor.execute("SELECT COUNT(*) as count FROM payment_sessions WHERE merchant_id = %s", (merchant_id,))
    payment_count = cursor.fetchone()['count']
    
    print(f"  Wallets: {wallet_count}")
    print(f"  Payments: {payment_count}")
    
    cursor.close()
    conn.close()
    
    print("\n" + "=" * 60)
    print("✅ TEST DATA CREATED SUCCESSFULLY!")
    print("=" * 60)
    print("\n🔄 Refresh your API debugger to see the data!")
    
except Exception as e:
    print(f"❌ Error: {e}")
    if conn:
        conn.rollback()
