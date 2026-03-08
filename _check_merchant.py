import psycopg2
from psycopg2.extras import RealDictCursor
conn = psycopg2.connect(host='localhost', port=5432, database='chainpe', user='dariwallettest', password='Mummydaddy143')
cursor = conn.cursor(cursor_factory=RealDictCursor)

mid = '27dd5606-f87f-4b93-ad64-33b95646d57f'
cursor.execute('SELECT id, name, email, onboarding_step, onboarding_completed, business_name, accepted_chains, accepted_tokens, api_key FROM merchants WHERE id = %s', (mid,))
m = cursor.fetchone()
for k, v in m.items():
    print(f'{k}: {v}')

print()
cursor.execute('SELECT COUNT(*) as cnt FROM merchant_wallets WHERE merchant_id = %s', (mid,))
row = cursor.fetchone()
print(f"Wallets: {row['cnt']}")
conn.close()
