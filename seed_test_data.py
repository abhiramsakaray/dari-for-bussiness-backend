"""
Seed test data for testing the dashboard.
Creates wallets, payments, invoices, and other test data for a merchant.
"""
import sys
import os
from datetime import datetime, timedelta
from decimal import Decimal
import random

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import (
    Merchant, MerchantWallet, PaymentSession, PaymentStatus,
    BlockchainNetwork, Refund, RefundStatus as DBRefundStatus,
    Invoice, InvoiceStatus, PaymentLink, SubscriptionPlan, Subscription,
    SubscriptionStatus
)
import secrets


def generate_session_id() -> str:
    """Generate a unique session ID"""
    return f"ps_{secrets.token_urlsafe(12)}"


def generate_wallet_address(chain: str) -> str:
    """Generate a fake wallet address for testing"""
    if chain == "stellar":
        return f"G{''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ234567', k=55))}"
    elif chain in ["ethereum", "polygon", "base"]:
        return f"0x{''.join(random.choices('0123456789abcdef', k=40))}"
    elif chain == "tron":
        return f"T{''.join(random.choices('123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz', k=33))}"
    return f"ADDR_{secrets.token_hex(16)}"


def seed_test_data(merchant_email: str):
    """Seed test data for a specific merchant."""
    db = SessionLocal()
    
    try:
        # Find the merchant
        merchant = db.query(Merchant).filter(Merchant.email == merchant_email).first()
        
        if not merchant:
            print(f"❌ Merchant with email '{merchant_email}' not found.")
            print(f"   Please make sure the merchant is registered first.")
            return
        
        print(f"✅ Found merchant: {merchant.name} ({merchant.email})")
        merchant_id = merchant.id
        
        # ============= CREATE WALLETS =============
        print("\n📍 Creating wallets...")
        
        chains = [
            ("stellar", BlockchainNetwork.STELLAR),
            ("ethereum", BlockchainNetwork.ETHEREUM),
            ("polygon", BlockchainNetwork.POLYGON),
            ("base", BlockchainNetwork.BASE),
            ("tron", BlockchainNetwork.TRON),
        ]
        
        wallets_created = 0
        for chain_name, chain_enum in chains:
            # Check if wallet already exists
            existing = db.query(MerchantWallet).filter(
                MerchantWallet.merchant_id == merchant_id,
                MerchantWallet.chain == chain_enum
            ).first()
            
            if not existing:
                wallet = MerchantWallet(
                    merchant_id=merchant_id,
                    chain=chain_enum,
                    wallet_address=generate_wallet_address(chain_name),
                    is_active=True,
                )
                db.add(wallet)
                wallets_created += 1
                print(f"   ✓ Created {chain_name} wallet")
        
        db.commit()
        
        # Set balances on the Merchant object (not on individual wallets)
        if merchant.balance_usdc == 0:
            merchant.balance_usdc = Decimal(random.randint(1000, 10000))
            merchant.balance_usdt = Decimal(random.randint(500, 5000))
            merchant.balance_pyusd = Decimal(random.randint(0, 2000))
            db.commit()
            print(f"✅ Set merchant balances: USDC={merchant.balance_usdc}, USDT={merchant.balance_usdt}, PYUSD={merchant.balance_pyusd}")
        
        print(f"✅ Created {wallets_created} wallets")
        
        # ============= CREATE PAYMENT SESSIONS =============
        print("\n💳 Creating payment sessions...")
        
        payment_data = [
            # Recent paid payments
            ("paid", 50, "USD", timedelta(hours=2)),
            ("paid", 100, "USD", timedelta(hours=5)),
            ("paid", 250, "USD", timedelta(days=1)),
            ("paid", 75, "EUR", timedelta(days=1)),
            ("paid", 150, "GBP", timedelta(days=2)),
            ("paid", 1999, "INR", timedelta(days=3)),
            ("paid", 300, "USD", timedelta(days=4)),
            ("paid", 500, "USD", timedelta(days=5)),
            # Pending payments
            ("created", 125, "USD", timedelta(minutes=30)),
            ("created", 80, "EUR", timedelta(hours=1)),
            # Expired payment
            ("expired", 200, "USD", timedelta(days=10)),
        ]
        
        payments_created = 0
        for status, amount_fiat, currency, time_ago in payment_data:
            session_id = generate_session_id()
            amount_usdc = amount_fiat * Decimal("1.0")  # Simplified conversion
            
            created_at = datetime.utcnow() - time_ago
            paid_at = created_at + timedelta(minutes=random.randint(1, 30)) if status == "paid" else None
            
            payment = PaymentSession(
                id=session_id,
                merchant_id=merchant_id,
                amount_fiat=amount_fiat,
                fiat_currency=currency,
                amount_usdc=amount_usdc,
                status=PaymentStatus(status),
                success_url="https://example.com/success",
                cancel_url="https://example.com/cancel",
                created_at=created_at,
                paid_at=paid_at,
                tx_hash=f"0x{secrets.token_hex(32)}" if status == "paid" else None,
            )
            db.add(payment)
            payments_created += 1
        
        db.commit()
        print(f"✅ Created {payments_created} payment sessions")
        
        # ============= CREATE INVOICES =============
        print("\n🧾 Creating invoices...")
        
        invoice_data = [
            ("paid", 500, "USD", timedelta(days=5)),
            ("paid", 750, "USD", timedelta(days=10)),
            ("pending", 1000, "USD", timedelta(days=1)),
            ("pending", 350, "EUR", timedelta(hours=12)),
        ]
        
        invoices_created = 0
        for status_str, amount, currency, time_ago in invoice_data:
            invoice_id = f"inv_{secrets.token_urlsafe(12)}"
            created_at = datetime.utcnow() - time_ago
            
            invoice = Invoice(
                id=invoice_id,
                merchant_id=merchant_id,
                customer_email=f"customer{random.randint(1, 100)}@example.com",
                customer_name=f"Customer {random.randint(1, 100)}",
                amount=amount,
                currency=currency,
                status=InvoiceStatus(status_str),
                description=f"Test invoice for {amount} {currency}",
                due_date=created_at + timedelta(days=30),
                created_at=created_at,
            )
            db.add(invoice)
            invoices_created += 1
        
        db.commit()
        print(f"✅ Created {invoices_created} invoices")
        
        # ============= CREATE PAYMENT LINKS =============
        print("\n🔗 Creating payment links...")
        
        link_data = [
            ("Test Product 1", 99, "USD"),
            ("Monthly Service", 49, "USD"),
            ("Premium Plan", 199, "USD"),
        ]
        
        links_created = 0
        for title, amount, currency in link_data:
            link_id = f"pl_{secrets.token_urlsafe(12)}"
            
            link = PaymentLink(
                id=link_id,
                merchant_id=merchant_id,
                title=title,
                amount=amount,
                currency=currency,
                is_active=True,
                created_at=datetime.utcnow() - timedelta(days=random.randint(1, 30)),
            )
            db.add(link)
            links_created += 1
        
        db.commit()
        print(f"✅ Created {links_created} payment links")
        
        # ============= CREATE SUBSCRIPTIONS =============
        print("\n📅 Creating subscription plans...")
        
        plan_data = [
            ("Basic Plan", 29, "monthly"),
            ("Pro Plan", 99, "monthly"),
            ("Enterprise", 299, "monthly"),
        ]
        
        plans_created = 0
        for name, price, interval in plan_data:
            plan_id = f"plan_{secrets.token_urlsafe(12)}"
            
            plan = SubscriptionPlan(
                id=plan_id,
                merchant_id=merchant_id,
                name=name,
                price=price,
                currency="USD",
                interval=interval,
                is_active=True,
                created_at=datetime.utcnow() - timedelta(days=random.randint(30, 90)),
            )
            db.add(plan)
            plans_created += 1
        
        db.commit()
        print(f"✅ Created {plans_created} subscription plans")
        
        # ============= CREATE REFUNDS =============
        print("\n💸 Creating refunds...")
        
        # Get some paid payments for refunds
        paid_payments = db.query(PaymentSession).filter(
            PaymentSession.merchant_id == merchant_id,
            PaymentSession.status == PaymentStatus.PAID
        ).limit(2).all()
        
        refunds_created = 0
        for payment in paid_payments:
            refund_id = f"ref_{secrets.token_urlsafe(12)}"
            
            refund = Refund(
                id=refund_id,
                payment_session_id=payment.id,
                merchant_id=merchant_id,
                amount=payment.amount_usdc,
                reason="Customer request",
                status=DBRefundStatus.COMPLETED if random.choice([True, False]) else DBRefundStatus.PENDING,
                created_at=payment.paid_at + timedelta(days=random.randint(1, 5)),
            )
            db.add(refund)
            refunds_created += 1
        
        db.commit()
        print(f"✅ Created {refunds_created} refunds")
        
        # ============= UPDATE MERCHANT PROFILE =============
        print("\n👤 Updating merchant profile...")
        
        if not merchant.country:
            merchant.country = "US"
        if not merchant.business_name:
            merchant.business_name = merchant.name
        if not merchant.api_key:
            merchant.api_key = f"pk_live_{secrets.token_urlsafe(32)}"
        
        merchant.onboarding_completed = True
        merchant.onboarding_step = 3
        
        db.commit()
        print(f"✅ Merchant profile updated")
        
        # ============= SUMMARY =============
        print("\n" + "=" * 60)
        print("✅ TEST DATA SEEDING COMPLETE!")
        print("=" * 60)
        print(f"Merchant: {merchant.name} ({merchant.email})")
        print(f"  - Wallets: {wallets_created} created")
        print(f"  - Payment Sessions: {payments_created} created")
        print(f"  - Invoices: {invoices_created} created")
        print(f"  - Payment Links: {links_created} created")
        print(f"  - Subscription Plans: {plans_created} created")
        print(f"  - Refunds: {refunds_created} created")
        print("\n💡 You can now test the dashboard with real-looking data!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Error seeding test data: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    # Get merchant email from command line or use default
    merchant_email = sys.argv[1] if len(sys.argv) > 1 else "abhiram@dariorganization.com"
    
    print("=" * 60)
    print("🌱 SEEDING TEST DATA")
    print("=" * 60)
    print(f"Target merchant: {merchant_email}\n")
    
    seed_test_data(merchant_email)
