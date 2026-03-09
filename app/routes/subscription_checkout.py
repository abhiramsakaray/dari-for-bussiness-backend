"""
Subscription Checkout Routes

Public-facing routes for customers to subscribe to merchant plans.
Works like the payment link checkout flow:
  1. Customer visits /subscribe/{plan_id}  
  2. Enters email + selects payment method  
  3. Subscription is created → first payment session → redirect to /checkout/{session_id}  
  4. Payment confirmed → subscription activated via webhook  
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import and_
import secrets
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from app.core.database import get_db
from app.core.config import settings
from app.models.models import (
    Merchant, SubscriptionPlan, Subscription, SubscriptionPayment,
    PaymentSession, MerchantWallet,
    SubscriptionStatus, PaymentStatus,
)
from app.services.event_queue import EventService, EventTypes

router = APIRouter(tags=["Subscription Checkout"])


def _generate_ids():
    return f"sub_{secrets.token_urlsafe(12)}", f"pay_{secrets.token_urlsafe(12)}"


def get_subscribe_url(request: Request, plan_id: str) -> str:
    """Generate the public subscribe URL for a plan."""
    base_url = str(request.base_url).rstrip("/")
    return f"{base_url}/subscribe/{plan_id}"


# ─────────────────────────────────────────────
# Public subscribe page (no auth required)
# ─────────────────────────────────────────────

@router.get("/subscribe/{plan_id}", response_class=HTMLResponse)
async def subscribe_page(
    request: Request,
    plan_id: str,
    db: Session = Depends(get_db),
):
    """
    Public subscription landing page.

    Displays plan details (name, price, trial info, features) and a form
    for the customer to enter their email/name and subscribe.
    """
    plan = db.query(SubscriptionPlan).filter(
        and_(SubscriptionPlan.id == plan_id, SubscriptionPlan.is_active == True)
    ).first()
    if not plan:
        return HTMLResponse(
            content=_error_page("Plan Not Found", "This subscription plan does not exist or is no longer available."),
            status_code=404,
        )

    merchant = db.query(Merchant).filter(Merchant.id == plan.merchant_id).first()
    merchant_name = merchant.name if merchant else "Merchant"

    # Interval display
    interval_label = plan.interval.value if hasattr(plan.interval, "value") else plan.interval

    # Use plan's stored currency, falling back to merchant's base_currency
    fiat = (plan.fiat_currency or (merchant.base_currency if merchant else "USD")).upper()
    sym = (merchant.currency_symbol if merchant and merchant.base_currency == fiat else None)
    if not sym:
        currency_symbols = {"USD": "$", "INR": "₹", "EUR": "€", "GBP": "£", "JPY": "¥", "AUD": "A$", "CAD": "C$", "SGD": "S$", "AED": "د.إ"}
        sym = currency_symbols.get(fiat, fiat + " ")

    # Button text
    if plan.trial_days and plan.trial_days > 0 and (plan.trial_type or "free") == "free":
        btn_text = f"Start {plan.trial_days}-day free trial"
    else:
        btn_text = f"Subscribe &ndash; {sym}{plan.amount:.2f}/{interval_label}"

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Subscribe &ndash; {plan.name}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f0f2f5;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:16px}}

.modal{{display:flex;width:780px;max-width:100%;min-height:520px;border-radius:16px;overflow:hidden;box-shadow:0 20px 60px rgba(0,0,0,.15);border:1px solid #e0e3e8}}

/* ── LEFT ── */
.left{{width:300px;min-width:300px;background:linear-gradient(165deg,#2563eb 0%,#1d4ed8 40%,#1e3a8a 100%);color:#fff;display:flex;flex-direction:column;padding:30px 24px 22px;position:relative;overflow:hidden}}
.left::after{{content:'';position:absolute;bottom:-60px;left:-30px;width:220px;height:220px;background:rgba(255,255,255,.05);border-radius:50%;pointer-events:none}}
.left::before{{content:'';position:absolute;bottom:50px;right:-50px;width:160px;height:160px;background:rgba(255,255,255,.04);border-radius:50%;pointer-events:none}}

.m-header{{display:flex;align-items:center;gap:12px;margin-bottom:30px}}
.m-avatar{{width:44px;height:44px;border-radius:11px;background:rgba(255,255,255,.18);display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:700;backdrop-filter:blur(4px)}}
.m-name{{font-size:17px;font-weight:700}}

.price-box{{background:rgba(255,255,255,.11);backdrop-filter:blur(6px);border:1px solid rgba(255,255,255,.16);border-radius:14px;padding:20px 18px;margin-bottom:20px}}
.price-title{{font-size:11px;font-weight:700;opacity:.7;text-transform:uppercase;letter-spacing:1px;margin-bottom:10px}}
.price-fiat{{font-size:36px;font-weight:800;letter-spacing:-.5px;line-height:1.1}}
.price-interval{{margin-top:10px;font-size:13px;font-weight:500;opacity:.8;display:flex;align-items:center;gap:6px}}
.price-interval .tag{{background:rgba(255,255,255,.14);padding:2px 10px;border-radius:6px;font-size:12px;font-weight:600}}

.plan-name{{font-size:20px;font-weight:700;margin-bottom:6px;position:relative;z-index:1}}
.plan-desc{{font-size:13px;opacity:.75;line-height:1.5;margin-bottom:16px;position:relative;z-index:1}}

.trial-badge{{background:rgba(74,222,128,.15);color:#4ade80;padding:10px 14px;border-radius:11px;font-size:12px;font-weight:600;margin-bottom:16px;display:flex;align-items:center;gap:8px;border:1px solid rgba(74,222,128,.15);position:relative;z-index:1}}
.trial-badge.reduced{{background:rgba(251,191,36,.12);color:#fbbf24;border-color:rgba(251,191,36,.12)}}

.features-list{{list-style:none;padding:0;margin:0;font-size:13px;opacity:.85;position:relative;z-index:1}}
.features-list li{{padding:7px 0;border-bottom:1px solid rgba(255,255,255,.08);display:flex;align-items:center;gap:8px}}
.features-list li::before{{content:'✓';font-weight:700;color:#4ade80;font-size:14px}}

.secured{{text-align:center;margin-top:auto;padding-top:20px;font-size:12px;font-weight:600;opacity:.55;position:relative;z-index:1}}
.secured b{{opacity:1;font-weight:700;color:#93c5fd}}

/* ── RIGHT ── */
.right{{flex:1;background:#fff;display:flex;flex-direction:column}}
.r-header{{padding:16px 24px;border-bottom:1px solid #e5e7eb;display:flex;align-items:center}}
.r-header h2{{font-size:16px;font-weight:700;color:#111827}}

.r-body{{flex:1;padding:28px 28px;display:flex;flex-direction:column;justify-content:center}}

.pf-group{{margin-bottom:18px}}
.pf-label{{display:block;font-size:12px;font-weight:600;color:#374151;margin-bottom:5px;text-transform:uppercase;letter-spacing:.4px}}
.pf-input{{width:100%;padding:10px 14px;border:1.5px solid #d1d5db;border-radius:10px;font-size:14px;font-family:inherit;outline:none;transition:border .15s;box-sizing:border-box}}
.pf-input:focus{{border-color:#2563eb;box-shadow:0 0 0 3px rgba(37,99,235,.1)}}

.sub-btn{{width:100%;padding:13px;border:none;border-radius:12px;background:linear-gradient(135deg,#2563eb,#1d4ed8);color:#fff;font-size:15px;font-weight:700;cursor:pointer;transition:opacity .15s;font-family:inherit;margin-top:6px}}
.sub-btn:hover{{opacity:.9}}
.sub-btn:disabled{{opacity:.5;cursor:not-allowed}}

.note{{font-size:11px;color:#94a3b8;text-align:center;margin-top:14px;line-height:1.5}}
.error-msg{{font-size:13px;margin-bottom:14px;padding:10px 14px;border-radius:10px;display:none}}
.error-msg.err{{background:#fef2f2;color:#ef4444;border:1px solid #fecaca;display:block}}
.error-msg.ok{{background:#f0fdf4;color:#16a34a;border:1px solid #bbf7d0;display:block}}

.setup-note{{font-size:12px;opacity:.6;margin-top:8px}}

@media(max-width:780px){{
  .modal{{flex-direction:column;width:100%;max-width:520px;min-height:auto}}
  .left{{width:100%;min-width:auto;padding:22px 20px 16px}}
  .price-fiat{{font-size:28px}}
  .r-body{{padding:20px}}
}}
@media(max-width:480px){{
  body{{padding:0}}
  .modal{{border-radius:0;min-height:100vh}}
}}
</style>
</head>
<body>
<div class="modal">
  <!-- ═ LEFT ═ -->
  <div class="left">
    <div class="m-header">
      <div class="m-avatar">{merchant_name[0].upper() if merchant_name else 'M'}</div>
      <div class="m-name">{merchant_name}</div>
    </div>

    <div class="plan-name">{plan.name}</div>
    {'<div class="plan-desc">' + (plan.description or '') + '</div>' if plan.description else ''}

    <div class="price-box">
      <div class="price-title">Subscription</div>
      <div class="price-fiat">{sym}{plan.amount:.2f}</div>
      <div class="price-interval">per {interval_label} <span class="tag">{interval_label.upper()}</span></div>
      {f'<div class="setup-note">+ {sym}{plan.setup_fee:.2f} one-time setup fee</div>' if plan.setup_fee and plan.setup_fee > 0 else ''}
    </div>

    {f'<div class="trial-badge">&#127873; {plan.trial_days}-day free trial included</div>' if plan.trial_days and plan.trial_days > 0 and (plan.trial_type or "free") == "free" else ''}
    {f'<div class="trial-badge reduced">&#127873; {plan.trial_days}-day trial at {sym}{plan.trial_price}/{interval_label}</div>' if plan.trial_days and plan.trial_days > 0 and plan.trial_type == "reduced_price" else ''}

    {('<ul class="features-list">' + "".join(f"<li>{f}</li>" for f in plan.features) + '</ul>') if plan.features else ''}

    <div class="secured">Secured by <b>ChainPe</b></div>
  </div>

  <!-- ═ RIGHT ═ -->
  <div class="right">
    <div class="r-header">
      <h2>Subscribe</h2>
    </div>
    <div class="r-body">
      <div class="error-msg" id="err"></div>
      <form id="subForm" onsubmit="return handleSubscribe(event)">
        <div class="pf-group">
          <label class="pf-label">Email address</label>
          <input type="email" class="pf-input" id="email" required placeholder="you@example.com">
        </div>
        <div class="pf-group">
          <label class="pf-label">Full name (optional)</label>
          <input type="text" class="pf-input" id="name" placeholder="Jane Doe">
        </div>
        <button class="sub-btn" type="submit" id="submitBtn">
          {btn_text}
        </button>
        <p class="note">You'll be redirected to the secure payment page.
          {('No charge during the trial period.' if plan.trial_days and plan.trial_days > 0 and (plan.trial_type or 'free') == 'free' else '')}
        </p>
      </form>
    </div>
  </div>
</div>

<script>
async function handleSubscribe(e) {{
  e.preventDefault();
  const btn = document.getElementById('submitBtn');
  const err = document.getElementById('err');
  err.className = 'error-msg';
  btn.disabled = true;
  btn.textContent = 'Processing...';

  try {{
    const res = await fetch('/subscribe/{plan_id}', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{
        email: document.getElementById('email').value,
        name: document.getElementById('name').value || null
      }})
    }});
    const data = await res.json();
    if (!res.ok) {{
      throw new Error(data.detail || 'Subscription failed');
    }}
    if (data.checkout_url) {{
      window.location.href = data.checkout_url;
    }} else {{
      err.className = 'error-msg ok';
      err.textContent = 'Subscription created! Check your email for details.';
      btn.textContent = 'Subscribed ✓';
    }}
  }} catch (ex) {{
    err.className = 'error-msg err';
    err.textContent = ex.message;
    btn.disabled = false;
    btn.textContent = 'Try again';
  }}
}}
</script>
</body></html>"""

    return HTMLResponse(content=page)


@router.post("/subscribe/{plan_id}")
async def subscribe_to_plan(
    request: Request,
    plan_id: str,
    db: Session = Depends(get_db),
):
    """
    Public endpoint: create a subscription and return checkout URL.

    Request body (JSON):
        email: str (required)
        name: str | null

    Returns:
        subscription_id, checkout_url (if payment required), status
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    email = (body.get("email") or "").strip()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Valid email is required")
    name = body.get("name")

    plan = db.query(SubscriptionPlan).filter(
        and_(SubscriptionPlan.id == plan_id, SubscriptionPlan.is_active == True)
    ).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found or inactive")

    # Prevent duplicate active subscriptions
    existing = db.query(Subscription).filter(
        and_(
            Subscription.plan_id == plan.id,
            Subscription.customer_email == email,
            Subscription.status.in_([
                SubscriptionStatus.ACTIVE,
                SubscriptionStatus.PENDING_PAYMENT,
                SubscriptionStatus.TRIALING,
                SubscriptionStatus.PAST_DUE,
            ]),
        )
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="You already have an active subscription to this plan")

    sub_id, session_id = _generate_ids()
    now = datetime.utcnow()

    # Trial logic
    trial_start = trial_end = None
    initial_status = SubscriptionStatus.PENDING_PAYMENT
    if plan.trial_days and plan.trial_days > 0:
        trial_start = now
        trial_end = now + timedelta(days=plan.trial_days)
        initial_status = SubscriptionStatus.TRIALING

    interval_val = plan.interval.value if hasattr(plan.interval, "value") else plan.interval
    if initial_status == SubscriptionStatus.TRIALING:
        period_start, period_end = trial_start, trial_end
    else:
        period_start = now
        period_end = calculate_next_billing_date(now, interval_val, plan.interval_count)

    subscription = Subscription(
        id=sub_id,
        plan_id=plan.id,
        merchant_id=plan.merchant_id,
        customer_email=email,
        customer_name=name,
        status=initial_status,
        current_period_start=period_start,
        current_period_end=period_end,
        billing_anchor=now,
        trial_start=trial_start,
        trial_end=trial_end,
        next_payment_at=period_end if initial_status == SubscriptionStatus.TRIALING else now,
    )
    db.add(subscription)

    # Determine if we need an immediate payment
    needs_payment = False
    first_amount = Decimal("0")

    if initial_status == SubscriptionStatus.PENDING_PAYMENT:
        first_amount = plan.amount
        needs_payment = True
    elif plan.trial_type == "reduced_price" and plan.trial_price and plan.trial_price > 0:
        first_amount = plan.trial_price
        needs_payment = True

    if plan.setup_fee and plan.setup_fee > 0:
        first_amount = first_amount + plan.setup_fee
        needs_payment = True

    checkout_url = None

    if needs_payment:
        # Find merchant wallet
        merchant_wallet = None
        chain = (plan.accepted_chains or ["stellar"])[0]
        wallet_rec = db.query(MerchantWallet).filter(
            and_(
                MerchantWallet.merchant_id == plan.merchant_id,
                MerchantWallet.is_active == True,
            )
        ).all()
        for w in wallet_rec:
            cval = w.chain.value if hasattr(w.chain, "value") else str(w.chain)
            if cval == chain:
                merchant_wallet = w.wallet_address
                break
        if not merchant_wallet and wallet_rec:
            merchant_wallet = wallet_rec[0].wallet_address
            chain = wallet_rec[0].chain.value if hasattr(wallet_rec[0].chain, "value") else str(wallet_rec[0].chain)

        token = (plan.accepted_tokens or ["USDC"])[0]

        payment_session = PaymentSession(
            id=session_id,
            merchant_id=plan.merchant_id,
            amount_fiat=first_amount,
            fiat_currency=plan.fiat_currency,
            amount_token=str(first_amount),
            amount_usdc=str(first_amount),
            token=token,
            chain=chain,
            accepted_tokens=plan.accepted_tokens,
            accepted_chains=plan.accepted_chains,
            merchant_wallet=merchant_wallet,
            status=PaymentStatus.CREATED,
            success_url="",
            cancel_url="",
            order_id=f"sub_{sub_id}",
            session_metadata={
                "subscription_id": sub_id,
                "plan_id": plan.id,
                "type": "subscription_payment",
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
            },
            expires_at=now + timedelta(hours=48),
            collect_payer_data=False,
            payer_email=email,
            payer_name=name,
        )
        db.add(payment_session)

        sub_payment = SubscriptionPayment(
            subscription_id=sub_id,
            payment_session_id=session_id,
            period_start=period_start,
            period_end=period_end,
            amount=first_amount,
            fiat_currency=plan.fiat_currency,
            status=PaymentStatus.CREATED,
        )
        db.add(sub_payment)

        base_url = str(request.base_url).rstrip("/")
        checkout_url = f"{base_url}/checkout/{session_id}"

    # Emit event
    event_service = EventService(db)
    event_service.create_event(
        event_type=EventTypes.SUBSCRIPTION_CREATED,
        entity_type="subscription",
        entity_id=sub_id,
        payload={
            "subscription_id": sub_id,
            "plan_id": plan.id,
            "plan_name": plan.name,
            "customer_email": email,
            "status": initial_status.value,
            "trial_days": plan.trial_days,
            "amount": float(first_amount) if needs_payment else 0,
            "event": "subscription.created",
        },
        merchant_id=str(plan.merchant_id),
    )

    db.commit()

    return {
        "subscription_id": sub_id,
        "status": initial_status.value,
        "checkout_url": checkout_url,
        "message": (
            f"Free trial started for {plan.trial_days} days. No payment required yet."
            if initial_status == SubscriptionStatus.TRIALING and not needs_payment
            else "Redirecting to payment..."
        ),
    }


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def calculate_next_billing_date(current_date: datetime, interval: str, interval_count: int = 1) -> datetime:
    if interval == "daily":
        return current_date + timedelta(days=interval_count)
    elif interval == "weekly":
        return current_date + timedelta(weeks=interval_count)
    elif interval == "monthly":
        return current_date + timedelta(days=30 * interval_count)
    elif interval == "quarterly":
        return current_date + timedelta(days=90 * interval_count)
    elif interval == "yearly":
        return current_date + timedelta(days=365 * interval_count)
    return current_date + timedelta(days=30)


def _error_page(title: str, message: str) -> str:
    return f"""<!DOCTYPE html>
<html><head><title>{title}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
</head>
<body style="font-family:'Inter',sans-serif;background:#f0f2f5;display:flex;align-items:center;justify-content:center;min-height:100vh">
<div style="text-align:center;background:#fff;padding:48px 40px;border-radius:16px;box-shadow:0 10px 40px rgba(0,0,0,.08);max-width:440px">
<h1 style="font-size:24px;color:#1e293b;margin-bottom:12px">{title}</h1>
<p style="color:#64748b;font-size:14px;line-height:1.6">{message}</p>
</div></body></html>"""
