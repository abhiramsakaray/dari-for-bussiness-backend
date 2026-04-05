"""
Fix Stuck Subscriptions

Manually fixes subscriptions that are stuck in PENDING_PAYMENT or have incorrect state.
This script should be run AFTER applying the database migration.

Usage:
    python scripts/fix_stuck_subscriptions.py --dry-run  # Preview changes
    python scripts/fix_stuck_subscriptions.py            # Apply fixes
"""

import sys
import os
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.models import Web3Subscription, Web3SubscriptionStatus
from app.services.gasless_relayer import relayer


def fix_stuck_subscriptions(dry_run=True):
    """Fix subscriptions stuck in PENDING_PAYMENT or with incorrect state"""
    db = SessionLocal()
    
    try:
        print("\n" + "="*80)
        print("STUCK SUBSCRIPTION FIXER")
        print("="*80)
        
        if dry_run:
            print("\n⚠️  DRY RUN MODE - No changes will be made")
        else:
            print("\n✅ LIVE MODE - Changes will be applied")
        
        now = datetime.utcnow()
        fixed_count = 0
        
        # Find stuck subscriptions
        stuck_subs = db.query(Web3Subscription).filter(
            Web3Subscription.status == Web3SubscriptionStatus.PENDING_PAYMENT,
            Web3Subscription.created_at < now - timedelta(hours=1)  # Older than 1 hour
        ).all()
        
        print(f"\n📋 Found {len(stuck_subs)} subscription(s) stuck in PENDING_PAYMENT > 1h")
        
        for sub in stuck_subs:
            print(f"\n{'─'*80}")
            print(f"Subscription ID: {sub.id}")
            print(f"Created: {sub.created_at}")
            print(f"On-chain ID: {sub.onchain_subscription_id}")
            print(f"Chain: {sub.chain}")
            
            if not sub.onchain_subscription_id:
                print("❌ No on-chain ID - cannot fix automatically")
                continue
            
            try:
                # Check on-chain state
                onchain = relayer.get_onchain_subscription(sub.chain, sub.onchain_subscription_id)
                
                print(f"\nOn-chain state:")
                print(f"  Active: {onchain['active']}")
                print(f"  Payment Count: {onchain['paymentCount']}")
                print(f"  Next Payment: {datetime.utcfromtimestamp(onchain['nextPayment'])}")
                
                # Determine correct state
                if not onchain['active']:
                    print("\n🔧 Fix: Set to CANCELLED (inactive on-chain)")
                    if not dry_run:
                        sub.status = Web3SubscriptionStatus.CANCELLED
                        sub.cancelled_at = now
                        sub.updated_at = now
                        fixed_count += 1
                
                elif onchain['paymentCount'] > 0:
                    print(f"\n🔧 Fix: Set to ACTIVE (has {onchain['paymentCount']} payment(s))")
                    if not dry_run:
                        sub.status = Web3SubscriptionStatus.ACTIVE
                        sub.total_payments = onchain['paymentCount']
                        sub.next_payment_at = datetime.utcfromtimestamp(onchain['nextPayment'])
                        sub.failed_payment_count = 0
                        sub.first_failed_at = None
                        sub.updated_at = now
                        fixed_count += 1
                
                else:
                    # No payments yet - check if payment is due
                    is_due = relayer.is_payment_due_onchain(sub.chain, sub.onchain_subscription_id)
                    
                    if is_due:
                        print("\n🔧 Fix: Set to PAST_DUE (payment due but not executed)")
                        if not dry_run:
                            sub.status = Web3SubscriptionStatus.PAST_DUE
                            sub.failed_payment_count = 1
                            sub.first_failed_at = sub.created_at
                            sub.next_payment_at = now  # Retry immediately
                            sub.updated_at = now
                            fixed_count += 1
                    else:
                        # Payment not due yet - update next_payment_at
                        next_payment = datetime.utcfromtimestamp(onchain['nextPayment'])
                        print(f"\n🔧 Fix: Update next_payment_at to {next_payment}")
                        if not dry_run:
                            sub.next_payment_at = next_payment
                            sub.updated_at = now
                            fixed_count += 1
                
            except Exception as e:
                print(f"\n❌ Error checking on-chain state: {e}")
                continue
        
        # Find overdue ACTIVE subscriptions
        overdue_subs = db.query(Web3Subscription).filter(
            Web3Subscription.status == Web3SubscriptionStatus.ACTIVE,
            Web3Subscription.next_payment_at < now - timedelta(hours=1)
        ).all()
        
        print(f"\n\n📋 Found {len(overdue_subs)} ACTIVE subscription(s) overdue > 1h")
        
        for sub in overdue_subs:
            print(f"\n{'─'*80}")
            print(f"Subscription ID: {sub.id}")
            print(f"Next Payment: {sub.next_payment_at}")
            print(f"Overdue by: {(now - sub.next_payment_at).total_seconds() / 3600:.1f}h")
            
            if not sub.onchain_subscription_id:
                print("❌ No on-chain ID - cannot fix automatically")
                continue
            
            try:
                # Check on-chain state
                onchain = relayer.get_onchain_subscription(sub.chain, sub.onchain_subscription_id)
                
                if not onchain['active']:
                    print("\n🔧 Fix: Set to CANCELLED (inactive on-chain)")
                    if not dry_run:
                        sub.status = Web3SubscriptionStatus.CANCELLED
                        sub.cancelled_at = now
                        sub.updated_at = now
                        fixed_count += 1
                
                else:
                    # Sync with on-chain state
                    onchain_next = datetime.utcfromtimestamp(onchain['nextPayment'])
                    
                    if onchain['paymentCount'] > sub.total_payments:
                        print(f"\n🔧 Fix: Sync payment count ({sub.total_payments} → {onchain['paymentCount']})")
                        if not dry_run:
                            sub.total_payments = onchain['paymentCount']
                            sub.next_payment_at = onchain_next
                            sub.failed_payment_count = 0
                            sub.first_failed_at = None
                            sub.updated_at = now
                            fixed_count += 1
                    
                    elif onchain_next > now:
                        print(f"\n🔧 Fix: Update next_payment_at to {onchain_next}")
                        if not dry_run:
                            sub.next_payment_at = onchain_next
                            sub.updated_at = now
                            fixed_count += 1
                    
                    else:
                        print("\n🔧 Fix: Set to PAST_DUE (payment overdue)")
                        if not dry_run:
                            sub.status = Web3SubscriptionStatus.PAST_DUE
                            if sub.first_failed_at is None:
                                sub.first_failed_at = sub.next_payment_at
                            sub.failed_payment_count = (sub.failed_payment_count or 0) + 1
                            sub.next_payment_at = now  # Retry immediately
                            sub.updated_at = now
                            fixed_count += 1
                
            except Exception as e:
                print(f"\n❌ Error checking on-chain state: {e}")
                continue
        
        # Commit changes
        if not dry_run and fixed_count > 0:
            db.commit()
            print(f"\n\n✅ Fixed {fixed_count} subscription(s)")
        elif dry_run:
            print(f"\n\n📊 Would fix {fixed_count} subscription(s)")
            print("\nRun without --dry-run to apply changes")
        else:
            print(f"\n\n✅ No subscriptions needed fixing")
        
        print("\n" + "="*80 + "\n")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        db.rollback()
    finally:
        db.close()


def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Fix stuck subscriptions")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without applying")
    
    args = parser.parse_args()
    
    fix_stuck_subscriptions(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
