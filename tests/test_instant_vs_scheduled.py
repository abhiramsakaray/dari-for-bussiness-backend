#!/usr/bin/env python
"""
Test script to verify instant vs scheduled refund processing modes
"""
import asyncio
import sys
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.models import Refund, RefundStatus as DBRefundStatus, PaymentSession
from app.services.refund_processor import process_all_pending_refunds
import uuid
import logging
from decimal import Decimal

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_test_refund(db: Session, time_offset_minutes: int = 0) -> str:
    """
    Create a test refund for testing purposes
    
    Args:
        db: Database session
        time_offset_minutes: How many minutes ago the refund should be marked as created
    
    Returns:
        Refund ID
    """
    try:
        # Get or create a test payment session
        test_payment = db.query(PaymentSession).filter(
            PaymentSession.id == "test-payment-001"
        ).first()
        
        if not test_payment:
            test_payment = PaymentSession(
                id="test-payment-001",
                merchant_id=uuid.uuid4(),
                token="USDC",
                chain="polygon",
                amount_fiat=Decimal(100),  # $100
                fiat_currency="USD",
                amount_token="100",
                status="PAID",
                merchant_wallet="0x1234567890123456789012345678901234567890",
                success_url="https://example.com/success",
                cancel_url="https://example.com/cancel",
                created_at=datetime.utcnow()
            )
            db.add(test_payment)
            db.commit()
        
        # Create test refund
        refund = Refund(
            id=str(uuid.uuid4()),
            payment_session_id=test_payment.id,
            merchant_id=test_payment.merchant_id,
            amount=50,
            token="USDC",
            chain="polygon",
            refund_address="0xrecipient00000000000000000000000000001",
            reason="customer_request",
            refund_source="manual",
            status=DBRefundStatus.PENDING,
            created_at=datetime.utcnow() - timedelta(minutes=time_offset_minutes)
        )
        
        db.add(refund)
        db.commit()
        
        logger.info(
            f"✅ Created test refund: {refund.id} (created {time_offset_minutes} min ago)"
        )
        return refund.id
        
    except Exception as e:
        logger.error(f"Failed to create test refund: {e}")
        raise


async def test_instant_mode():
    """Test instant mode - should process all PENDING refunds"""
    logger.info("\n" + "="*80)
    logger.info("TEST 1: INSTANT MODE (Manual Trigger)")
    logger.info("="*80)
    
    db = SessionLocal()
    try:
        # Create a fresh test refund
        refund_id = create_test_refund(db, time_offset_minutes=0)
        
        # Query to verify it exists and is PENDING
        refund = db.query(Refund).filter(Refund.id == refund_id).first()
        logger.info(f"Created refund status: {refund.status}")
        
        logger.info("\nCalling process_all_pending_refunds(mode='instant')...")
        stats = await process_all_pending_refunds(mode="instant")
        
        logger.info("\n📊 RESULTS:")
        logger.info(f"   Mode: {stats.get('processing_mode')}")
        logger.info(f"   Total pending found: {stats['total_pending']}")
        logger.info(f"   Processed: {stats['processed']}")
        logger.info(f"   Failed: {stats['failed']}")
        logger.info(f"   Skipped: {stats.get('skipped', 0)}")
        
        if stats['errors']:
            logger.error(f"   Errors: {stats['errors']}")
        
        # Verify mode is instant
        assert stats.get('processing_mode') == 'instant', "Mode should be 'instant'"
        logger.info("✅ TEST 1 PASSED: Instant mode works correctly")
        
    except AssertionError as e:
        logger.error(f"❌ TEST 1 FAILED: {e}")
    except Exception as e:
        logger.error(f"❌ TEST 1 ERROR: {e}", exc_info=True)
    finally:
        db.close()


async def test_scheduled_mode_recent_refund():
    """Test scheduled mode - should SKIP recent refunds (not stuck)"""
    logger.info("\n" + "="*80)
    logger.info("TEST 2: SCHEDULED MODE (Recent Refund - Should Skip)")
    logger.info("="*80)
    
    db = SessionLocal()
    try:
        # Create a refund that was just created (0 minutes ago)
        refund_id = create_test_refund(db, time_offset_minutes=0)
        
        logger.info("\nCalling process_all_pending_refunds(mode='scheduled', stuck_minutes=60)...")
        stats = await process_all_pending_refunds(mode="scheduled", stuck_minutes=60)
        
        logger.info("\n📊 RESULTS:")
        logger.info(f"   Mode: {stats.get('processing_mode')}")
        logger.info(f"   Total pending found: {stats['total_pending']}")
        logger.info(f"   Processed: {stats['processed']}")
        logger.info(f"   Failed: {stats['failed']}")
        logger.info(f"   Skipped: {stats.get('skipped', 0)}")
        
        if stats['errors']:
            logger.error(f"   Errors: {stats['errors']}")
        
        # Verify it was skipped (not processed)
        assert stats.get('processing_mode') == 'scheduled', "Mode should be 'scheduled'"
        assert stats['processed'] == 0, "Should not process recent refunds"
        assert stats.get('skipped', 0) > 0, "Should skip non-stuck refunds"
        logger.info("✅ TEST 2 PASSED: Scheduled mode correctly skips recent refunds")
        
    except AssertionError as e:
        logger.error(f"❌ TEST 2 FAILED: {e}")
    except Exception as e:
        logger.error(f"❌ TEST 2 ERROR: {e}", exc_info=True)
    finally:
        db.close()


async def test_scheduled_mode_stuck_refund():
    """Test scheduled mode - should PROCESS stuck refunds (>60 minutes old)"""
    logger.info("\n" + "="*80)
    logger.info("TEST 3: SCHEDULED MODE (Stuck Refund - Should Process)")
    logger.info("="*80)
    
    db = SessionLocal()
    try:
        # Create a refund that's 70 minutes old (stuck)
        refund_id = create_test_refund(db, time_offset_minutes=70)
        
        logger.info("\nCalling process_all_pending_refunds(mode='scheduled', stuck_minutes=60)...")
        stats = await process_all_pending_refunds(mode="scheduled", stuck_minutes=60)
        
        logger.info("\n📊 RESULTS:")
        logger.info(f"   Mode: {stats.get('processing_mode')}")
        logger.info(f"   Total pending found: {stats['total_pending']}")
        logger.info(f"   Processed: {stats['processed']}")
        logger.info(f"   Failed: {stats['failed']}")
        logger.info(f"   Skipped: {stats.get('skipped', 0)}")
        
        if stats['errors']:
            logger.error(f"   Errors: {stats['errors']}")
        
        # Verify mode is scheduled
        assert stats.get('processing_mode') == 'scheduled', "Mode should be 'scheduled'"
        logger.info("✅ TEST 3 PASSED: Scheduled mode correctly identifies stuck refunds")
        
    except AssertionError as e:
        logger.error(f"❌ TEST 3 FAILED: {e}")
    except Exception as e:
        logger.error(f"❌ TEST 3 ERROR: {e}", exc_info=True)
    finally:
        db.close()


async def print_current_refunds():
    """Print current refund status"""
    logger.info("\n" + "="*80)
    logger.info("CURRENT PENDING REFUNDS")
    logger.info("="*80)
    
    db = SessionLocal()
    try:
        pending_refunds = db.query(Refund).filter(
            Refund.status == DBRefundStatus.PENDING
        ).all()
        
        if not pending_refunds:
            logger.info("No pending refunds found")
        else:
            logger.info(f"Found {len(pending_refunds)} pending refunds")
            for rf in pending_refunds:
                age = datetime.utcnow() - rf.created_at if rf.created_at else None
                age_minutes = age.total_seconds() / 60 if age else None
                logger.info(
                    f"  • {rf.id}: {age_minutes:.1f}m old, "
                    f"Amount={rf.amount} {rf.token}, Chain={rf.chain}"
                )
    except Exception as e:
        logger.error(f"Error querying refunds: {e}")
    finally:
        db.close()


async def main():
    """Run all tests"""
    logger.info("\n" + "="*80)
    logger.info("🧪 REFUND PROCESSING MODE TESTS")
    logger.info("Testing instant vs scheduled processing behavior")
    logger.info("="*80)
    
    # Run tests
    await test_instant_mode()
    await print_current_refunds()
    
    await test_scheduled_mode_recent_refund()
    await print_current_refunds()
    
    await test_scheduled_mode_stuck_refund()
    await print_current_refunds()
    
    logger.info("\n" + "="*80)
    logger.info("✅ ALL TESTS COMPLETED")
    logger.info("="*80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())



async def test_instant_mode():
    """Test instant mode - should process all PENDING refunds"""
    logger.info("\n" + "="*80)
    logger.info("TEST 1: INSTANT MODE (Manual Trigger)")
    logger.info("="*80)
    
    db = SessionLocal()
    try:
        # Create a fresh test refund
        refund_id = create_test_refund(db, time_offset_minutes=0)
        
        # Query to verify it exists and is PENDING
        refund = db.query(Refund).filter(Refund.id == refund_id).first()
        logger.info(f"Created refund status: {refund.status}")
        
        logger.info("\nCalling process_all_pending_refunds(mode='instant')...")
        stats = await process_all_pending_refunds(mode="instant")
        
        logger.info("\n📊 RESULTS:")
        logger.info(f"   Mode: {stats.get('processing_mode')}")
        logger.info(f"   Total pending found: {stats['total_pending']}")
        logger.info(f"   Processed: {stats['processed']}")
        logger.info(f"   Failed: {stats['failed']}")
        logger.info(f"   Skipped: {stats.get('skipped', 0)}")
        
        if stats['errors']:
            logger.error(f"   Errors: {stats['errors']}")
        
        # Verify mode is instant
        assert stats.get('processing_mode') == 'instant', "Mode should be 'instant'"
        logger.info("✅ TEST 1 PASSED: Instant mode works correctly")
        
    except AssertionError as e:
        logger.error(f"❌ TEST 1 FAILED: {e}")
    except Exception as e:
        logger.error(f"❌ TEST 1 ERROR: {e}", exc_info=True)
    finally:
        db.close()


async def test_scheduled_mode_recent_refund():
    """Test scheduled mode - should SKIP recent refunds (not stuck)"""
    logger.info("\n" + "="*80)
    logger.info("TEST 2: SCHEDULED MODE (Recent Refund - Should Skip)")
    logger.info("="*80)
    
    db = SessionLocal()
    try:
        # Create a refund that was just created (0 minutes ago)
        refund_id = create_test_refund(db, time_offset_minutes=0)
        
        logger.info("\nCalling process_all_pending_refunds(mode='scheduled', stuck_minutes=60)...")
        stats = await process_all_pending_refunds(mode="scheduled", stuck_minutes=60)
        
        logger.info("\n📊 RESULTS:")
        logger.info(f"   Mode: {stats.get('processing_mode')}")
        logger.info(f"   Total pending found: {stats['total_pending']}")
        logger.info(f"   Processed: {stats['processed']}")
        logger.info(f"   Failed: {stats['failed']}")
        logger.info(f"   Skipped: {stats.get('skipped', 0)}")
        
        if stats['errors']:
            logger.error(f"   Errors: {stats['errors']}")
        
        # Verify it was skipped (not processed)
        assert stats.get('processing_mode') == 'scheduled', "Mode should be 'scheduled'"
        assert stats['processed'] == 0, "Should not process recent refunds"
        assert stats.get('skipped', 0) > 0, "Should skip non-stuck refunds"
        logger.info("✅ TEST 2 PASSED: Scheduled mode correctly skips recent refunds")
        
    except AssertionError as e:
        logger.error(f"❌ TEST 2 FAILED: {e}")
    except Exception as e:
        logger.error(f"❌ TEST 2 ERROR: {e}", exc_info=True)
    finally:
        db.close()


async def test_scheduled_mode_stuck_refund():
    """Test scheduled mode - should PROCESS stuck refunds (>60 minutes old)"""
    logger.info("\n" + "="*80)
    logger.info("TEST 3: SCHEDULED MODE (Stuck Refund - Should Process)")
    logger.info("="*80)
    
    db = SessionLocal()
    try:
        # Create a refund that's 70 minutes old (stuck)
        refund_id = create_test_refund(db, time_offset_minutes=70)
        
        logger.info("\nCalling process_all_pending_refunds(mode='scheduled', stuck_minutes=60)...")
        stats = await process_all_pending_refunds(mode="scheduled", stuck_minutes=60)
        
        logger.info("\n📊 RESULTS:")
        logger.info(f"   Mode: {stats.get('processing_mode')}")
        logger.info(f"   Total pending found: {stats['total_pending']}")
        logger.info(f"   Processed: {stats['processed']}")
        logger.info(f"   Failed: {stats['failed']}")
        logger.info(f"   Skipped: {stats.get('skipped', 0)}")
        
        if stats['errors']:
            logger.error(f"   Errors: {stats['errors']}")
        
        # Verify mode is scheduled
        assert stats.get('processing_mode') == 'scheduled', "Mode should be 'scheduled'"
        logger.info("✅ TEST 3 PASSED: Scheduled mode correctly identifies stuck refunds")
        
    except AssertionError as e:
        logger.error(f"❌ TEST 3 FAILED: {e}")
    except Exception as e:
        logger.error(f"❌ TEST 3 ERROR: {e}", exc_info=True)
    finally:
        db.close()


async def print_current_refunds():
    """Print current refund status"""
    logger.info("\n" + "="*80)
    logger.info("CURRENT PENDING REFUNDS")
    logger.info("="*80)
    
    db = SessionLocal()
    try:
        pending_refunds = db.query(Refund).filter(
            Refund.status == DBRefundStatus.PENDING
        ).all()
        
        if not pending_refunds:
            logger.info("No pending refunds found")
        else:
            logger.info(f"Found {len(pending_refunds)} pending refunds")
            for rf in pending_refunds:
                age = datetime.utcnow() - rf.created_at if rf.created_at else None
                age_minutes = age.total_seconds() / 60 if age else None
                logger.info(
                    f"  • {rf.id}: {age_minutes:.1f}m old, "
                    f"Amount={rf.amount} {rf.token}, Chain={rf.chain}"
                )
    except Exception as e:
        logger.error(f"Error querying refunds: {e}")
    finally:
        db.close()


async def main():
    """Run all tests"""
    logger.info("\n" + "="*80)
    logger.info("🧪 REFUND PROCESSING MODE TESTS")
    logger.info("Testing instant vs scheduled processing behavior")
    logger.info("="*80)
    
    # Run tests
    await test_instant_mode()
    await print_current_refunds()
    
    await test_scheduled_mode_recent_refund()
    await print_current_refunds()
    
    await test_scheduled_mode_stuck_refund()
    await print_current_refunds()
    
    logger.info("\n" + "="*80)
    logger.info("✅ ALL TESTS COMPLETED")
    logger.info("="*80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
