"""
One-time migration script to add missing values to the payment_status enum in PostgreSQL.
Run once: python fix_enum.py

The existing DB enum uses UPPERCASE names (CREATED, PAID, EXPIRED) because SQLAlchemy's
default behavior stores the Python enum's .name (not .value) when using Enum columns.
We need to add FAILED (and optionally PENDING, REFUNDED, PARTIALLY_REFUNDED) to the DB enum.
"""
import sys
from sqlalchemy import create_engine, text

# Load settings the same way the app does
try:
    from app.core.config import settings
    db_url = settings.DATABASE_URL
except Exception as e:
    print(f"Could not load settings: {e}")
    sys.exit(1)

if "sqlite" in db_url:
    print("SQLite detected — no enum migration needed for SQLite.")
    print("If you are using PostgreSQL, set DATABASE_URL in your .env file.")
    sys.exit(0)

print(f"Connecting to database...")

engine = create_engine(db_url)

# These are the UPPERCASE names SQLAlchemy stores by default
new_values = ["PENDING", "FAILED", "REFUNDED", "PARTIALLY_REFUNDED"]

with engine.connect() as conn:
    # Check existing enum values (look for both possible type names)
    result = conn.execute(text("""
        SELECT t.typname, enumlabel 
        FROM pg_enum e
        JOIN pg_type t ON t.oid = e.enumtypid
        WHERE t.typname IN ('paymentstatus', 'payment_status')
        ORDER BY t.typname, enumsortorder;
    """))
    rows = result.fetchall()
    
    if not rows:
        print("ERROR: No 'payment_status' or 'paymentstatus' enum type found in the database!")
        print("Make sure you are connected to the correct database.")
        sys.exit(1)
    
    type_name = rows[0][0]
    existing = [row[1] for row in rows]
    print(f"Found enum type '{type_name}' with values: {existing}")

    added = []
    for value in new_values:
        if value not in existing:
            conn.execute(text(f"ALTER TYPE {type_name} ADD VALUE IF NOT EXISTS '{value}'"))
            added.append(value)
            print(f"  ✓ Added '{value}'")
        else:
            print(f"  - '{value}' already exists, skipping")
    
    conn.commit()

if added:
    print(f"\n✅ Successfully added {len(added)} new value(s): {added}")
    print("Restart your FastAPI server for the changes to take effect.")
else:
    print("\n✅ All values already present — no changes needed.")
