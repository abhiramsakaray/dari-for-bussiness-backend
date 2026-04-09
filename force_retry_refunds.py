#!/usr/bin/env python
"""
Force retry completed refunds that failed on-chain
"""
import asyncio
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(__file__))

from app.core.database import SessionLocal
from app.models.models import Refund, RefundStatus as DBRefundStatus
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def force_retry_failed_refunds():
    """
    Find COMPLETED refunds that appear to have failed on-chain and retry them.
    
    These are refunds that show as COMPLETED but the tx_hash might not be real.
    """
    db = SessionLocal()
    try:
        # Find all COMPLETED refunds
        completed_refunds = db.query(Refund).filter(
            Refund.status == DBRefundStatus.COMPLETED
        ).all()
        
        logger.info(f"Found {len(completed_refunds)} COMPLETED refunds")
        
        if not completed_refunds:
            logger.info("No completed refunds to retry")
            return
        
        # List them for inspection
        for refund in completed_refunds:
            logger.info(
                f"\n📋 Refund: {refund.id}"
                f"\n   Status: {refund.status.value}"
                f"\n   Amount: {refund.amount} {refund.token}"
                f"\n   Chain: {refund.chain}"
                f"\n   To: {refund.refund_address}"
                f"\n   TX Hash: {refund.tx_hash}"
                f"\n   Completed At: {refund.completed_at}"
                f"\n   Created At: {refund.created_at}"
            )
        
        # Ask which ones to retry
        logger.info("\n" + "="*80)
        logger.info("To retry specific refunds, use the API endpoint:")
        logger.info("  POST /refunds/{refund_id}/force-retry")
        logger.info("  Authorization: Bearer {merchant_token}")
        logger.info("\nExample:")
        for refund in completed_refunds[:2]:
            logger.info(f"  curl -X POST http://127.0.0.1:8003/refunds/{refund.id}/force-retry \\")
            logger.info(f"    -H 'Authorization: Bearer $TOKEN' \\")
            logger.info(f"    -H 'X-Request-Nonce: xxxxxx' \\")
            logger.info(f"    -H 'X-Request-Timestamp: xxxxxx'")
        logger.info("="*80)
        
    finally:
        db.close()


if __name__ == "__main__":
    force_retry_failed_refunds()
