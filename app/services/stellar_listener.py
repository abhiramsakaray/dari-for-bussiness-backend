import asyncio
import logging
from datetime import datetime
from typing import Optional
from stellar_sdk import Server, Asset
from stellar_sdk.exceptions import BaseHorizonError
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.core.config import settings
from app.models import PaymentSession, PaymentStatus
from app.services.webhook_service import send_webhook
import time
from requests.exceptions import ConnectionError, Timeout, ReadTimeout

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class StellarPaymentListener:
    """
    Background service to listen for USDC payments on the Stellar network.
    """
    
    def __init__(self):
        self.server = Server(horizon_url=settings.STELLAR_HORIZON_URL)
        self.usdc_asset = Asset(
            code=settings.USDC_ASSET_CODE,
            issuer=settings.USDC_ASSET_ISSUER
        )
        self.is_running = False
        self.cursor = "now"  # Start from current ledger
    
    def get_db(self) -> Session:
        """Get database session."""
        return SessionLocal()
    
    async def validate_and_process_payment(
        self,
        tx_hash: str,
        destination: str,
        amount: str,
        memo: Optional[str],
        asset: Asset
    ):
        """
        Validate payment and update payment session if valid.
        Supports both USDC and XLM payments.
        """
        db = self.get_db()
        try:
            # Validate memo exists
            if not memo:
                logger.info(f"Payment {tx_hash} has no memo, skipping")
                return
            
            # Find payment session by memo (session_id)
            session = db.query(PaymentSession).filter(
                PaymentSession.id == memo
            ).first()
            
            if not session:
                logger.info(f"No payment session found for memo: {memo}")
                return
            
            # Check if session is already paid
            if session.status == PaymentStatus.PAID:
                logger.info(f"Session {memo} already marked as paid, skipping")
                return
            
            # Validate destination address matches merchant
            if destination != session.merchant.stellar_address:
                logger.warning(
                    f"Payment destination {destination} does not match merchant address "
                    f"{session.merchant.stellar_address} for session {memo}"
                )
                return
            
            # Determine if payment is USDC or XLM
            is_usdc = (asset.code == self.usdc_asset.code and 
                      asset.issuer == self.usdc_asset.issuer)
            is_xlm = asset.is_native()  # Native XLM
            
            logger.info(f"🔍 Asset check: is_usdc={is_usdc}, is_xlm={is_xlm}, asset={asset}")
            
            if not (is_usdc or is_xlm):
                logger.info(f"Payment {tx_hash} is neither USDC nor XLM, skipping")
                return
            
            # Validate amount
            expected_amount = float(session.amount_usdc)
            received_amount = float(amount)
            
            # For XLM, convert expected USDC amount to XLM (using 1:10 ratio)
            # In production, use real-time exchange rate
            if is_xlm:
                expected_amount = expected_amount * 10  # 1 USDC ≈ 10 XLM (placeholder)
                asset_type = "XLM"
            else:
                asset_type = "USDC"
            
            # Allow small difference for rounding (0.01)
            if abs(received_amount - expected_amount) > 0.01:
                logger.warning(
                    f"Payment amount mismatch for session {memo}. "
                    f"Expected: {expected_amount} {asset_type}, Received: {received_amount} {asset_type}"
                )
                return
            
            # All validations passed - mark as paid
            logger.info(
                f"✅ Valid payment detected for session {memo}. "
                f"Amount: {received_amount} {asset_type}, Tx: {tx_hash}"
            )
            
            session.status = PaymentStatus.PAID
            session.tx_hash = tx_hash
            session.paid_at = datetime.utcnow()
            
            db.commit()
            db.refresh(session)
            
            # Send webhook notification
            if session.merchant.webhook_url:
                await send_webhook(session, db)
            else:
                logger.warning(f"No webhook URL configured for merchant {session.merchant.id}")
            
        except Exception as e:
            logger.error(f"Error processing payment {tx_hash}: {e}")
            db.rollback()
        finally:
            db.close()
    
    async def process_payment_operation(self, operation, tx_hash: str, memo: Optional[str]):
        """Process a single payment operation. Supports both USDC and XLM."""
        try:
            # Check if it's a payment operation
            if operation["type"] not in ["payment", "path_payment_strict_receive", "path_payment_strict_send"]:
                return
            
            # Extract payment details
            destination = operation.get("to") or operation.get("destination")
            
            # Get asset information
            asset_type = operation.get("asset_type")
            
            logger.info(f"💰 Processing payment: tx={tx_hash[:8]}... dest={destination[:8] if destination else 'none'}... asset_type={asset_type} memo={memo}")
            
            # Handle native XLM payments
            if asset_type == "native":
                asset = Asset.native()  # XLM
                amount = operation.get("amount")
                
                logger.info(f"✨ XLM payment detected: amount={amount} XLM, memo={memo}")
                
                if amount and destination:
                    await self.validate_and_process_payment(
                        tx_hash=tx_hash,
                        destination=destination,
                        amount=amount,
                        memo=memo,
                        asset=asset
                    )
                return
            
            # Handle asset payments (USDC, etc.)
            asset_code = operation.get("asset_code")
            asset_issuer = operation.get("asset_issuer")
            
            if not asset_code or not asset_issuer:
                return
            
            asset = Asset(code=asset_code, issuer=asset_issuer)
            
            # Get amount
            amount = operation.get("amount")
            if not amount:
                return
            
            # Process the payment
            await self.validate_and_process_payment(
                tx_hash=tx_hash,
                destination=destination,
                amount=amount,
                memo=memo,
                asset=asset
            )
            
        except Exception as e:
            logger.error(f"Error processing operation: {e}")
    
    async def handle_transaction(self, transaction):
        """Handle a single transaction."""
        try:
            tx_hash = transaction.get("id")
            memo = transaction.get("memo")
            
            # Get all operations for this transaction
            operations_url = transaction.get("_links", {}).get("operations", {}).get("href")
            if not operations_url:
                return
            
            # Fetch operations
            operations_response = self.server.operations().for_transaction(tx_hash).call()
            operations = operations_response.get("_embedded", {}).get("records", [])
            
            # Process each operation
            for operation in operations:
                await self.process_payment_operation(operation, tx_hash, memo)
                
        except Exception as e:
            logger.error(f"Error handling transaction: {e}")
    
    async def listen_for_payments(self):
        """
        Main listening loop for Stellar payments.
        Only watches payments to active merchant addresses.
        """
        self.is_running = True
        logger.info("🚀 Stellar payment listener started")
        logger.info(f"Network: {settings.STELLAR_NETWORK}")
        logger.info(f"Horizon URL: {settings.STELLAR_HORIZON_URL}")
        logger.info(f"Watching for USDC and XLM payments")
        
        # Get all active merchant addresses
        db = self.get_db()
        try:
            from app.models import Merchant
            merchants = db.query(Merchant).filter(
                Merchant.stellar_address.isnot(None),
                Merchant.stellar_address != ""
            ).all()
            
            merchant_addresses = [m.stellar_address for m in merchants]
            logger.info(f"👥 Watching {len(merchant_addresses)} merchant address(es)")
            
            if not merchant_addresses:
                logger.warning("⚠️ No merchant addresses to watch! Please add Stellar addresses to merchant profiles.")
                return
                
        finally:
            db.close()
        
        # Watch payments for each merchant address
        while self.is_running:
            try:
                for merchant_address in merchant_addresses:
                    retry_count = 0
                    max_retries = 3
                    
                    while retry_count < max_retries and self.is_running:
                        try:
                            logger.info(f"📡 Streaming payments for {merchant_address[:8]}...")
                            
                            # Stream payments to this specific merchant address
                            payments_stream = self.server.payments().for_account(merchant_address).cursor(self.cursor).limit(10).stream()
                            
                            for payment in payments_stream:
                                if not self.is_running:
                                    break
                                
                                # Only process if it's a payment operation
                                if payment.get("type") not in ["payment", "path_payment_strict_receive", "path_payment_strict_send"]:
                                    continue
                                
                                # Update cursor
                                self.cursor = payment.get("paging_token")
                                
                                # Get transaction to extract memo
                                tx_hash = payment.get("transaction_hash")
                                tx = self.server.transactions().transaction(tx_hash).call()
                                memo = tx.get("memo")
                                
                                # Process the payment
                                await self.process_payment_operation(payment, tx_hash, memo)
                            
                            # If we get here without exception, break retry loop
                            break
                            
                        except (ConnectionError, Timeout, ReadTimeout) as e:
                            retry_count += 1
                            logger.warning(f"⚠️ Connection timeout for {merchant_address[:8]}... (attempt {retry_count}/{max_retries})")
                            if retry_count < max_retries:
                                await asyncio.sleep(5)  # Wait before retry
                            else:
                                logger.error(f"❌ Max retries reached for {merchant_address[:8]}..., moving to next address")
                        except BaseHorizonError as e:
                            logger.error(f"Horizon error for {merchant_address[:8]}...: {e}")
                            await asyncio.sleep(2)
                            break  # Move to next address
                        except Exception as e:
                            logger.error(f"Error processing payments for {merchant_address[:8]}...: {e}")
                            await asyncio.sleep(2)
                            break  # Move to next address
                    
                await asyncio.sleep(1)  # Brief pause between merchant address checks
                    
            except Exception as e:
                logger.error(f"Unexpected error in payment listener: {e}")
                await asyncio.sleep(5)  # Wait before retrying
    
    def stop(self):
        """Stop the listener."""
        logger.info("Stopping Stellar payment listener...")
        self.is_running = False


# Global listener instance
listener = StellarPaymentListener()


async def start_listener():
    """Start the Stellar payment listener."""
    await listener.listen_for_payments()


def stop_listener():
    """Stop the Stellar payment listener."""
    listener.stop()


# Run listener as standalone script
if __name__ == "__main__":
    try:
        asyncio.run(start_listener())
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down...")
        stop_listener()
