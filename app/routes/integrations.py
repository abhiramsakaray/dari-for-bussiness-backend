"""
E-commerce Platform Integration Endpoints
Easy integration for Shopify, WooCommerce, and other platforms
"""
from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import RedirectResponse, HTMLResponse
from pydantic import BaseModel
from typing import Optional
from app.core.database import get_db
from app.models import Merchant, PaymentSession
from sqlalchemy.orm import Session
import secrets

router = APIRouter(prefix="/integrations", tags=["E-commerce Integrations"])


class SimplePaymentRequest(BaseModel):
    """Simple payment request for e-commerce platforms"""
    api_key: str
    amount: str
    currency: str = "USD"
    order_id: str
    customer_email: Optional[str] = None
    success_url: str
    cancel_url: str
    webhook_url: Optional[str] = None


@router.post("/create-checkout")
async def create_simple_checkout(
    request: SimplePaymentRequest,
    db: Session = Depends(get_db)
):
    """
    Simple checkout creation for e-commerce platforms
    
    Usage:
    POST /integrations/create-checkout
    {
        "api_key": "YOUR_API_KEY",
        "amount": "50.00",
        "currency": "USD",
        "order_id": "ORDER-123",
        "customer_email": "customer@example.com",
        "success_url": "https://yourstore.com/success",
        "cancel_url": "https://yourstore.com/cancel",
        "webhook_url": "https://yourstore.com/webhook"
    }
    
    Returns:
    {
        "checkout_url": "https://chainpe.onrender.com/checkout/pay_xxx",
        "session_id": "pay_xxx"
    }
    """
    # Verify API key
    merchant = db.query(Merchant).filter(Merchant.api_key == request.api_key).first()
    if not merchant:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    # Create payment session directly
    from stellar_sdk import Keypair
    from app.core.config import settings
    from app.models import PaymentStatus
    from datetime import datetime, timedelta
    from app.services.payment_utils import generate_session_id
    import logging
    
    logger = logging.getLogger(__name__)
    
    session_id = generate_session_id()
    
    # Calculate USDC amount (assuming 1:1 for USD)
    amount_usdc = str(float(request.amount))
    
    # Generate payment memo
    memo = session_id
    
    new_session = PaymentSession(
        id=session_id,
        merchant_id=merchant.id,
        amount_fiat=float(request.amount),
        fiat_currency=request.currency,
        amount_usdc=amount_usdc,
        status=PaymentStatus.CREATED,
        success_url=request.success_url,
        cancel_url=request.cancel_url
    )
    
    db.add(new_session)
    db.commit()
    db.refresh(new_session)
    
    checkout_url = f"{settings.APP_BASE_URL}/checkout/{session_id}"
    
    return {
        "checkout_url": checkout_url,
        "session_id": session_id,
        "status": "pending"
    }


@router.get("/payment-button")
async def get_payment_button(api_key: str):
    """
    Get embeddable payment button HTML
    
    Usage:
    GET /integrations/payment-button?api_key=YOUR_API_KEY
    
    Returns HTML snippet that can be embedded in any website
    """
    
    button_html = f"""
    <script>
    function openChainPeCheckout(amount, orderId, successUrl, cancelUrl) {{
        const checkoutData = {{
            api_key: '{api_key}',
            amount: amount,
            currency: 'USD',
            order_id: orderId,
            success_url: successUrl,
            cancel_url: cancelUrl
        }};
        
        fetch('https://chainpe.onrender.com/integrations/create-checkout', {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify(checkoutData)
        }})
        .then(res => res.json())
        .then(data => {{
            window.location.href = data.checkout_url;
        }});
    }}
    </script>
    
    <button 
        onclick="openChainPeCheckout('50.00', 'ORDER-123', window.location.href + '?payment=success', window.location.href + '?payment=cancel')"
        style="background: #000; color: #fff; padding: 12px 24px; border: none; cursor: pointer; font-weight: 600;">
        Pay with ChainPe
    </button>
    """
    
    return HTMLResponse(content=button_html)


@router.get("/verify/{session_id}")
async def verify_payment_status(
    session_id: str,
    api_key: str,
    db: Session = Depends(get_db)
):
    """
    Verify payment status for e-commerce platforms
    
    Usage:
    GET /integrations/verify/pay_xxx?api_key=YOUR_API_KEY
    
    Returns payment status and details
    """
    # Verify API key
    merchant = db.query(Merchant).filter(Merchant.api_key == api_key).first()
    if not merchant:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    # Get session
    session = db.query(PaymentSession).filter(
        PaymentSession.session_id == session_id,
        PaymentSession.merchant_id == merchant.id
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Payment session not found")
    
    return {
        "session_id": session.session_id,
        "status": session.status.value,
        "amount": str(session.amount_fiat),
        "currency": session.fiat_currency,
        "paid_amount": str(session.paid_amount) if session.paid_amount else None,
        "paid_asset": session.paid_asset,
        "transaction_hash": session.transaction_hash,
        "metadata": session.metadata,
        "created_at": session.created_at.isoformat(),
        "paid_at": session.paid_at.isoformat() if session.paid_at else None
    }


@router.get("/shopify-install")
async def shopify_install_page():
    """Landing page for Shopify app installation"""
    
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>ChainPe for Shopify</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }
            h1 { color: #000; }
            .step { background: #f5f5f5; padding: 20px; margin: 20px 0; border: 2px solid #000; }
            code { background: #000; color: #fff; padding: 2px 6px; }
        </style>
    </head>
    <body>
        <h1>ChainPe Payment Gateway for Shopify</h1>
        
        <div class="step">
            <h3>Step 1: Get Your API Key</h3>
            <p>Sign up at <code>https://chainpe.onrender.com/docs</code> and create a merchant account to get your API key.</p>
        </div>
        
        <div class="step">
            <h3>Step 2: Configure Webhook</h3>
            <p>Set your Shopify webhook URL when creating checkout sessions.</p>
        </div>
        
        <div class="step">
            <h3>Step 3: Add Payment Button</h3>
            <p>Add this code to your Shopify theme:</p>
            <pre><code>
&lt;button onclick="payWithChainPe()"&gt;Pay with Crypto&lt;/button&gt;
&lt;script&gt;
function payWithChainPe() {
    fetch('https://chainpe.onrender.com/integrations/create-checkout', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            api_key: 'YOUR_API_KEY',
            amount: '{{ checkout.total_price }}',
            currency: '{{ checkout.currency }}',
            order_id: '{{ order.name }}',
            success_url: '{{ shop.url }}/orders/{{ order.name }}',
            cancel_url: '{{ shop.url }}/cart'
        })
    })
    .then(res => res.json())
    .then(data => window.location.href = data.checkout_url);
}
&lt;/script&gt;
            </code></pre>
        </div>
        
        <p><strong>Documentation:</strong> <a href="http://localhost:8000/docs">API Docs</a></p>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html)


@router.get("/woocommerce-plugin")
async def woocommerce_plugin_info():
    """Information page for WooCommerce plugin"""
    
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>ChainPe for WooCommerce</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }
            h1 { color: #000; }
            .step { background: #f5f5f5; padding: 20px; margin: 20px 0; border: 2px solid #000; }
            code { background: #000; color: #fff; padding: 2px 6px; }
        </style>
    </head>
    <body>
        <h1>ChainPe Payment Gateway for WooCommerce</h1>
        
        <div class="step">
            <h3>Integration Steps</h3>
            <ol>
                <li>Get your ChainPe API key from the dashboard</li>
                <li>Add custom payment gateway in WooCommerce settings</li>
                <li>Use our REST API endpoint for checkout creation</li>
            </ol>
        </div>
        
        <div class="step">
            <h3>PHP Integration Example</h3>
            <pre><code>
// Create ChainPe checkout
$response = wp_remote_post('https://chainpe.onrender.com/integrations/create-checkout', array(
    'body' => json_encode(array(
        'api_key' => 'YOUR_API_KEY',
        'amount' => $order->get_total(),
        'currency' => get_woocommerce_currency(),
        'order_id' => $order->get_id(),
        'success_url' => $this->get_return_url($order),
        'cancel_url' => wc_get_checkout_url(),
        'webhook_url' => get_site_url() . '/wc-api/chainpe_webhook'
    )),
    'headers' => array('Content-Type' => 'application/json')
));

$data = json_decode(wp_remote_retrieve_body($response));
wp_redirect($data->checkout_url);
            </code></pre>
        </div>
        
        <p><strong>Documentation:</strong> <a href="http://localhost:8000/docs">API Docs</a></p>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html)
