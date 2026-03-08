"""
Fix merchant abhiram@dariorganization.com: create wallets and mark onboarding complete
"""
import psycopg2
import secrets
import uuid

def generate_placeholder_address(chain):
    random_hex = secrets.token_hex(20)
    if chain == "stellar":
        return f"G{'A' * 15}{secrets.token_hex(20).upper()[:40]}"
    elif chain == "tron":
        return f"T{secrets.token_hex(16).upper()[:33]}"
    else:
        return f"0x{random_hex}"

merchant_id = "27dd5606-f87f-4b93-ad64-33b95646d57f"
chains = ["stellar", "ethereum", "polygon", "base", "tron"]
tokens = ["USDC", "USDT", "PYUSD"]

try:
    conn = psycopg2.connect(host='localhost', port=5432, database='chainpe', user='dariwallettest', password='Mummydaddy143')
    cursor = conn.cursor()

    # Create wallets
    print("Creating wallets for abhiram@dariorganization.com...")
    for chain in chains:
        wallet_id = str(uuid.uuid4())
        address = generate_placeholder_address(chain)
        cursor.execute("""
            INSERT INTO merchant_wallets (id, merchant_id, chain, wallet_address, is_active, created_at)
            VALUES (%s, %s, %s, %s, TRUE, NOW())
            ON CONFLICT DO NOTHING
        """, (wallet_id, merchant_id, chain.upper(), address))
        print(f"  + {chain.upper()}: {address[:30]}...")

    # Update merchant: mark onboarding complete, set chains/tokens
    import json
    cursor.execute("""
        UPDATE merchants
        SET onboarding_step = 3,
            onboarding_completed = TRUE,
            accepted_chains = %s::jsonb,
            accepted_tokens = %s::jsonb
        WHERE id = %s
    """, (json.dumps(chains), json.dumps(tokens), merchant_id))
    print("\nUpdated merchant: onboarding_completed=True, step=3")

    conn.commit()

    # Verify
    cursor.execute("SELECT COUNT(*) FROM merchant_wallets WHERE merchant_id = %s", (merchant_id,))
    count = cursor.fetchone()[0]
    print(f"\n✅ Done! Merchant now has {count} wallets.")

    cursor.close()
    conn.close()

except Exception as e:
    print(f"❌ Error: {e}")
    if conn:
        conn.rollback()
