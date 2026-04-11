#!/usr/bin/env python3
"""Check payment sessions and merchant wallet addresses for debugging listener issues."""

import sys
import os

# Add parent directory to path so we can import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.models import PaymentSession, MerchantWallet
from app.core.config import settings
from sqlalchemy import func

def check_payment_addresses():
    """Check unconfirmed payments and merchant wallet setup."""
    db = SessionLocal()
    try:
        # Find recent CREATED payment sessions on Polygon
        print("🔍 RECENT CREATED PAYMENT SESSIONS (Polygon)")
        print("=" * 80)
        
        sessions = db.query(PaymentSession).filter(
            PaymentSession.chain == 'polygon',
            PaymentSession.status == 'CREATED'
        ).order_by(PaymentSession.created_at.desc()).limit(5).all()
        
        if not sessions:
            print("No CREATED sessions found on Polygon")
        else:
            for s in sessions:
                print(f"\nSession: {s.id}")
                print(f"  Merchant: {s.merchant_id}")
                print(f"  Amount: {s.amount_usdc} USDC (token: {s.amount_token})")
                print(f"  Chain: {s.chain}")
                print(f"  Token: {s.token}")
                print(f"  Merchant Wallet: {s.merchant_wallet}")
                print(f"  Deposit Address: {s.deposit_address}")
                print(f"  Created: {s.created_at}")
                if s.tx_hash:
                    print(f"  TX Hash: {s.tx_hash}")
        
        # Check merchant wallet configuration
        print("\n" + "=" * 80)
        print("👥 MERCHANT WALLET CONFIGURATION (Polygon)")
        print("=" * 80)
        
        wallets = db.query(MerchantWallet).filter(
            MerchantWallet.chain == 'polygon'
        ).all()
        
        if not wallets:
            print("No merchant wallets configured for Polygon")
        else:
            for w in wallets:
                print(f"\nWallet ID: {w.id}")
                print(f"  Merchant: {w.merchant_id}")
                print(f"  Address: {w.wallet_address}")
                print(f"  Active: {w.is_active}")
                print(f"  Created: {w.created_at}")
        
        # Check if payment session addresses match merchant wallets
        print("\n" + "=" * 80)
        print("🔗 ADDRESS MATCHING CHECK")
        print("=" * 80)
        
        active_wallet_addrs = {w.wallet_address.lower() for w in wallets if w.is_active and w.wallet_address}
        
        for s in sessions:
            session_addr = (s.merchant_wallet or "").lower()
            if session_addr:
                is_in_wallets = session_addr in active_wallet_addrs
                print(f"\nSession {s.id}:")
                print(f"  Waiting for payment to: {s.merchant_wallet}")
                print(f"  In active merchant wallets? {is_in_wallets}")
                if not is_in_wallets:
                    print(f"  ❌ PROBLEM: This address is NOT in the listener's watched addresses!")
                else:
                    print(f"  ✅ This address WILL be detected by listener")
            else:
                print(f"\nSession {s.id}: No merchant_wallet address set!")
        
        print("\n" + "=" * 80)
        print("📊 LISTENER WATCHED ADDRESSES (what listener sees)")
        print("=" * 80)
        print(f"Active merchant wallets for Polygon: {len(active_wallet_addrs)}")
        for addr in active_wallet_addrs:
            print(f"  • {addr}")
        
        # Check total payment count by status
        print("\n" + "=" * 80)
        print("📈 PAYMENT SESSION COUNT BY STATUS (All Chains)")
        print("=" * 80)
        
        stats = db.query(
            PaymentSession.chain,
            PaymentSession.status,
            func.count(PaymentSession.id).label('count')
        ).group_by(PaymentSession.chain, PaymentSession.status).all()
        
        for chain, status, count in stats:
            print(f"{chain:12} {status:20} {count:4} sessions")
            
    finally:
        db.close()

if __name__ == '__main__':
    check_payment_addresses()
