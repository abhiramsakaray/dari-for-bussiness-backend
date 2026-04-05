#!/usr/bin/env python3
"""
Fix Stellar refund with missing recipient address

Issue: ref_vhH2q6npGcfp_Y6x has no refund_address specified
Solution: Update address via API and trigger reprocessing

To use this script, you need:
1. The merchant's API key for authentication
2. The customer's Stellar refund address (must be obtained from customer)
"""

import os
import sys
import logging
from decimal import Decimal

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    """Show steps to fix the Stellar refund"""
    
    refund_id = "ref_vhH2q6npGcfp_Y6x"
    
    logger.info("=" * 80)
    logger.info("Stellar Refund Recovery Process")
    logger.info("=" * 80)
    
    logger.info(f"\nRefund ID: {refund_id}")
    logger.info("Status: FAILED")
    logger.info("Reason: Recipient wallet address not specified")
    logger.info("Chain: Stellar")
    logger.info("Amount: 1.000000 USDC")
    
    logger.info("\n🔧 SOLUTION:")
    logger.info("-" * 80)
    
    logger.info("\nStep 1: Contact the customer to get their Stellar wallet address")
    logger.info("  - Email: (check payment_sessions.payer_email)")
    logger.info("  - Ask: 'What is your Stellar wallet address to receive the refund?'")
    logger.info("  - Expected format: G... (e.g., GBBD47UZQ5LAeluc4ENTDVRPA6EOBJQJBQS7OCVLUF57XAUBRMAKAFI)")
    
    logger.info("\nStep 2: Once you have the Stellar address, call the PATCH endpoint:")
    logger.info("")
    logger.info("  PATCH /refunds/{refund_id}/update-address")
    logger.info("  Query Parameters:")
    logger.info("    - refund_address=<stellar_address>")
    logger.info("")
    logger.info("  Example curl:")
    logger.info(f"""
  curl -X PATCH 'http://localhost:8003/refunds/{refund_id}/update-address' \\
    -H 'Authorization: Bearer <MERCHANT_API_KEY>' \\
    -H 'Content-Type: application/json' \\
    -d '{{"refund_address": "GBBD47UZQ5LAELUC4ENTDVRPA6EOBJQJBQS7OCVLUF57XAUBRMAKAFI"}}'
    """)
    
    logger.info("\nStep 3: Backend response (if successful):")
    logger.info("""
  {{
    "message": "Refund address updated and reset to PENDING",
    "id": "ref_vhH2q6npGcfp_Y6x",
    "previous_address": "(empty)",
    "new_address": "GBBD47UZQ5LAELUC4ENTDVRPA6EOBJQJBQS7OCVLUF57XAUBRMAKAFI",
    "new_status": "PENDING"
  }}
    """)
    
    logger.info("\nStep 4: Refund will be automatically reprocessed")
    logger.info("  - Status will remain PENDING")
    logger.info("  - Scheduler (or instant trigger) will process it")
    logger.info("  - Real USDC will be sent to Stellar address")
    logger.info("  - Transaction hash will be stored")
    
    logger.info("\n" + "=" * 80)
    logger.info("✅ Recovery workflow complete")
    logger.info("=" * 80)
    
    # Show current refund details
    logger.info("\n📋 Current Refund Details:")
    logger.info("-" * 80)
    
    sys.path.insert(0, '.')
    os.environ['ENV'] = 'dev'
    
    from app.core.database import SessionLocal
    from app.models.models import Refund, PaymentSession
    
    db = SessionLocal()
    
    try:
        refund = db.query(Refund).filter(Refund.id == refund_id).first()
        if refund:
            session = db.query(PaymentSession).filter(
                PaymentSession.id == refund.payment_session_id
            ).first()
            
            logger.info(f"ID: {refund.id}")
            logger.info(f"Payment Session: {refund.payment_session_id}")
            logger.info(f"Amount: {refund.amount} {refund.token}")
            logger.info(f"Chain: {refund.chain}")
            logger.info(f"Refund Address: [{refund.refund_address}]  (EMPTY)")
            logger.info(f"Status: {refund.status.value}")
            logger.info(f"Reason: {refund.reason}")
            logger.info(f"Failure Reason: {refund.failure_reason}")
            logger.info(f"Created: {refund.created_at}")
            
            if session:
                logger.info(f"\nPayment Details:")
                logger.info(f"  Payer Email: {session.payer_email}")
                logger.info(f"  Payer Name: {session.payer_name}")
                logger.info(f"  Order ID: {session.order_id}")
        else:
            logger.error(f"Refund {refund_id} not found!")
    
    finally:
        db.close()


if __name__ == "__main__":
    main()
