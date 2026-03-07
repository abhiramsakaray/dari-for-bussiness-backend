"""
Show all merchants and their data counts
"""
import psycopg2
from psycopg2.extras import RealDictCursor

try:
    conn = psycopg2.connect(
        host="localhost",
        port=5432,
        database="chainpe",
        user="dariwallettest",
        password="Mummydaddy143"
    )
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    print("=" * 80)
    print("ALL MERCHANTS WITH DATA SUMMARY")
    print("=" * 80)
    
    # Get all merchants with their data counts
    cursor.execute("""
        SELECT 
            m.id,
            m.name,
            m.email,
            m.created_at,
            COUNT(DISTINCT mw.id) as wallet_count,
            COUNT(DISTINCT ps.id) as payment_count
        FROM merchants m
        LEFT JOIN merchant_wallets mw ON m.id = mw.merchant_id
        LEFT JOIN payment_sessions ps ON m.id = ps.merchant_id
        GROUP BY m.id, m.name, m.email, m.created_at
        ORDER BY m.created_at DESC
    """)
    merchants = cursor.fetchall()
    
    for m in merchants:
        print(f"\n📧 {m['email']}")
        print(f"   Name: {m['name']}")
        print(f"   ID: {m['id']}")
        print(f"   Wallets: {m['wallet_count']}")
        print(f"   Payments: {m['payment_count']}")
        print(f"   Created: {m['created_at']}")
        
        # Show wallets for merchants with wallets
        if m['wallet_count'] > 0:
            cursor.execute("""
                SELECT chain, wallet_address 
                FROM merchant_wallets 
                WHERE merchant_id = %s
            """, (m['id'],))
            wallets = cursor.fetchall()
            print("   Chains:", ", ".join([w['chain'] for w in wallets]))
    
    cursor.close()
    conn.close()
    
    print("\n" + "=" * 80)
    print("\n💡 TIP: Log in with a merchant that has wallets and payments")
    print("   to see data in the dashboard!")
    print("=" * 80)
    
except Exception as e:
    print(f"❌ Error: {e}")
