"""
Add API Key to Merchant Model

This script adds the api_key field to existing Merchant accounts.
Run this if you're getting "Cannot read api_key" errors.
"""

import secrets
from app.core.database import SessionLocal
from app.models import Merchant


def generate_api_key() -> str:
    """Generate a secure API key."""
    return f"pk_live_{secrets.token_urlsafe(32)}"


def add_api_keys_to_merchants():
    """Add API keys to all merchants that don't have one."""
    db = SessionLocal()
    try:
        merchants = db.query(Merchant).all()
        updated_count = 0
        
        for merchant in merchants:
            if not hasattr(merchant, 'api_key') or not merchant.api_key:
                api_key = generate_api_key()
                merchant.api_key = api_key
                print(f"✅ Generated API key for {merchant.email}")
                print(f"   API Key: {api_key}")
                updated_count += 1
        
        if updated_count > 0:
            db.commit()
            print(f"\n✅ Successfully updated {updated_count} merchant(s)")
        else:
            print("ℹ️  All merchants already have API keys")
            
    except Exception as e:
        db.rollback()
        print(f"❌ Error: {e}")
    finally:
        db.close()


def generate_api_key_for_email(email: str):
    """Generate API key for a specific merchant by email."""
    db = SessionLocal()
    try:
        merchant = db.query(Merchant).filter(Merchant.email == email).first()
        
        if not merchant:
            print(f"❌ Merchant {email} not found")
            return
        
        api_key = generate_api_key()
        merchant.api_key = api_key
        db.commit()
        
        print(f"✅ API Key generated for {merchant.email}")
        print(f"\nAPI Key: {api_key}")
        print(f"\n📋 Add this to your frontend .env file:")
        print(f"VITE_CHAINPE_API_KEY={api_key}")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        # Generate for specific email
        email = sys.argv[1]
        generate_api_key_for_email(email)
    else:
        # Generate for all merchants
        print("Generating API keys for all merchants without one...\n")
        add_api_keys_to_merchants()
