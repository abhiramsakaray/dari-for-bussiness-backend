"""
Shopify Order Creation Service
Handles creating draft orders and completing them after payment
"""
import requests
import logging
from typing import Dict, Any
from app.models import PaymentSession

logger = logging.getLogger(__name__)


async def create_shopify_order(session: PaymentSession, shopify_store: str, access_token: str) -> Dict[str, Any]:
    """
    Create a Shopify order after successful payment
    
    Args:
        session: PaymentSession with payment details
        shopify_store: Shopify store URL (e.g., "stellerfi.myshopify.com")
        access_token: Shopify Admin API access token
    """
    try:
        # Extract order details from session metadata
        metadata = session.metadata or {}
        order_id = metadata.get("order_id")
        customer_email = metadata.get("customer_email", "customer@example.com")
        
        # Create order via Shopify Admin API
        url = f"https://{shopify_store}/admin/api/2024-01/orders.json"
        headers = {
            "X-Shopify-Access-Token": access_token,
            "Content-Type": "application/json"
        }
        
        order_data = {
            "order": {
                "email": customer_email,
                "financial_status": "paid",
                "fulfillment_status": None,
                "send_receipt": True,
                "send_fulfillment_receipt": False,
                "note": f"Paid with ChainPe - Tx: {session.tx_hash}",
                "tags": "chainpe, crypto-payment",
                "transactions": [
                    {
                        "kind": "sale",
                        "status": "success",
                        "amount": str(session.amount_fiat),
                        "currency": session.fiat_currency,
                        "gateway": "ChainPe"
                    }
                ],
                "line_items": metadata.get("line_items", []),
                "customer": {
                    "email": customer_email
                }
            }
        }
        
        response = requests.post(url, json=order_data, headers=headers)
        response.raise_for_status()
        
        result = response.json()
        logger.info(f"✅ Shopify order created: {result['order']['id']}")
        return result
        
    except Exception as e:
        logger.error(f"❌ Failed to create Shopify order: {e}")
        raise
