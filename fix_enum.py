import sys
sys.path.insert(0, r"d:\Projects\Dari for Bussiness\chainpe\chainpe-backend")

from app.core.database import engine
from sqlalchemy import text

with engine.connect() as conn:
    try:
        conn.execute(text("ALTER TYPE web3subscriptionstatus ADD VALUE IF NOT EXISTS 'PENDING_PAYMENT'"))
        print("Added uppercase PENDING_PAYMENT")
    except Exception as e:
        print(f"PENDING_PAYMENT: {e}")
    try:
        conn.execute(text("ALTER TYPE web3subscriptionstatus ADD VALUE IF NOT EXISTS 'PAUSED'"))
        print("Added uppercase PAUSED")
    except Exception as e:
        print(f"PAUSED: {e}")
    conn.commit()

print("Enum fix migration done")
