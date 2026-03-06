"""
Database initialization script.
Creates all tables and optionally seeds initial admin account.
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import engine, Base, SessionLocal
from app.core.security import hash_password
from app.core.config import settings
from app.models import Merchant, PaymentSession, Admin


def init_db():
    """Initialize the database."""
    print("Creating database tables...")
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    
    print("✅ Database tables created successfully!")
    
    # Create admin account if it doesn't exist
    db = SessionLocal()
    try:
        existing_admin = db.query(Admin).filter(Admin.email == settings.ADMIN_EMAIL).first()
        
        if not existing_admin:
            admin = Admin(
                email=settings.ADMIN_EMAIL,
                password_hash=hash_password(settings.ADMIN_PASSWORD)
            )
            db.add(admin)
            db.commit()
            print(f"\n✅ Admin account created:")
            print(f"   Email: {settings.ADMIN_EMAIL}")
            print(f"   Password: {settings.ADMIN_PASSWORD}")
            print(f"\n⚠️  IMPORTANT: Change the admin password in production!")
        else:
            print(f"\nℹ️  Admin account already exists: {settings.ADMIN_EMAIL}")
    
    except Exception as e:
        print(f"Error creating admin account: {e}")
        db.rollback()
    finally:
        db.close()
    
    print("\n" + "=" * 60)
    print("Database initialization complete!")
    print("=" * 60)


if __name__ == "__main__":
    init_db()
