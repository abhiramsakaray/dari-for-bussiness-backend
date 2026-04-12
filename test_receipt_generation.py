"""
Test Receipt Generation

Quick test script to verify receipt generation works.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.database import SessionLocal
from app.models.models import PaymentSession, PaymentStatus
from app.services.receipt_service import ReceiptService


def test_receipt_generation():
    """Test receipt generation for a paid payment"""
    print("\n" + "="*80)
    print("RECEIPT GENERATION TEST")
    print("="*80)
    
    db = SessionLocal()
    
    try:
        # Find a paid payment
        paid_payment = db.query(PaymentSession).filter(
            PaymentSession.status.in_([PaymentStatus.PAID, PaymentStatus.CONFIRMED])
        ).first()
        
        if not paid_payment:
            print("\n❌ No paid payments found in database")
            print("Please make a test payment first")
            return
        
        print(f"\n📋 Found paid payment:")
        print(f"  Session ID: {paid_payment.id}")
        print(f"  Amount: ${paid_payment.amount_fiat} {paid_payment.fiat_currency}")
        print(f"  Status: {paid_payment.status.value}")
        print(f"  Chain: {paid_payment.chain}")
        print(f"  Token: {paid_payment.token}")
        print(f"  TX Hash: {paid_payment.tx_hash}")
        
        # Generate receipt
        print(f"\n🔄 Generating receipt...")
        service = ReceiptService(db)
        receipt = service.generate_receipt_for_payment(paid_payment.id)
        
        if not receipt:
            print("❌ Failed to generate receipt")
            return
        
        print(f"\n✅ Receipt generated successfully!")
        print(f"  Receipt ID: {receipt.id}")
        print(f"  Invoice Number: {receipt.invoice_number}")
        print(f"  Customer: {receipt.customer_name} ({receipt.customer_email})")
        print(f"  Amount: ${receipt.total} {receipt.fiat_currency}")
        print(f"  Status: {receipt.status.value}")
        
        # Generate PDF
        print(f"\n🔄 Generating PDF...")
        pdf_buffer = service.generate_pdf(receipt.id)
        
        if not pdf_buffer:
            print("❌ Failed to generate PDF")
            return
        
        # Save PDF to file
        filename = f"test_receipt_{receipt.invoice_number}.pdf"
        with open(filename, 'wb') as f:
            f.write(pdf_buffer.getvalue())
        
        print(f"\n✅ PDF generated successfully!")
        print(f"  File: {filename}")
        print(f"  Size: {len(pdf_buffer.getvalue())} bytes")
        
        # API URLs
        print(f"\n📡 API Endpoints:")
        print(f"  Download: GET /receipts/{receipt.id}/download")
        print(f"  View: GET /receipts/{receipt.id}/view")
        print(f"  Details: GET /receipts/{receipt.id}")
        
        print(f"\n" + "="*80)
        print("✅ ALL TESTS PASSED!")
        print("="*80)
        print(f"\nYou can now:")
        print(f"1. Open {filename} to view the PDF")
        print(f"2. Use the API endpoints to download/view from frontend")
        print(f"3. Add receipt generation buttons to your payment details page")
        print()
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    test_receipt_generation()
