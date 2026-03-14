import psycopg2

conn = psycopg2.connect(
    host="localhost",
    port=5432,
    database="chainpe",
    user="dariwallettest",
    password="Mummydaddy143",
)
conn.autocommit = True
cur = conn.cursor()

cur.execute("ALTER TYPE subscription_status ADD VALUE IF NOT EXISTS 'pending_payment'")
cur.execute("ALTER TYPE subscription_status ADD VALUE IF NOT EXISTS 'PENDING_PAYMENT'")

# Normalize legacy uppercase enum data to lowercase values expected by ORM.
cur.execute(
    """
    UPDATE subscriptions
    SET status = CASE status::text
        WHEN 'ACTIVE' THEN 'active'::subscription_status
        WHEN 'PAUSED' THEN 'paused'::subscription_status
        WHEN 'CANCELLED' THEN 'cancelled'::subscription_status
        WHEN 'PAST_DUE' THEN 'past_due'::subscription_status
        WHEN 'TRIALING' THEN 'trialing'::subscription_status
        WHEN 'PENDING_PAYMENT' THEN 'pending_payment'::subscription_status
        ELSE status
    END
    WHERE status::text IN (
        'ACTIVE', 'PAUSED', 'CANCELLED', 'PAST_DUE', 'TRIALING', 'PENDING_PAYMENT'
    )
    """
)

cur.execute("select unnest(enum_range(NULL::subscription_status))::text")
print([r[0] for r in cur.fetchall()])

cur.close()
conn.close()
