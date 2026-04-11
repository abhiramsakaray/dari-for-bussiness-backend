#!/usr/bin/env python3
"""
Check Unconfirmed Polygon Payments

This script finds and diagnoses unconfirmed payments on Polygon.
Helps identify:
  - Payment pending confirmation
  - Blockchain confirmation status
  - Why payment might be stuck
"""

import sys
from datetime import datetime, timedelta

sys.path.insert(0, '.')

from app.core.database import SessionLocal
from app.models.models import PaymentSession, PaymentStatus
from web3 import Web3

# Polygon Amoy RPC
POLYGON_RPC = "https://rpc-amoy.polygon.technology"

def check_unconfirmed_payments():
    """Find all unconfirmed Polygon payments"""
    print(f"\n{'='*70}")
    print(f"🔍 Checking Unconfirmed Polygon Payments")
    print(f"{'='*70}\n")
    
    db = SessionLocal()
    try:
        # Find payments from last 24 hours that are not confirmed
        cutoff = datetime.utcnow() - timedelta(hours=24)
        
        unconfirmed = db.query(PaymentSession).filter(
            PaymentSession.chain == 'polygon',
            PaymentSession.status.in_([
                PaymentStatus.CREATED,
                PaymentStatus.PENDING,
                PaymentStatus.PROCESSING,
            ]),
            PaymentSession.created_at >= cutoff
        ).order_by(PaymentSession.created_at.desc()).all()
        
        if not unconfirmed:
            print("✅ No unconfirmed Polygon payments found in last 24 hours\n")
            return
        
        print(f"Found {len(unconfirmed)} unconfirmed payment(s):\n")
        
        for i, payment in enumerate(unconfirmed, 1):
            print(f"{i}. Payment Session: {payment.id}")
            print(f"   Status: {payment.status.value}")
            print(f"   Amount: {payment.amount_fiat} {payment.fiat_currency}")
            print(f"   Token: {payment.token} ({payment.amount_token})")
            print(f"   Merchant: {payment.merchant_id}")
            print(f"   Created: {payment.created_at}")
            if payment.tx_hash:
                print(f"   TX Hash: {payment.tx_hash}")
                check_blockchain_status(payment.tx_hash)
            else:
                print(f"   TX Hash: Not yet recorded")
            print(f"   Awaiting: {datetime.utcnow() - payment.created_at}")
            print()
        
        # Return first unconfirmed for further analysis
        if unconfirmed:
            return unconfirmed[0]
    finally:
        db.close()


def check_blockchain_status(tx_hash):
    """Check transaction status on Polygon blockchain"""
    print(f"   📍 Checking on-chain status...")
    
    try:
        w3 = Web3(Web3.HTTPProvider(POLYGON_RPC))
        
        if not w3.is_connected():
            print(f"      ❌ Cannot connect to Polygon RPC")
            return
        
        # Try to get receipt
        try:
            receipt = w3.eth.get_transaction_receipt(tx_hash)
            if receipt:
                print(f"      ✅ Transaction confirmed!")
                print(f"         Block: {receipt['blockNumber']}")
                print(f"         Status: {'✅ SUCCESS' if receipt['status'] == 1 else '❌ REVERTED'}")
                print(f"         Gas Used: {receipt['gasUsed']}")
                return
        except Exception:
            pass
        
        # Check if transaction exists but not confirmed
        try:
            tx = w3.eth.get_transaction(tx_hash)
            if tx:
                print(f"      ⏳ Transaction pending (in mempool)")
                print(f"         From: {tx['from']}")
                print(f"         To: {tx['to']}")
                print(f"         Nonce: {tx['nonce']}")
                print(f"         Gas Price: {w3.from_wei(tx['gasPrice'], 'gwei')} gwei")
                return
        except Exception:
            pass
        
        print(f"      ❌ Transaction not found on blockchain")
        print(f"         ℹ️  It may not have been broadcast, or network is slow")
        
    except Exception as e:
        print(f"      ⚠️  Error checking blockchain: {e}")


def show_options(payment):
    """Show what to do next"""
    print(f"\n{'='*70}")
    print(f"💡 Next Steps")
    print(f"{'='*70}\n")
    
    status = payment.status.value
    
    if status == 'CREATED':
        print("❌ Payment created but NOT sent to blockchain")
        print("   Options:")
        print("   1. Check if user completed the payment form")
        print("   2. User must scan QR code and confirm from wallet")
        print("   3. Session may have expired (15 min timeout from first load)")
        print("   4. Check blockchain listeners are running")
        
    elif status == 'PENDING':
        print("⏳ Payment is PENDING (transaction detected)")
        print("   Options:")
        print("   1. Wait for blockchain confirmation (1-3 min typically)")
        print("   2. Check if listeners are running: python scripts/run_listeners.py polygon")
        print("   3. Manually check TX on: https://amoy.polygonscan.com/tx/" + (payment.tx_hash or 'TX_HASH'))
        print("   4. If stuck, check: python docs/check_gas_estimation.py polygon")
        
    elif status == 'PROCESSING':
        print("🔄 Payment is PROCESSING (waiting for confirmations)")
        print("   Options:")
        print("   1. Usually confirms within 1-3 blocks")
        print("   2. Check Polygon network status")
        print("   3. If stuck >10 minutes, check logs for errors")


def main():
    payment = check_unconfirmed_payments()
    
    if payment:
        show_options(payment)
    
    print(f"\n{'='*70}\n")


if __name__ == '__main__':
    main()
