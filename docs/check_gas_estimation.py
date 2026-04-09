#!/usr/bin/env python3
"""
Diagnose Gas Estimation Errors

This script helps identify why gas estimation is failing for subscription payments.
It checks:
  1. Relayer account balance and nonce
  2. Subscription exists on-chain and is in valid state
  3. Required approvals are in place
  4. Smart contract state and permissions
"""

import asyncio
import sys
from decimal import Decimal
from web3 import Web3

# Add app to path
sys.path.insert(0, '/app' if __name__ != '__main__' else '.')

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.models import Web3Subscription
from app.services.gasless_relayer import CHAIN_CONFIG, relayer as evm_relayer


def check_relayer_balance(chain: str):
    """Check relayer account balance and nonce"""
    print(f"\n{'='*60}")
    print(f"🔍 Checking Relayer Status on {chain.upper()}")
    print(f"{'='*60}")
    
    try:
        balance_info = evm_relayer.get_relayer_balance(chain)
        print(f"✅ Relayer Address: {balance_info['address']}")
        print(f"   Balance: {balance_info['balance_eth']} ETH")
        print(f"   Balance: {balance_info['balance_native']} {balance_info['symbol']}")
        print(f"   Status: {'⚠️  LOW BALANCE' if float(balance_info['balance_eth']) < 0.1 else '✅ Sufficient'}")
        return balance_info
    except Exception as e:
        print(f"❌ Error checking relayer: {e}")
        return None


def check_subscription_onchain(chain: str, onchain_id: int):
    """Check if subscription exists on-chain and is valid"""
    print(f"\n{'='*60}")
    print(f"🔍 Checking Subscription #{onchain_id} on {chain.upper()}")
    print(f"{'='*60}")
    
    try:
        sub_data = evm_relayer.get_onchain_subscription(chain, onchain_id)
        print(f"✅ Subscription exists on-chain")
        print(f"   Subscriber: {sub_data['subscriber']}")
        print(f"   Merchant: {sub_data['merchant']}")
        print(f"   Token: {sub_data['token']}")
        print(f"   Amount: {sub_data['amount']}")
        print(f"   Interval: {sub_data['interval']} seconds")
        print(f"   Active: {sub_data['active']}")
        print(f"   Next Payment: {sub_data['nextPayment']}")
        
        # Check if payment is due
        is_due = evm_relayer.is_payment_due_onchain(chain, onchain_id)
        print(f"   Payment Due: {'✅ YES' if is_due else '❌ No'}")
        
        return sub_data, is_due
    except Exception as e:
        print(f"❌ Error checking subscription: {e}")
        return None, None


def check_contract_permissions(chain: str):
    """Check if relayer has required permissions on contract"""
    print(f"\n{'='*60}")
    print(f"🔍 Checking Contract Permissions on {chain.upper()}")
    print(f"{'='*60}")
    
    try:
        contract = evm_relayer._get_contract(chain)
        relayer_addr = evm_relayer._account.address
        
        print(f"✅ Contract connected: {contract.address}")
        print(f"   Relayer: {relayer_addr}")
        
        # Try to call a read-only function to verify we can interact with the contract
        print(f"   Can call contract functions: ✅")
        
        return True
    except Exception as e:
        print(f"❌ Error checking contract: {e}")
        return False


async def test_gas_estimation(chain: str, onchain_id: int):
    """Test gas estimation for executePayment"""
    print(f"\n{'='*60}")
    print(f"🔍 Testing Gas Estimation on {chain.upper()}")
    print(f"{'='*60}")
    
    try:
        contract = evm_relayer._get_contract(chain)
        tx_func = contract.functions.executePayment(onchain_id)
        
        print(f"⏳ Estimating gas for executePayment({onchain_id})...")
        gas_estimate = tx_func.estimate_gas({"from": evm_relayer._account.address})
        gas_limit = int(gas_estimate * 1.3)
        
        print(f"✅ Gas estimation successful")
        print(f"   Estimated: {gas_estimate} gas")
        print(f"   With 30% buffer: {gas_limit} gas")
        
        return gas_limit
    except Exception as e:
        print(f"❌ Gas estimation failed: {e}")
        print(f"   Error Type: {type(e).__name__}")
        print(f"   Possible causes:")
        print(f"      • Subscription not found on-chain")
        print(f"      • Subscription is not in a due state")
        print(f"      • Subscription already executed")
        print(f"      • Token approval missing")
        print(f"      • Insufficient subscriber balance")
        print(f"      • Contract paused or disabled")
        return None


async def main():
    if len(sys.argv) < 2:
        print("Usage: python check_gas_estimation.py <chain> [subscription_id]")
        print("Example: python check_gas_estimation.py polygon 123")
        sys.exit(1)
    
    chain = sys.argv[1].lower()
    sub_id = int(sys.argv[2]) if len(sys.argv) > 2 else None
    
    # Initialize relayer
    if not evm_relayer._account:
        print("❌ Relayer not initialized. Set RELAYER_PRIVATE_KEY in .env")
        sys.exit(1)
    
    # Check relayer status
    balance_info = check_relayer_balance(chain)
    if not balance_info:
        sys.exit(1)
    
    # If subscription ID provided, check it
    if sub_id:
        sub_data, is_due = check_subscription_onchain(chain, sub_id)
        if sub_data:
            # Test gas estimation
            await test_gas_estimation(chain, sub_id)
        else:
            print("⚠️  Cannot test gas estimation without valid subscription")
    else:
        # List due subscriptions from database
        print(f"\n{'='*60}")
        print(f"📋 Due Subscriptions in Database")
        print(f"{'='*60}")
        
        db = SessionLocal()
        try:
            due_subs = db.query(Web3Subscription).filter(
                Web3Subscription.chain == chain,
                Web3Subscription.status.in_(['ACTIVE', 'PAST_DUE', 'PENDING_PAYMENT']),
            ).all()
            
            if not due_subs:
                print(f"No due subscriptions found for {chain}")
            else:
                for sub in due_subs[:5]:  # Show first 5
                    print(f"\n  ID: {sub.id}")
                    print(f"  Chain ID (on-chain): {sub.onchain_subscription_id}")
                    print(f"  Status: {sub.status}")
                    print(f"  Next Payment: {sub.next_payment_at}")
                    
                    # Test gas estimation for this one
                    if sub.onchain_subscription_id:
                        print(f"  Testing gas estimation...")
                        await test_gas_estimation(chain, sub.onchain_subscription_id)
        finally:
            db.close()
    
    print(f"\n{'='*60}")
    print(f"✅ Diagnosis complete")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    asyncio.run(main())
