#!/usr/bin/env python3
"""Check what payment sessions exist and what addresses they're waiting for."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.models import PaymentSession, PaymentStatus

db = SessionLocal()
try:
    # Get the most recent CREATED Polygon payments
    sessions = db.query(PaymentSession).filter(
        PaymentSession.chain == 'polygon',
        PaymentSession.status == 'CREATED'
    ).order_by(PaymentSession.created_at.desc()).limit(3).all()
    
    print("=" * 80)
    print("YOUR RECENT PAYMENT SESSIONS - WHERE TO SEND PAYMENT")
    print("=" * 80)
    
    for s in sessions:
        print(f"\n📝 Session ID: {s.id}")
        print(f"   Amount: {s.amount_usdc} USDC")
        print(f"   Chain: {s.chain}")
        print(f"   Token: {s.token}")
        print(f"   ⬅️  SEND PAYMENT TO THIS ADDRESS:")
        print(f"   👉 {s.merchant_wallet}")
        print(f"   Status: {s.status}")
        print(f"   Created: {s.created_at}")
        if s.tx_hash:
            print(f"   TX Hash: {s.tx_hash}")
            print(f"   Confirmations: {s.confirmations}")
            
finally:
    db.close()
