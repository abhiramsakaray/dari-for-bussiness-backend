"""
Subscription Diagnostic Tool

Analyzes Web3 subscriptions to identify issues with recurring payments.
Checks on-chain state vs database state and provides actionable insights.

Usage:
    python scripts/diagnose_subscriptions.py
    python scripts/diagnose_subscriptions.py --subscription-id <uuid>
    python scripts/diagnose_subscriptions.py --merchant-id <uuid>
"""

import sys
import os
import asyncio
from datetime import datetime, timedelta
from decimal import Decimal

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.models import Web3Subscription, Web3SubscriptionStatus
from app.services.gasless_relayer import relayer
from sqlalchemy import and_


def format_timestamp(dt):
    """Format datetime for display"""
    if not dt:
        return "N/A"
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def check_subscription_health(db, sub):
    """Check a single subscription's health"""
    print(f"\n{'='*80}")
    print(f"Subscription ID: {sub.id}")
    print(f"{'='*80}")
    
    # Basic info
    print(f"\n📋 Basic Info:")
    print(f"  Chain: {sub.chain}")
    print(f"  On-chain ID: {sub.onchain_subscription_id}")
    print(f"  Status: {sub.status.value}")
    print(f"  Subscriber: {sub.subscriber_address}")
    print(f"  Merchant: {sub.merchant_address}")
    print(f"  Token: {sub.token_symbol}")
    print(f"  Amount: {sub.amount}")
    print(f"  Interval: {sub.interval_seconds}s ({sub.interval_seconds // 86400}d)")
    
    # Timing info
    print(f"\n⏰ Timing:")
    print(f"  Created: {format_timestamp(sub.created_at)}")
    print(f"  Next Payment: {format_timestamp(sub.next_payment_at)}")
    now = datetime.utcnow()
    if sub.next_payment_at:
        delta = (sub.next_payment_at - now).total_seconds()
        if delta > 0:
            print(f"  Time Until Due: {int(delta)}s ({delta/3600:.1f}h)")
        else:
            print(f"  Overdue By: {int(-delta)}s ({-delta/3600:.1f}h)")
    
    # Payment history
    print(f"\n💰 Payment History:")
    print(f"  Total Payments: {sub.total_payments}")
    print(f"  Total Collected: {sub.total_amount_collected} {sub.token_symbol}")
    print(f"  Failed Count: {sub.failed_payment_count}")
    if sub.first_failed_at:
        print(f"  First Failed: {format_timestamp(sub.first_failed_at)}")
        hours_past_due = (now - sub.first_failed_at).total_seconds() / 3600
        print(f"  Hours Past Due: {hours_past_due:.1f}h")
    
    # Grace period
    print(f"\n⏳ Grace Period:")
    grace_days = sub.grace_period_days or 3
    print(f"  Grace Period: {grace_days} days ({grace_days * 24}h)")
    if sub.first_failed_at:
        hours_past_due = (now - sub.first_failed_at).total_seconds() / 3600
        grace_hours = grace_days * 24
        remaining = grace_hours - hours_past_due
        if remaining > 0:
            print(f"  Grace Remaining: {remaining:.1f}h")
        else:
            print(f"  Grace Exceeded By: {-remaining:.1f}h")
    
    # On-chain state
    if sub.onchain_subscription_id:
        print(f"\n⛓️  On-Chain State:")
        try:
            onchain = relayer.get_onchain_subscription(sub.chain, sub.onchain_subscription_id)
            print(f"  Active: {onchain['active']}")
            print(f"  Payment Count: {onchain['paymentCount']}")
            print(f"  Next Payment: {datetime.utcfromtimestamp(onchain['nextPayment'])}")
            print(f"  Amount: {onchain['amount']}")
            
            # Check for mismatches
            print(f"\n🔍 State Validation:")
            db_active = sub.status in (Web3SubscriptionStatus.ACTIVE, Web3SubscriptionStatus.PAST_DUE, Web3SubscriptionStatus.PENDING_PAYMENT)
            if db_active != onchain['active']:
                print(f"  ⚠️  STATUS MISMATCH: DB={sub.status.value}, Chain={onchain['active']}")
            else:
                print(f"  ✅ Status matches")
            
            if sub.total_payments != onchain['paymentCount']:
                print(f"  ⚠️  PAYMENT COUNT MISMATCH: DB={sub.total_payments}, Chain={onchain['paymentCount']}")
            else:
                print(f"  ✅ Payment count matches")
            
            # Check if payment is due on-chain
            is_due = relayer.is_payment_due_onchain(sub.chain, sub.onchain_subscription_id)
            print(f"  Payment Due On-Chain: {is_due}")
            
        except Exception as e:
            print(f"  ❌ Error reading on-chain state: {e}")
    
    # Issues and recommendations
    print(f"\n🔧 Diagnosis:")
    issues = []
    recommendations = []
    
    # Check 1: Stuck in PENDING_PAYMENT
    if sub.status == Web3SubscriptionStatus.PENDING_PAYMENT:
        age_hours = (now - sub.created_at).total_seconds() / 3600
        if age_hours > 1:
            issues.append(f"Stuck in PENDING_PAYMENT for {age_hours:.1f}h")
            recommendations.append("First payment may have failed. Check relayer logs.")
    
    # Check 2: Overdue but not PAST_DUE
    if sub.status == Web3SubscriptionStatus.ACTIVE and sub.next_payment_at and sub.next_payment_at < now:
        overdue_hours = (now - sub.next_payment_at).total_seconds() / 3600
        if overdue_hours > 1:
            issues.append(f"Payment overdue by {overdue_hours:.1f}h but status is ACTIVE")
            recommendations.append("Scheduler may not be running or picking up this subscription")
    
    # Check 3: Grace period exceeded but not PAUSED
    if sub.first_failed_at and sub.status != Web3SubscriptionStatus.PAUSED:
        hours_past_due = (now - sub.first_failed_at).total_seconds() / 3600
        grace_hours = (sub.grace_period_days or 3) * 24
        if hours_past_due > grace_hours:
            issues.append(f"Grace period exceeded by {hours_past_due - grace_hours:.1f}h but not PAUSED")
            recommendations.append("Should be automatically paused by scheduler")
    
    # Check 4: No on-chain ID
    if not sub.onchain_subscription_id:
        issues.append("No on-chain subscription ID")
        recommendations.append("Subscription creation may have failed. Check created_tx_hash.")
    
    # Check 5: High failure count
    if sub.failed_payment_count >= 3:
        issues.append(f"High failure count: {sub.failed_payment_count}")
        recommendations.append("Check subscriber wallet balance and token allowance")
    
    if issues:
        print(f"  ⚠️  Issues Found:")
        for issue in issues:
            print(f"    - {issue}")
    else:
        print(f"  ✅ No issues detected")
    
    if recommendations:
        print(f"\n💡 Recommendations:")
        for rec in recommendations:
            print(f"    - {rec}")
    
    print(f"\n{'='*80}\n")


def main():
    """Main diagnostic function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Diagnose Web3 subscription issues")
    parser.add_argument("--subscription-id", help="Check specific subscription by ID")
    parser.add_argument("--merchant-id", help="Check all subscriptions for a merchant")
    parser.add_argument("--status", help="Filter by status (active, past_due, pending_payment, paused)")
    parser.add_argument("--all", action="store_true", help="Check all subscriptions")
    
    args = parser.parse_args()
    
    db = SessionLocal()
    
    try:
        print("\n" + "="*80)
        print("WEB3 SUBSCRIPTION DIAGNOSTIC TOOL")
        print("="*80)
        
        # Build query
        query = db.query(Web3Subscription)
        
        if args.subscription_id:
            query = query.filter(Web3Subscription.id == args.subscription_id)
        elif args.merchant_id:
            query = query.filter(Web3Subscription.merchant_id == args.merchant_id)
        elif args.status:
            status_map = {
                "active": Web3SubscriptionStatus.ACTIVE,
                "past_due": Web3SubscriptionStatus.PAST_DUE,
                "pending_payment": Web3SubscriptionStatus.PENDING_PAYMENT,
                "paused": Web3SubscriptionStatus.PAUSED,
                "cancelled": Web3SubscriptionStatus.CANCELLED,
            }
            if args.status.lower() in status_map:
                query = query.filter(Web3Subscription.status == status_map[args.status.lower()])
        elif not args.all:
            # Default: show problematic subscriptions
            query = query.filter(
                Web3Subscription.status.in_([
                    Web3SubscriptionStatus.PENDING_PAYMENT,
                    Web3SubscriptionStatus.PAST_DUE,
                ])
            )
        
        subscriptions = query.order_by(Web3Subscription.created_at.desc()).limit(50).all()
        
        if not subscriptions:
            print("\n❌ No subscriptions found matching criteria")
            return
        
        print(f"\n📊 Found {len(subscriptions)} subscription(s)\n")
        
        for sub in subscriptions:
            check_subscription_health(db, sub)
        
        # Summary statistics
        print("\n" + "="*80)
        print("SUMMARY STATISTICS")
        print("="*80)
        
        all_subs = db.query(Web3Subscription).all()
        total = len(all_subs)
        
        status_counts = {}
        for sub in all_subs:
            status = sub.status.value
            status_counts[status] = status_counts.get(status, 0) + 1
        
        print(f"\nTotal Subscriptions: {total}")
        print(f"\nBy Status:")
        for status, count in sorted(status_counts.items()):
            pct = (count / total * 100) if total > 0 else 0
            print(f"  {status}: {count} ({pct:.1f}%)")
        
        # Overdue subscriptions
        now = datetime.utcnow()
        overdue = [s for s in all_subs if s.next_payment_at and s.next_payment_at < now and s.status in (Web3SubscriptionStatus.ACTIVE, Web3SubscriptionStatus.PENDING_PAYMENT)]
        if overdue:
            print(f"\n⚠️  {len(overdue)} subscription(s) overdue but not PAST_DUE")
        
        # Stuck in PENDING_PAYMENT
        stuck = [s for s in all_subs if s.status == Web3SubscriptionStatus.PENDING_PAYMENT and (now - s.created_at).total_seconds() > 3600]
        if stuck:
            print(f"⚠️  {len(stuck)} subscription(s) stuck in PENDING_PAYMENT > 1h")
        
        print("\n" + "="*80 + "\n")
        
    finally:
        db.close()


if __name__ == "__main__":
    main()
