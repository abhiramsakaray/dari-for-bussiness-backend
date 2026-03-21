from sqlalchemy import text
from app.core.database import engine

with engine.connect() as conn:
    res = conn.execute(text("SELECT enumlabel FROM pg_enum JOIN pg_type ON pg_enum.enumtypid = pg_type.oid WHERE pg_type.typname = 'web3subscriptionstatus';"))
    labels = [row[0] for row in res]
    print(f"Enum labels in DB: {labels}")
