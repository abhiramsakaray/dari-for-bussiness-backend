import sys
sys.path.insert(0, r"d:\Projects\Dari for Bussiness\chainpe\chainpe-backend")

from app.core.database import engine
from sqlalchemy import text

with engine.connect() as conn:
    try:
        conn.execute(text("ALTER TYPE web3subscriptionstatus ADD VALUE IF NOT EXISTS 'pending_payment'"))
        print("Added pending_payment")
    except Exception as e:
        print(f"pending_payment: {e}")
    try:
        conn.execute(text("ALTER TYPE web3subscriptionstatus ADD VALUE IF NOT EXISTS 'paused'"))
        print("Added paused")
    except Exception as e:
        print(f"paused: {e}")
    conn.commit()

    try:
        conn.execute(text("ALTER TABLE web3_subscriptions ADD COLUMN IF NOT EXISTS grace_period_days INTEGER DEFAULT 3"))
        print("Added grace_period_days")
    except Exception as e:
        print(f"grace_period_days: {e}")
    try:
        conn.execute(text("ALTER TABLE web3_subscriptions ADD COLUMN IF NOT EXISTS paused_at TIMESTAMP"))
        print("Added paused_at")
    except Exception as e:
        print(f"paused_at: {e}")
    conn.commit()

print("Migration done")
