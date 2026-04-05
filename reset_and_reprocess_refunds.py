#!/usr/bin/env python
"""
Reset failed refunds and reprocess them
"""
import asyncio
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from app.core.database import SessionLocal
from app.models.models import Refund, RefundStatus as DBRefundStatus
from app.services.refund_processor import process_all_pending_refunds
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def reset_and_reprocess():
    """Reset failed refunds and reprocess them immediately"""
    db = SessionLocal()
    try:
        # Find the failed refunds
        failed_refunds = db.query(Refund).filter(
            Refund.id.in_([
                "ref_7S27vsN9r7tWMB8D",
                "ref_qvgt2tak4tOwCm7i"
            ])
        ).all()
        
        logger.info(f"Found {len(failed_refunds)} refunds to reset")
        
        for refund in failed_refunds:
            logger.info(f"\n🔄 Resetting refund {refund.id}")
            logger.info(f"   Old TX Hash: {refund.tx_hash}")
            logger.info(f"   Old Status: {refund.status.value}")
            
            # Reset to pending
            refund.tx_hash = None
            refund.status = DBRefundStatus.PENDING
            refund.completed_at = None
            refund.failure_reason = "Recovery: Reset fake tx_hash and reprocessing"
            
            logger.info(f"   New Status: {refund.status.value}")
        
        db.commit()
        logger.info(f"\n✅ Reset {len(failed_refunds)} refunds to PENDING\n")
        
        # Now reprocess in instant mode
        logger.info("="*80)
        logger.info("Reprocessing refunds INSTANTLY...")
        logger.info("="*80 + "\n")
        
        stats = await process_all_pending_refunds(mode="instant")
        
        logger.info("\n" + "="*80)
        logger.info("📊 REPROCESSING RESULTS:")
        logger.info("="*80)
        logger.info(f"Mode: {stats.get('processing_mode')}")
        logger.info(f"Total pending: {stats['total_pending']}")
        logger.info(f"Successfully processed: {stats['processed']}")
        logger.info(f"Failed: {stats['failed']}")
        
        if stats['errors']:
            logger.error(f"Errors: {stats['errors']}")
        else:
            logger.info("✅ No errors!")
        
        logger.info("="*80 + "\n")
        
        # Show updated refunds
        for refund_id in ["ref_7S27vsN9r7tWMB8D", "ref_qvgt2tak4tOwCm7i"]:
            updated = db.query(Refund).filter(Refund.id == refund_id).first()
            if updated:
                logger.info(f"📋 Updated {updated.id}:")
                logger.info(f"   Status: {updated.status.value}")
                logger.info(f"   TX Hash: {updated.tx_hash}")
                logger.info(f"   Completed At: {updated.completed_at}")
        
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(reset_and_reprocess())
