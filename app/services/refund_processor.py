"""
Refund Processor Service
Handles sending refunds on-chain via appropriate blockchain relayers
"""
import logging
import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.models import Refund, PaymentSession, RefundStatus as DBRefundStatus, PaymentEvent
from app.services.webhook_service import send_refund_webhook
from app.services.blockchain_relayer import relayer_service
import uuid

logger = logging.getLogger(__name__)


async def process_refund_on_chain(refund_id: str, merchant_id: str) -> bool:
    """
    Process a refund by sending it on-chain to the customer's wallet.
    
    Args:
        refund_id: ID of the refund to process
        merchant_id: ID of the merchant (for logging)
    
    Returns:
        True if successful, False if failed
    """
    db = SessionLocal()
    try:
        # Get the refund
        refund = db.query(Refund).filter(Refund.id == refund_id).first()
        if not refund:
            logger.error(f"Refund {refund_id} not found")
            return False
        
        # Get the payment session for token and chain info
        payment = db.query(PaymentSession).filter(
            PaymentSession.id == refund.payment_session_id
        ).first()
        
        if not payment:
            logger.error(f"Payment {refund.payment_session_id} not found for refund {refund_id}")
            refund.status = DBRefundStatus.FAILED
            refund.failure_reason = "Associated payment not found"
            db.commit()
            
            # Send failure webhook
            try:
                await send_refund_webhook(refund, db)
            except Exception as e:
                logger.error(f"Failed to send refund webhook for {refund_id}: {e}")
            
            return False
        
        # Validate refund has required fields
        # Note: refund_address may be optional for certain chains (e.g., Stellar)
        # that have alternative ways to retrieve the recipient address
        if not refund.refund_address:
            # Try to get address from session metadata or chain-specific sources
            payment_session = db.query(PaymentSession).filter(
                PaymentSession.id == refund.payment_session_id
            ).first()
            
            if payment_session:
                # For Stellar: check session metadata for wallet info
                if refund.chain and refund.chain.lower() == "stellar":
                    if payment_session.session_metadata and isinstance(payment_session.session_metadata, dict):
                        metadata_addr = payment_session.session_metadata.get("stellar_address") or \
                                      payment_session.session_metadata.get("wallet_address") or \
                                      payment_session.session_metadata.get("payer_address")
                        if metadata_addr:
                            refund.refund_address = metadata_addr
                            logger.info(f"Refund {refund_id}: Retrieved Stellar address from session metadata: {metadata_addr[:20]}...")
            
            # If still no address, fail the refund
            if not refund.refund_address:
                logger.error(f"Refund {refund_id} missing recipient wallet address for chain: {refund.chain}")
                refund.status = DBRefundStatus.FAILED
                refund.failure_reason = f"Recipient wallet address not specified (required for {refund.chain} refunds)"
                db.commit()
                
                # Send failure webhook
                try:
                    await send_refund_webhook(refund, db)
                except Exception as e:
                    logger.error(f"Failed to send refund webhook for {refund_id}: {e}")
                
                return False
        
        logger.info(
            f"🔄 Processing refund {refund_id}: "
            f"Amount={refund.amount} {refund.token}, "
            f"Chain={refund.chain}, "
            f"To={refund.refund_address}, "
            f"Source={refund.refund_source}"
        )
        
        # Update status to PROCESSING
        refund.status = DBRefundStatus.PROCESSING
        db.commit()
        
        # Route to appropriate blockchain processor based on chain via relayer
        tx_hash = None
        logger.info(f"🔗 Sending refund via {refund.chain.upper()} relayer...")
        
        if refund.chain.lower() in ["polygon", "stellar", "solana", "soroban", "tron"]:
            tx_hash = await relayer_service.send_refund(
                chain=refund.chain,
                token=refund.token,
                amount=refund.amount,
                to_address=refund.refund_address,
                refund_id=refund_id
            )
        else:
            logger.error(f"Unsupported chain for refund {refund_id}: {refund.chain}")
            refund.status = DBRefundStatus.FAILED
            refund.failure_reason = f"Unsupported blockchain: {refund.chain}"
            db.commit()
            
            # Send failure webhook
            try:
                await send_refund_webhook(refund, db)
            except Exception as e:
                logger.error(f"Failed to send refund webhook for {refund_id}: {e}")
            
            return False
        
        # Update refund with transaction hash
        if tx_hash:
            refund.tx_hash = tx_hash
            refund.status = DBRefundStatus.COMPLETED
            refund.completed_at = datetime.utcnow()
            logger.info(f"✅ Refund {refund_id} completed with tx_hash: {tx_hash}")
            db.commit()
            
            # Log transaction event for audit trail (skip if table issues)
            try:
                event = PaymentEvent(
                    session_id=str(refund.payment_session_id),
                    event_type="refund.completed",
                    details={
                        "refund_id": refund_id,
                        "amount": str(refund.amount),
                        "token": refund.token,
                        "chain": refund.chain,
                        "recipient": refund.refund_address,
                        "tx_hash": tx_hash,
                        "reason": refund.reason
                    }
                )
                db.add(event)
                db.commit()
            except Exception as e:
                logger.warning(f"⚠️  Failed to log refund.completed event: {e}")
                # Don't fail the whole refund if event logging fails
                db.rollback()
            
            # Send completion webhook
            try:
                await send_refund_webhook(refund, db)
            except Exception as e:
                logger.error(f"Failed to send refund webhook for {refund_id}: {e}")
        else:
            refund.status = DBRefundStatus.FAILED
            refund.failure_reason = "Transaction failed to send on-chain"
            logger.error(f"❌ Refund {refund_id} failed: could not get transaction hash")
            db.commit()
            
            # Log transaction event for failure (skip if table issues)
            try:
                event = PaymentEvent(
                    session_id=str(refund.payment_session_id),
                    event_type="refund.failed",
                    details={
                        "refund_id": refund_id,
                        "reason": "Transaction failed to send on-chain",
                        "amount": str(refund.amount),
                        "token": refund.token,
                        "chain": refund.chain
                    }
                )
                db.add(event)
                db.commit()
            except Exception as e:
                logger.error(f"Failed to log transaction event: {e}")
            
            # Send failure webhook
            try:
                await send_refund_webhook(refund, db)
            except Exception as e:
                logger.error(f"Failed to send refund webhook for {refund_id}: {e}")
        
        return tx_hash is not None
        
    except Exception as e:
        logger.error(f"❌ Error processing refund {refund_id}: {str(e)}", exc_info=True)
        try:
            refund = db.query(Refund).filter(Refund.id == refund_id).first()
            if refund:
                refund.status = DBRefundStatus.FAILED
                refund.failure_reason = f"Processing error: {str(e)}"
                db.commit()
                
                # Send failure webhook
                try:
                    await send_refund_webhook(refund, db)
                except:
                    pass
        except:
            pass
        return False
    
    finally:
        db.close()





async def process_all_pending_refunds(mode: str = "instant", stuck_minutes: int = 60) -> dict:
    """
    Process PENDING refunds in the database.
    
    Args:
        mode: "instant" to process all PENDING, or "scheduled" to only process stuck ones
        stuck_minutes: Time threshold (in minutes) for considering a refund "stuck" (only for scheduled mode)
    
    Returns:
        Dictionary with statistics:
        {
            'total_pending': int,
            'processed': int,
            'failed': int,
            'skipped': int,  # Only in scheduled mode
            'processing_mode': str,
            'errors': List[str]
        }
    """
    db = SessionLocal()
    stats = {
        'total_pending': 0,
        'processed': 0,
        'failed': 0,
        'skipped': 0,
        'processing_mode': mode,
        'errors': []
    }
    
    try:
        # Get all pending refunds
        pending_refunds = db.query(Refund).filter(
            Refund.status == DBRefundStatus.PENDING
        ).all()
        
        stats['total_pending'] = len(pending_refunds)
        
        if mode == "instant":
            logger.info(f"⚡ [INSTANT MODE] Found {len(pending_refunds)} pending refunds to process immediately")
        else:
            logger.info(f"🔄 [SCHEDULED MODE] Found {len(pending_refunds)} total pending refunds - filtering for stuck ones")
        
        # Process each refund
        for refund in pending_refunds:
            try:
                # For scheduled mode, only process refunds older than threshold
                if mode == "scheduled":
                    if refund.created_at:
                        time_pending = datetime.utcnow() - refund.created_at
                        minutes_pending = time_pending.total_seconds() / 60
                        
                        if minutes_pending < stuck_minutes:
                            logger.info(
                                f"⏭️  [SCHEDULED] Skipping refund {refund.id} - only {minutes_pending:.1f}m pending "
                                f"(threshold: {stuck_minutes}m)"
                            )
                            stats['skipped'] += 1
                            continue
                        else:
                            logger.info(
                                f"🔧 [SCHEDULED] Processing stuck refund {refund.id} - {minutes_pending:.1f}m pending "
                                f"(threshold: {stuck_minutes}m)"
                            )
                    else:
                        logger.warning(f"⚠️  [SCHEDULED] Refund {refund.id} has no created_at timestamp")
                        stats['skipped'] += 1
                        continue
                else:
                    logger.info(f"⏳ [INSTANT] Processing refund {refund.id}...")
                
                success = await process_refund_on_chain(refund.id, str(refund.merchant_id))
                
                if success:
                    stats['processed'] += 1
                    logger.info(f"✅ Successfully processed refund {refund.id}")
                else:
                    stats['failed'] += 1
                    error_msg = f"Refund {refund.id} failed to process"
                    stats['errors'].append(error_msg)
                    logger.error(error_msg)
                    
            except Exception as e:
                stats['failed'] += 1
                error_msg = f"Error processing refund {refund.id}: {str(e)}"
                stats['errors'].append(error_msg)
                logger.error(error_msg, exc_info=True)
        
        if mode == "instant":
            logger.info(
                f"✅ [INSTANT MODE] Complete: {stats['processed']} processed, {stats['failed']} failed"
            )
        else:
            logger.info(
                f"✅ [SCHEDULED MODE] Complete: {stats['processed']} processed, "
                f"{stats['failed']} failed, {stats['skipped']} skipped (not stuck yet)"
            )
        
    except Exception as e:
        error_msg = f"Critical error in process_all_pending_refunds: {str(e)}"
        stats['errors'].append(error_msg)
        logger.error(error_msg, exc_info=True)
    
    finally:
        db.close()
    
    return stats


# Import datetime for processed_at timestamp
from datetime import datetime
