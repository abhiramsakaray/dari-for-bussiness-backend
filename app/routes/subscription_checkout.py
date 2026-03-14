"""
Subscription Checkout Routes

Public-facing routes for customers to subscribe to merchant plans.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import and_, cast, String
import secrets
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from app.core.database import get_db
from app.core.config import settings
from app.models.models import (
    Merchant, SubscriptionPlan, Subscription, SubscriptionPayment,
    PaymentSession, MerchantWallet,
    SubscriptionStatus, PaymentStatus,
)
from app.services.event_queue import EventService, EventTypes
from app.services.currency_service import convert_local_to_usdc

router = APIRouter(tags=["Subscription Checkout"])

EVM_SIGNATURE_CHAINS = {"ethereum", "polygon", "base"}

INTERVAL_SECONDS = {
    "daily": 86400,
    "weekly": 604800,
    "monthly": 2592000,
    "quarterly": 7776000,
    "yearly": 31536000,
}

TOKEN_ADDRESS_SETTINGS = {
    "ethereum": {
        "USDC": "ETHEREUM_USDC_ADDRESS",
        "USDT": "ETHEREUM_USDT_ADDRESS",
    },
    "polygon": {
        "USDC": "POLYGON_USDC_ADDRESS",
        "USDT": "POLYGON_USDT_ADDRESS",
    },
    "base": {
        "USDC": "BASE_USDC_ADDRESS",
    },
}


def _chain_id_for(chain: str) -> int:
    if chain == "ethereum":
        return int(settings.ETHEREUM_CHAIN_ID)
    if chain == "polygon":
        return int(settings.POLYGON_CHAIN_ID)
    if chain == "base":
        return int(settings.BASE_CHAIN_ID)
    return 0


def _resolve_token_address(chain: str, token_symbol: str) -> str:
    setting_name = TOKEN_ADDRESS_SETTINGS.get(chain, {}).get(token_symbol.upper())
    if not setting_name:
        raise HTTPException(status_code=400, detail=f"Unsupported token {token_symbol} on {chain}")
    address = getattr(settings, setting_name, "")
    if not address:
        raise HTTPException(status_code=400, detail=f"Token address missing in env: {setting_name}")
    return address


def _has_subscription_contract(chain: str) -> bool:
    setting_name = f"SUBSCRIPTION_CONTRACT_{chain.upper()}"
    return bool(getattr(settings, setting_name, ""))


def _generate_ids():
    return f"sub_{secrets.token_urlsafe(12)}", f"pay_{secrets.token_urlsafe(12)}"


def get_subscribe_url(request: Request, plan_id: str) -> str:
    """Generate the public subscribe URL for a plan."""
    base_url = str(request.base_url).rstrip("/")
    return f"{base_url}/subscribe/{plan_id}"


def _status_value(status_obj) -> str:
    return status_obj.value if hasattr(status_obj, "value") else str(status_obj)


def _build_manage_url(base_url: str, subscription_id: str, email: str) -> str:
    return f"{base_url}/subscribe/manage/{subscription_id}?email={email}"


# ─────────────────────────────────────────────
# Public subscribe page (no auth required)
# ─────────────────────────────────────────────

@router.get("/subscribe/{plan_id}", response_class=HTMLResponse)
async def subscribe_page(
    request: Request,
    plan_id: str,
    source: Optional[str] = Query(default=None, description="Originating website or app"),
    customer_id: Optional[str] = Query(default=None, description="Merchant customer identifier"),
    return_url: Optional[str] = Query(default=None, description="Where to send user after non-payment flows"),
    success_url: Optional[str] = Query(default=None, description="Where checkout should redirect on success"),
    cancel_url: Optional[str] = Query(default=None, description="Where checkout should redirect on cancel"),
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

    # Emit "plan viewed" webhook event for funnel tracking
    try:
        event_service = EventService(db)
        event_service.create_event(
            event_type=EventTypes.SUBSCRIPTION_PLAN_VIEWED,
            entity_type="subscription_plan",
            entity_id=plan.id,
            merchant_id=str(plan.merchant_id),
            payload={
                "event": "subscription.plan_viewed",
                "plan_id": plan.id,
                "plan_name": plan.name,
                "source": source,
                "customer_id": customer_id,
                "return_url": return_url,
                "success_url": success_url,
                "cancel_url": cancel_url,
                "ip": request.client.host if request.client else None,
                "user_agent": request.headers.get("user-agent"),
            },
        )
    except Exception:
        # Non-blocking analytics webhook event
        pass

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
                <input type="hidden" id="source" value="{source or ''}">
                <input type="hidden" id="customer_id" value="{customer_id or ''}">
                <input type="hidden" id="return_url" value="{return_url or ''}">
                <input type="hidden" id="success_url" value="{success_url or ''}">
                <input type="hidden" id="cancel_url" value="{cancel_url or ''}">
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
                name: document.getElementById('name').value || null,
                source: document.getElementById('source').value || null,
                customer_id: document.getElementById('customer_id').value || null,
                return_url: document.getElementById('return_url').value || null,
                success_url: document.getElementById('success_url').value || null,
                cancel_url: document.getElementById('cancel_url').value || null
      }})
    }});
    const data = await res.json();
    if (!res.ok) {{
      throw new Error(data.detail || 'Subscription failed');
    }}
                if (data.authorize_url) {{
            window.location.href = data.authorize_url;
                }} else if (data.checkout_url) {{
      window.location.href = data.checkout_url;
        }} else if (data.redirect_url) {{
            window.location.href = data.redirect_url;
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
    source = body.get("source")
    customer_id = body.get("customer_id")
    return_url = body.get("return_url")
    success_url = body.get("success_url")
    cancel_url = body.get("cancel_url")

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
            cast(Subscription.status, String).in_([
                SubscriptionStatus.ACTIVE.value,
                SubscriptionStatus.PENDING_PAYMENT.value,
                SubscriptionStatus.TRIALING.value,
                SubscriptionStatus.PAST_DUE.value,
            ]),
        )
    ).first()
    if existing:
        existing_status = _status_value(existing.status)
        base_url = str(request.base_url).rstrip("/")
        manage_url = _build_manage_url(base_url, existing.id, email)
        existing_plan = existing.plan
        existing_chain = ""
        if existing_plan and existing_plan.accepted_chains:
            existing_chain = str(existing_plan.accepted_chains[0]).lower()
        meta = existing.subscription_metadata or {}
        if isinstance(meta, dict) and meta.get("chain"):
            existing_chain = str(meta.get("chain")).lower()

        if existing_chain in EVM_SIGNATURE_CHAINS and _has_subscription_contract(existing_chain):
            return {
                "subscription_id": existing.id,
                "status": existing_status,
                "existing_subscription": True,
                "authorize_url": f"{base_url}/subscribe/authorize/{existing.id}?email={email}",
                "manage_url": manage_url,
                "message": "Authorization required. Sign in wallet to continue this subscription.",
            }

        pending_payment = (
            db.query(SubscriptionPayment)
            .filter(
                SubscriptionPayment.subscription_id == existing.id,
                SubscriptionPayment.status.in_([PaymentStatus.CREATED, PaymentStatus.PENDING]),
                SubscriptionPayment.payment_session_id.isnot(None),
            )
            .order_by(SubscriptionPayment.created_at.desc())
            .first()
        )

        if pending_payment and pending_payment.payment_session_id:
            return {
                "subscription_id": existing.id,
                "status": existing_status,
                "existing_subscription": True,
                "checkout_url": f"{base_url}/checkout/{pending_payment.payment_session_id}",
                "manage_url": manage_url,
                "message": "You already started this subscription. Continue payment or manage your subscription.",
            }

        return {
            "subscription_id": existing.id,
            "status": existing_status,
            "existing_subscription": True,
            "manage_url": manage_url,
            "message": "You already have a subscription for this plan. Manage it from your subscription page.",
        }

    # Emit "plan selected" event before creating subscription
    try:
        event_service = EventService(db)
        event_service.create_event(
            event_type=EventTypes.SUBSCRIPTION_PLAN_SELECTED,
            entity_type="subscription_plan",
            entity_id=plan.id,
            payload={
                "event": "subscription.plan_selected",
                "plan_id": plan.id,
                "plan_name": plan.name,
                "customer_email": email,
                "customer_name": name,
                "customer_id": customer_id,
                "source": source,
            },
            merchant_id=str(plan.merchant_id),
        )
    except Exception:
        pass

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
        status=initial_status.value,
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

    base_url = str(request.base_url).rstrip("/")
    checkout_url = None
    manage_url = _build_manage_url(base_url, sub_id, email)
    authorize_url = None

    if needs_payment:
        # Find merchant wallet
        merchant_wallet = None
        chain = str((plan.accepted_chains or ["stellar"])[0]).lower()
        wallet_rec = db.query(MerchantWallet).filter(
            and_(
                MerchantWallet.merchant_id == plan.merchant_id,
                MerchantWallet.is_active == True,
            )
        ).all()
        for w in wallet_rec:
            cval = (w.chain.value if hasattr(w.chain, "value") else str(w.chain)).lower()
            if cval == chain:
                merchant_wallet = w.wallet_address
                break
        if not merchant_wallet and wallet_rec:
            merchant_wallet = wallet_rec[0].wallet_address
            chain = (wallet_rec[0].chain.value if hasattr(wallet_rec[0].chain, "value") else str(wallet_rec[0].chain)).lower()

        token = str((plan.accepted_tokens or ["USDC"])[0]).upper()

        fiat_currency = (plan.fiat_currency or "USD").upper()
        amount_usdc = Decimal(str(first_amount))
        if fiat_currency != "USD":
            converted_usdc, _rate = await convert_local_to_usdc(
                float(first_amount),
                fiat_currency,
            )
            amount_usdc = Decimal(str(converted_usdc))

        # EVM subscriptions should use EIP-712 signature authorization, not direct transfer QR flow.
        if chain in EVM_SIGNATURE_CHAINS and _has_subscription_contract(chain):
            if not merchant_wallet:
                raise HTTPException(status_code=400, detail=f"Merchant wallet required for {chain} subscriptions")

            subscription.subscription_metadata = {
                "authorization_required": True,
                "authorization_method": "eip712_mandate",
                "amount_usdc": str(amount_usdc),
                "token": token,
                "chain": chain,
                "source": source,
                "customer_id": customer_id,
                "return_url": return_url,
            }
            authorize_url = f"{base_url}/subscribe/authorize/{sub_id}?email={email}"
        else:
            payment_session = PaymentSession(
                id=session_id,
                merchant_id=plan.merchant_id,
                amount_fiat=first_amount,
                fiat_currency=fiat_currency,
                amount_token=str(amount_usdc),
                amount_usdc=str(amount_usdc),
                token=token,
                chain=chain,
                accepted_tokens=plan.accepted_tokens,
                accepted_chains=plan.accepted_chains,
                merchant_wallet=merchant_wallet,
                status=PaymentStatus.CREATED,
                success_url=success_url or return_url or "",
                cancel_url=cancel_url or return_url or "",
                order_id=f"sub_{sub_id}",
                session_metadata={
                    "subscription_id": sub_id,
                    "plan_id": plan.id,
                    "type": "subscription_payment",
                    "source": source,
                    "customer_id": customer_id,
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

    # Emit approval event (customer completed hosted step and subscription record exists)
    try:
        event_service = EventService(db)
        event_service.create_event(
            event_type=EventTypes.SUBSCRIPTION_APPROVED,
            entity_type="subscription",
            entity_id=sub_id,
            payload={
                "event": "subscription.approved",
                "subscription_id": sub_id,
                "plan_id": plan.id,
                "customer_email": email,
                "status": initial_status.value,
                "checkout_required": needs_payment,
                "checkout_url": checkout_url,
                "authorize_url": authorize_url,
                "source": source,
                "customer_id": customer_id,
            },
            merchant_id=str(plan.merchant_id),
        )
    except Exception:
        pass

    return {
        "subscription_id": sub_id,
        "status": initial_status.value,
        "checkout_url": checkout_url,
                "authorize_url": authorize_url,
        "manage_url": manage_url,
        "redirect_url": (return_url if (initial_status == SubscriptionStatus.TRIALING and not needs_payment) else None),
        "message": (
            f"Free trial started for {plan.trial_days} days. No payment required yet."
            if initial_status == SubscriptionStatus.TRIALING and not needs_payment
                        else ("Authorization required. Please sign in wallet to activate subscription." if authorize_url else "Redirecting to payment...")
        ),
    }


@router.get("/subscribe/authorize/{subscription_id}", response_class=HTMLResponse)
async def subscription_authorize_page(
    request: Request,
    subscription_id: str,
    email: str = Query(..., description="Subscriber email for authorization"),
    db: Session = Depends(get_db),
):
    sub = db.query(Subscription).filter(Subscription.id == subscription_id).first()
    if not sub or sub.customer_email.lower() != email.lower():
        raise HTTPException(status_code=404, detail="Subscription not found")

    plan = sub.plan
    merchant = db.query(Merchant).filter(Merchant.id == sub.merchant_id).first()
    merchant_name = merchant.name if merchant else "Merchant"

    sym = "$"
    fiat_currency = "USD"
    amount_fiat = "--"
    if plan:
        fiat_currency = (plan.fiat_currency or "USD").upper()
        symbols = {
            "USD": "$", "INR": "₹", "EUR": "€", "GBP": "£", "JPY": "¥", "AUD": "A$", "CAD": "C$", "SGD": "S$", "AED": "د.إ"
        }
        sym = symbols.get(fiat_currency, f"{fiat_currency} ")
        amount_fiat = f"{sym}{Decimal(str(plan.amount)):.2f}"

    auth_url = f"{str(request.base_url).rstrip('/')}/subscribe/authorize/{subscription_id}?email={email}"

    page = f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1.0\">
  <title>Authorize Subscription</title>
  <script src=\"https://cdn.jsdelivr.net/npm/ethers@6.13.2/dist/ethers.umd.min.js\"></script>
  <style>
    *{{margin:0;padding:0;box-sizing:border-box}}
    body{{font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f0f2f5;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:16px}}
    .modal{{display:flex;width:980px;max-width:100%;min-height:560px;border-radius:16px;overflow:hidden;box-shadow:0 20px 60px rgba(0,0,0,.15);border:1px solid #e0e3e8}}
    .left{{width:320px;min-width:320px;background:linear-gradient(165deg,#2563eb 0%,#1d4ed8 40%,#1e3a8a 100%);color:#fff;display:flex;flex-direction:column;padding:30px 24px 22px;position:relative;overflow:hidden}}
    .left::after{{content:'';position:absolute;bottom:-60px;left:-30px;width:220px;height:220px;background:rgba(255,255,255,.05);border-radius:50%;pointer-events:none}}
    .left::before{{content:'';position:absolute;bottom:50px;right:-50px;width:160px;height:160px;background:rgba(255,255,255,.04);border-radius:50%;pointer-events:none}}
    .m-header{{display:flex;align-items:center;gap:12px;margin-bottom:30px;z-index:1}}
    .m-avatar{{width:44px;height:44px;border-radius:11px;background:rgba(255,255,255,.18);display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:700;backdrop-filter:blur(4px)}}
    .m-name{{font-size:17px;font-weight:700}}
    .price-box{{background:rgba(255,255,255,.11);backdrop-filter:blur(6px);border:1px solid rgba(255,255,255,.16);border-radius:14px;padding:20px 18px;margin-bottom:16px;z-index:1}}
    .price-title{{font-size:11px;font-weight:700;opacity:.7;text-transform:uppercase;letter-spacing:1px;margin-bottom:10px}}
    .price-fiat{{font-size:34px;font-weight:800;line-height:1.1}}
    .price-crypto{{margin-top:10px;font-size:13px;opacity:.9}}
    .status-pill{{display:flex;align-items:center;gap:8px;background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.2);padding:10px 12px;border-radius:10px;font-size:13px;font-weight:600;z-index:1}}
    .dot{{width:8px;height:8px;border-radius:50%;background:#fbbf24}}
    .secured{{text-align:center;margin-top:auto;padding-top:20px;font-size:12px;font-weight:600;opacity:.55;z-index:1}}
    .secured b{{opacity:1;font-weight:700;color:#93c5fd}}
    .right{{flex:1;background:#fff;display:grid;grid-template-columns:1fr 1fr;gap:14px;padding:16px}}
    .panel{{border:1px solid #e5e7eb;border-radius:14px;padding:16px;background:#fff}}
    .panel h2{{font-size:18px;color:#111827;margin-bottom:8px}}
    .sub{{font-size:13px;color:#64748b;line-height:1.4;margin-bottom:12px}}
    .meta{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}
    .box{{background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:10px}}
    .lbl{{font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:.4px}}
    .val{{font-weight:700;color:#0f172a;margin-top:4px;font-size:13px;word-break:break-word}}
    .btn{{width:100%;padding:13px;border:none;border-radius:12px;background:linear-gradient(135deg,#2563eb,#1d4ed8);color:#fff;font-size:15px;font-weight:700;cursor:pointer;font-family:inherit;margin-top:12px}}
    .btn:hover{{opacity:.92}}
    .btn:disabled{{opacity:.6;cursor:not-allowed}}
    .msg{{margin-top:10px;font-size:14px;color:#334155;white-space:pre-wrap;min-height:20px}}
    .qr-box{{background:#f9fafb;border:1px solid #e5e7eb;border-radius:12px;padding:14px;text-align:center}}
    .qr-img{{background:#fff;border:2px solid #e5e7eb;border-radius:12px;padding:10px;display:inline-flex}}
    .qr-img img{{width:170px;height:170px}}
    .qr-note{{font-size:12px;color:#6b7280;margin-top:10px;line-height:1.45}}
    .option{{font-size:13px;color:#334155;margin-top:10px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:8px 10px}}
    @media(max-width:900px){{
      .modal{{flex-direction:column;max-width:620px;min-height:auto}}
      .left{{width:100%;min-width:auto;padding:22px 20px 16px}}
      .right{{grid-template-columns:1fr}}
    }}
  </style>
</head>
<body>
<div class=\"modal\">
  <div class=\"left\">
    <div class=\"m-header\">
      <div class=\"m-avatar\">{merchant_name[0].upper() if merchant_name else 'M'}</div>
      <div class=\"m-name\">{merchant_name}</div>
    </div>
    <div class=\"price-box\">
      <div class=\"price-title\">Price Summary</div>
      <div class=\"price-fiat\" id=\"fiatValue\">{amount_fiat}</div>
      <div class=\"price-crypto\">≈ <span id=\"cryptoValue\">-- USDC</span> on <span id=\"chainValue\">Polygon</span></div>
    </div>
    <div class=\"status-pill\"><span class=\"dot\"></span><span id=\"statusText\">Waiting for wallet signature...</span></div>
    <div class=\"secured\">Secured by <b>ChainPe</b></div>
  </div>

  <div class=\"right\">
    <div class=\"panel\">
      <h2>Authorize Subscription</h2>
      <div class=\"sub\">This uses the same hosted checkout style, but the method is wallet signature (EIP-712 mandate), not token transfer QR.</div>
      <div class=\"meta\" id=\"meta\"></div>
      <button id=\"signBtn\" class=\"btn\" onclick=\"startAuthorization()\">Connect Wallet & Sign</button>
      <div id=\"msg\" class=\"msg\"></div>
    </div>

    <div class=\"panel\">
      <h2>Scan To Sign On Mobile</h2>
      <div class=\"sub\">Scan this QR with your mobile wallet browser to open this same authorization page and sign from phone.</div>
            <div class=\"qr-box\">
                <div class=\"qr-img\"><img id=\"qrImg\" src=\"\" alt=\"Authorization QR\"></div>
                <div class=\"qr-note\" id=\"qrNote\">Method: EIP-712 signature authorization<br>Action: Sign mandate, then subscription is created</div>
            </div>
            <div style=\"display:flex;gap:8px;flex-wrap:wrap;margin-top:10px\">
                <button type=\"button\" class=\"btn\" style=\"width:auto;padding:8px 12px;font-size:13px\" onclick=\"setQrMode('metamask')\">MetaMask QR</button>
                <button type=\"button\" class=\"btn\" style=\"width:auto;padding:8px 12px;font-size:13px\" onclick=\"setQrMode('trust')\">Trust Wallet QR</button>
                <button type=\"button\" class=\"btn\" style=\"width:auto;padding:8px 12px;font-size:13px\" onclick=\"setQrMode('browser')\">Browser QR</button>
            </div>
      <div class=\"option\">No direct transfer is requested in this flow.</div>
      <div class=\"option\">If you are already on mobile wallet browser, tap “Connect Wallet & Sign”.</div>
    </div>
  </div>
</div>

<script>
  const SUB_ID = {subscription_id!r};
  const EMAIL = {email!r};
  const AUTH_URL = {auth_url!r};
    const AUTH_URL_ENC = encodeURIComponent(AUTH_URL);
    const MM_DEEPLINK = `https://metamask.app.link/dapp/${{encodeURIComponent(new URL(AUTH_URL).host + new URL(AUTH_URL).pathname + new URL(AUTH_URL).search)}}`;
  let cfg = null;
    let qrMode = 'metamask';
    let provider = null;

  function setMsg(v) {{ document.getElementById('msg').textContent = v; }}

  function setStatus(v) {{ document.getElementById('statusText').textContent = v; }}

    function pickSignerAddress(accounts) {{
        const list = Array.isArray(accounts) ? accounts : [];
        const selected = (provider && provider.selectedAddress) || (window.ethereum && window.ethereum.selectedAddress) || null;
        // Some wallets can sign with selectedAddress even when eth_accounts is stale.
        // Prefer selectedAddress first to keep the signed payload aligned with actual signer.
        if (selected) return String(selected);
        return list.length > 0 ? String(list[0]) : null;
    }}

    function formatErr(err) {{
        if (!err) return 'Authorization failed';
        if (err && Number(err.code) === 4001) return 'Signature request was rejected in wallet. Please approve to continue.';
        if (err && Number(err.code) === 4100) return 'Wallet has not authorized this account/method for the site. Open wallet, connect this site, and retry.';
        if (typeof err === 'string') return err;
        if (typeof err.message === 'string' && err.message.trim()) return err.message;
        if (typeof err.reason === 'string' && err.reason.trim()) return err.reason;
        if (typeof err.code !== 'undefined' && typeof err.data !== 'undefined') {{
            return `Wallet error (${{err.code}}): ${{typeof err.data === 'string' ? err.data : JSON.stringify(err.data)}}`;
        }}
        if (typeof err === 'object') {{
            try {{
                return JSON.stringify(err);
            }} catch (_e) {{
                return String(err);
            }}
        }}
        return String(err);
    }}

    function resolveProvider() {{
        if (!window.ethereum) return null;
        if (Array.isArray(window.ethereum.providers) && window.ethereum.providers.length > 0) {{
            const mm = window.ethereum.providers.find((p) => p && p.isMetaMask);
            return mm || window.ethereum.providers[0];
        }}
        return window.ethereum;
    }}

    function requestWithTimeout(method, params, timeoutMs = 15000) {{
        if (!provider || typeof provider.request !== 'function') {{
            return Promise.reject(new Error('No compatible wallet provider found'));
        }}
        return Promise.race([
            provider.request({{ method, params }}),
            new Promise((_, reject) => setTimeout(() => reject(new Error('Wallet request timed out. Open your wallet app/extension and try again.')), timeoutMs)),
        ]);
    }}

    function showWalletHelp() {{
        setMsg('Wallet popup not opened. If you are on desktop, unlock MetaMask extension and retry. If you are on mobile, open in wallet browser using MetaMask QR.');
    }}

    function getDeepLink(mode) {{
        if (mode === 'metamask') {{
            const u = new URL(AUTH_URL);
            const dappPath = `${{u.host}}${{u.pathname}}${{u.search}}`;
            return `https://metamask.app.link/dapp/${{encodeURIComponent(dappPath)}}`;
        }}
        if (mode === 'trust') {{
            return `https://link.trustwallet.com/open_url?coin_id=60&url=${{AUTH_URL_ENC}}`;
        }}
        return AUTH_URL;
    }}

    function setQrMode(mode) {{
        qrMode = mode;
        const deepLink = getDeepLink(mode);
        document.getElementById('qrImg').src = `https://api.qrserver.com/v1/create-qr-code/?size=220x220&data=${{encodeURIComponent(deepLink)}}`;
        const note = document.getElementById('qrNote');
        if (!note) return;
        if (mode === 'metamask') {{
            note.innerHTML = 'Scan with MetaMask mobile to open and sign mandate directly';
        }} else if (mode === 'trust') {{
            note.innerHTML = 'Scan with Trust Wallet mobile to open and sign mandate directly';
        }} else {{
            note.innerHTML = 'Scan with any browser, then open in wallet browser to sign';
        }}
    }}

  function renderMeta() {{
    if (!cfg) return;
    const m = document.getElementById('meta');
    m.innerHTML = `
      <div class=\"box\"><div class=\"lbl\">Chain</div><div class=\"val\">${{cfg.chain}} (ID ${{cfg.chain_id}})</div></div>
      <div class=\"box\"><div class=\"lbl\">Amount</div><div class=\"val\">${{cfg.amount}} ${{cfg.token_symbol}}</div></div>
      <div class=\"box\"><div class=\"lbl\">Interval</div><div class=\"val\">${{cfg.interval}}</div></div>
      <div class=\"box\"><div class=\"lbl\">Subscription</div><div class=\"val\">${{cfg.subscription_id}}</div></div>
    `;
    document.getElementById('cryptoValue').textContent = `${{cfg.amount}} ${{cfg.token_symbol}}`;
    document.getElementById('chainValue').textContent = cfg.chain;
  }}

  async function loadConfig() {{
    const res = await fetch(`/subscribe/authorize/${{SUB_ID}}/config?email=${{encodeURIComponent(EMAIL)}}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Failed to load authorization config');
    cfg = data;
    renderMeta();
  }}

  async function ensureNetwork(chainIdDecimal) {{
    const targetHex = '0x' + Number(chainIdDecimal).toString(16);
        const currentHex = await requestWithTimeout('eth_chainId', undefined, 10000);
    if (currentHex.toLowerCase() === targetHex.toLowerCase()) return;
        await requestWithTimeout('wallet_switchEthereumChain', [{{ chainId: targetHex }}], 20000);
  }}

  async function startAuthorization() {{
    const btn = document.getElementById('signBtn');
    btn.disabled = true;
    try {{
            provider = resolveProvider();
            if (!provider) throw new Error('No EVM wallet detected. Open this page in a wallet browser.');
      if (!cfg) await loadConfig();

            // Prompt wallet site permissions up front to reduce 4100 unauthorized errors.
            try {{
                await requestWithTimeout('wallet_requestPermissions', [{{ eth_accounts: {{}} }}], 15000);
            }} catch (_permErr) {{
                // Some wallets may not support this method; continue with eth_requestAccounts.
            }}

      setStatus('Connecting wallet...');
      setMsg('Connecting wallet...');
    const accounts = await requestWithTimeout('eth_requestAccounts', undefined, 20000);
    let subscriber = pickSignerAddress(accounts);
      if (!subscriber) throw new Error('Wallet account not found');

      await ensureNetwork(cfg.chain_id);

      setStatus('Preparing signature payload...');
      setMsg('Preparing signature payload...');
            const signingPayload = {{
                subscriber,
                merchant_id: cfg.merchant_address,
                token_address: cfg.token_address,
                amount: cfg.amount_raw,
                interval: cfg.interval_seconds,
                max_payments: (cfg.max_payments && Number(cfg.max_payments) > 0) ? Number(cfg.max_payments) : 0,
                chain: cfg.chain,
                chain_id: cfg.chain_id,
            }};
            const signRes = await fetch('/web3-subscriptions/mandate/signing-data', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify(signingPayload)
      }});
            let signData = await signRes.json();
            if (!signRes.ok) {{
                let detailMessage = 'Failed to prepare signing data';
                if (Array.isArray(signData.detail)) {{
                    detailMessage = signData.detail.map((d) => d.msg || JSON.stringify(d)).join('; ');
                }} else if (typeof signData.detail === 'string') {{
                    detailMessage = signData.detail;
                }}
                throw new Error(detailMessage);
            }}

      setStatus('Waiting for signature...');
      setMsg('Please confirm the signature in your wallet...');
      const typedData = {{
        domain: signData.domain,
        types: {{ ...signData.types }},
        primaryType: signData.primaryType,
        message: signData.message,
      }};

            let signature = await requestWithTimeout('eth_signTypedData_v4', [subscriber, JSON.stringify(typedData)], 30000);

            // Some wallets may sign with a different active account than eth_requestAccounts returned.
            // Detect and recover automatically by regenerating typed data for recovered signer.
            let recovered = '';
            try {{
                recovered = ethers.verifyTypedData(signData.domain, signData.types, signData.message, signature);
            }} catch (_e) {{
                recovered = '';
            }}

            if (recovered && recovered.toLowerCase() !== subscriber.toLowerCase()) {{
                setStatus('Account mismatch detected...');
                setMsg(`Wallet signed with ${{recovered}}. Re-preparing mandate for this signer and requesting one corrected signature...`);

                const accounts2 = await requestWithTimeout('eth_requestAccounts', undefined, 20000);
                const hasRecovered = Array.isArray(accounts2) && accounts2.some((a) => String(a).toLowerCase() === recovered.toLowerCase());
                if (!hasRecovered) {{
                    throw new Error(`Wallet signed with ${{recovered}}, but this account is not connected for this site. In wallet: switch to ${{recovered}} and reconnect site, then retry.`);
                }}
                subscriber = recovered;

                const correctedPayload = {{
                    subscriber,
                    merchant_id: cfg.merchant_address,
                    token_address: cfg.token_address,
                    amount: cfg.amount_raw,
                    interval: cfg.interval_seconds,
                    max_payments: (cfg.max_payments && Number(cfg.max_payments) > 0) ? Number(cfg.max_payments) : 0,
                    chain: cfg.chain,
                    chain_id: cfg.chain_id,
                }};

                const correctedRes = await fetch('/web3-subscriptions/mandate/signing-data', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify(correctedPayload)
                }});
                const correctedData = await correctedRes.json();
                if (!correctedRes.ok) {{
                    let detailMessage = 'Failed to prepare corrected signing data';
                    if (Array.isArray(correctedData.detail)) {{
                        detailMessage = correctedData.detail.map((d) => d.msg || JSON.stringify(d)).join('; ');
                    }} else if (typeof correctedData.detail === 'string') {{
                        detailMessage = correctedData.detail;
                    }}
                    throw new Error(detailMessage);
                }}

                signData = correctedData;
                const correctedTypedData = {{
                    domain: signData.domain,
                    types: {{ ...signData.types }},
                    primaryType: signData.primaryType,
                    message: signData.message,
                }};
                setStatus('Waiting for corrected signature...');
                setMsg(`Please sign once more with active account ${{subscriber}}.`);
                signature = await requestWithTimeout('eth_signTypedData_v4', [subscriber, JSON.stringify(correctedTypedData)], 30000);
            }}

      setStatus('Creating subscription...');
      setMsg('Creating on-chain subscription...');
            const authorizePayload = {{
                signature,
                subscriber_address: subscriber,
                nonce: signData.nonce,
                merchant_id: cfg.merchant_id,
                token_address: cfg.token_address,
                token_symbol: cfg.token_symbol,
                amount: cfg.amount,
                interval: cfg.interval,
                chain: cfg.chain,
                chain_id: cfg.chain_id,
                customer_email: cfg.customer_email,
                customer_name: cfg.customer_name,
            }};
            if (cfg.max_payments && Number(cfg.max_payments) > 0) {{
                authorizePayload.max_payments = Number(cfg.max_payments);
            }}
      const authRes = await fetch('/web3-subscriptions/authorize', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify(authorizePayload)
      }});
      const authData = await authRes.json();
            if (!authRes.ok) {{
                let detailMessage = 'Subscription authorization failed';
                if (Array.isArray(authData.detail)) {{
                    detailMessage = authData.detail.map((d) => d.msg || JSON.stringify(d)).join('; ');
                }} else if (typeof authData.detail === 'string') {{
                    detailMessage = authData.detail;
                }}
                throw new Error(detailMessage);
            }}

      await fetch(`/subscribe/authorize/${{SUB_ID}}/complete`, {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ email: EMAIL, web3_subscription_id: authData.id }})
      }});

      setStatus('Authorized');
      setMsg('Subscription authorized. Redirecting...');
      setTimeout(() => {{ window.location.href = cfg.manage_url; }}, 700);
    }} catch (e) {{
      setStatus('Authorization failed');
            const msg = formatErr(e);
            setMsg(msg);
            if (msg.toLowerCase().includes('timed out')) {{
                showWalletHelp();
            }}
    }} finally {{
      btn.disabled = false;
    }}
  }}

    setQrMode(qrMode);
    if (!window.ethereum) {{
        setMsg(`No injected wallet detected in this browser. Open in wallet browser: ${{MM_DEEPLINK}}`);
    }}
  loadConfig().catch(e => setMsg(e.message || 'Failed to initialize'));
</script>
</body>
</html>"""

    return HTMLResponse(content=page)


@router.get("/subscribe/authorize/{subscription_id}/config")
async def subscription_authorize_config(
    request: Request,
    subscription_id: str,
    email: str = Query(..., description="Subscriber email for authorization"),
    db: Session = Depends(get_db),
):
    sub = db.query(Subscription).filter(Subscription.id == subscription_id).first()
    if not sub or sub.customer_email.lower() != email.lower():
        raise HTTPException(status_code=404, detail="Subscription not found")

    plan = sub.plan
    if not plan:
        raise HTTPException(status_code=400, detail="Plan not found")

    chain = str((plan.accepted_chains or ["polygon"])[0]).lower()
    if chain not in EVM_SIGNATURE_CHAINS:
        raise HTTPException(status_code=400, detail=f"Chain {chain} does not support mandate signing")
    if not _has_subscription_contract(chain):
        raise HTTPException(status_code=400, detail=f"Subscription contract not configured for {chain}")

    merchant_wallet = None
    wallets = db.query(MerchantWallet).filter(
        and_(MerchantWallet.merchant_id == plan.merchant_id, MerchantWallet.is_active == True)
    ).all()
    for w in wallets:
        cval = (w.chain.value if hasattr(w.chain, "value") else str(w.chain)).lower()
        if cval == chain:
            merchant_wallet = w.wallet_address
            break
    if not merchant_wallet:
        raise HTTPException(status_code=400, detail=f"Merchant wallet missing for {chain}")

    token_symbol = str((plan.accepted_tokens or ["USDC"])[0]).upper()
    token_address = _resolve_token_address(chain, token_symbol)
    chain_id = _chain_id_for(chain)
    if not chain_id:
        raise HTTPException(status_code=400, detail=f"Chain ID missing for {chain}")

    interval = plan.interval.value if hasattr(plan.interval, "value") else str(plan.interval)
    interval_seconds = INTERVAL_SECONDS.get(interval)
    if not interval_seconds:
        raise HTTPException(status_code=400, detail=f"Unsupported interval: {interval}")

    amount_fiat = Decimal(str(plan.amount))
    fiat_currency = (plan.fiat_currency or "USD").upper()
    amount = amount_fiat
    if fiat_currency != "USD":
        converted_usdc, _ = await convert_local_to_usdc(float(amount_fiat), fiat_currency)
        amount = Decimal(str(converted_usdc))

    amount_raw = int(amount * Decimal(10 ** 6))
    max_payments = int(plan.max_billing_cycles) if plan.max_billing_cycles else None

    base_url = str(request.base_url).rstrip("/")
    return {
        "subscription_id": sub.id,
        "merchant_id": str(plan.merchant_id),
        "merchant_address": merchant_wallet,
        "customer_email": sub.customer_email,
        "customer_name": sub.customer_name,
        "chain": chain,
        "chain_id": chain_id,
        "token_symbol": token_symbol,
        "token_address": token_address,
        "amount": float(amount),
        "amount_raw": amount_raw,
        "max_payments": max_payments,
        "interval": interval,
        "interval_seconds": interval_seconds,
        "manage_url": _build_manage_url(base_url, sub.id, sub.customer_email),
    }


@router.post("/subscribe/authorize/{subscription_id}/complete")
async def subscription_authorize_complete(
    subscription_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    body = await request.json()
    email = (body.get("email") or "").strip().lower()
    web3_subscription_id = body.get("web3_subscription_id")

    if not email:
        raise HTTPException(status_code=400, detail="Email is required")

    sub = db.query(Subscription).filter(Subscription.id == subscription_id).first()
    if not sub or sub.customer_email.lower() != email:
        raise HTTPException(status_code=404, detail="Subscription not found")

    sub.status = SubscriptionStatus.ACTIVE.value
    sub.updated_at = datetime.utcnow()
    metadata = sub.subscription_metadata or {}
    metadata.update({
        "authorization_completed": True,
        "web3_subscription_id": web3_subscription_id,
        "authorization_completed_at": datetime.utcnow().isoformat(),
    })
    sub.subscription_metadata = metadata
    db.commit()

    return {
        "message": "Subscription authorized",
        "subscription_id": sub.id,
        "status": sub.status,
        "web3_subscription_id": web3_subscription_id,
    }


@router.get("/subscribe/manage/{subscription_id}", response_class=HTMLResponse)
async def manage_subscription_page(
    request: Request,
    subscription_id: str,
    email: str = Query(..., description="Subscriber email for authorization"),
    db: Session = Depends(get_db),
):
    sub = db.query(Subscription).filter(Subscription.id == subscription_id).first()
    if not sub or sub.customer_email.lower() != email.lower():
        raise HTTPException(status_code=404, detail="Subscription not found")

    status = _status_value(sub.status)
    base_url = str(request.base_url).rstrip("/")

    page = f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1.0\">
  <title>Manage Subscription</title>
  <style>
    body{{font-family:Inter,Arial,sans-serif;background:#f4f6fb;padding:20px}}
    .card{{max-width:760px;margin:0 auto;background:#fff;border-radius:14px;padding:22px;box-shadow:0 8px 30px rgba(0,0,0,.08)}}
    h1{{margin:0 0 8px 0;font-size:22px}}
    .meta{{color:#475569;font-size:14px;margin-bottom:18px}}
    .status{{display:inline-block;padding:6px 10px;border-radius:999px;background:#eef2ff;color:#3730a3;font-size:12px;font-weight:700}}
    .grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:18px 0}}
    .box{{background:#f8fafc;padding:12px;border-radius:10px;border:1px solid #e2e8f0}}
    .lbl{{font-size:12px;color:#64748b}}
    .val{{font-weight:700;color:#0f172a;margin-top:4px}}
    .actions{{display:flex;flex-wrap:wrap;gap:10px;margin-top:18px}}
    button{{border:none;border-radius:10px;padding:10px 14px;font-weight:700;cursor:pointer}}
    .pay{{background:#1d4ed8;color:#fff}}
    .pause{{background:#f59e0b;color:#fff}}
    .resume{{background:#0ea5e9;color:#fff}}
    .cancel{{background:#dc2626;color:#fff}}
    .msg{{margin-top:14px;font-size:14px}}
  </style>
</head>
<body>
  <div class=\"card\">
    <h1>Manage Subscription</h1>
    <div class=\"meta\">Subscription <b>{sub.id}</b> · Email <b>{sub.customer_email}</b></div>
    <div class=\"status\">{status}</div>

    <div class=\"grid\">
      <div class=\"box\"><div class=\"lbl\">Plan</div><div class=\"val\">{sub.plan_id}</div></div>
      <div class=\"box\"><div class=\"lbl\">Next Payment</div><div class=\"val\">{sub.next_payment_at or '-'}</div></div>
    </div>

    <div class=\"actions\">
      <button class=\"pay\" onclick=\"actionCall('pay-now')\">Pay Due / Advance</button>
      <button class=\"pause\" onclick=\"actionCall('pause')\">Pause</button>
      <button class=\"resume\" onclick=\"actionCall('resume')\">Resume</button>
      <button class=\"cancel\" onclick=\"actionCall('cancel')\">Cancel</button>
    </div>

    <div id=\"msg\" class=\"msg\"></div>
  </div>

  <script>
    async function actionCall(action) {{
      const msg = document.getElementById('msg');
      msg.textContent = 'Processing...';
      const url = `{base_url}/subscribe/manage/{subscription_id}/` + action;
      const res = await fetch(url, {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ email: '{email}' }})
      }});
      const data = await res.json();
      if (!res.ok) {{
        msg.textContent = data.detail || 'Failed';
        return;
      }}
      if (data.checkout_url) {{
        window.location.href = data.checkout_url;
        return;
      }}
      msg.textContent = data.message || 'Done';
      setTimeout(() => window.location.reload(), 900);
    }}
  </script>
</body></html>"""

    return HTMLResponse(content=page)


@router.post("/subscribe/manage/{subscription_id}/pay-now")
async def manage_subscription_pay_now(
    request: Request,
    subscription_id: str,
    db: Session = Depends(get_db),
):
    body = await request.json()
    email = (body.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")

    sub = db.query(Subscription).filter(Subscription.id == subscription_id).first()
    if not sub or sub.customer_email.lower() != email:
        raise HTTPException(status_code=404, detail="Subscription not found")

    # Reuse latest pending payment session if available
    pending = (
        db.query(SubscriptionPayment)
        .filter(
            SubscriptionPayment.subscription_id == sub.id,
            SubscriptionPayment.status.in_([PaymentStatus.CREATED, PaymentStatus.PENDING]),
            SubscriptionPayment.payment_session_id.isnot(None),
        )
        .order_by(SubscriptionPayment.created_at.desc())
        .first()
    )

    base_url = str(request.base_url).rstrip("/")
    if pending and pending.payment_session_id:
        return {
            "message": "Continuing pending payment",
            "checkout_url": f"{base_url}/checkout/{pending.payment_session_id}",
        }

    # Create a fresh payment session via existing merchant route logic equivalent
    plan = sub.plan
    if not plan:
        raise HTTPException(status_code=400, detail="Plan not found")

    selected_chain = (sub.customer_chain or ((plan.accepted_chains or ["polygon"])[0])).lower()
    if selected_chain in EVM_SIGNATURE_CHAINS and _has_subscription_contract(selected_chain):
        return {
            "message": "Authorization required for subscription billing",
            "authorize_url": f"{base_url}/subscribe/authorize/{sub.id}?email={sub.customer_email}",
        }

    first_amount = plan.amount
    from app.services.currency_service import convert_local_to_usdc
    fiat_currency = (plan.fiat_currency or "USD").upper()
    amount_usdc = float(first_amount)
    if fiat_currency != "USD":
        amount_usdc, _ = await convert_local_to_usdc(float(first_amount), fiat_currency)

    # Wallet and chain selection
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

    session_id = f"pay_{secrets.token_urlsafe(12)}"
    ps = PaymentSession(
        id=session_id,
        merchant_id=sub.merchant_id,
        amount_fiat=first_amount,
        fiat_currency=fiat_currency,
        amount_token=str(amount_usdc),
        amount_usdc=str(amount_usdc),
        token=sub.customer_token or (plan.accepted_tokens[0] if plan.accepted_tokens else "USDC"),
        chain=sub.customer_chain or chain,
        accepted_tokens=plan.accepted_tokens,
        accepted_chains=plan.accepted_chains,
        merchant_wallet=merchant_wallet,
        status=PaymentStatus.CREATED,
        success_url="",
        cancel_url="",
        order_id=f"sub_{sub.id}_manual",
        session_metadata={
            "subscription_id": sub.id,
            "plan_id": plan.id,
            "type": "subscription_payment",
            "manual": True,
        },
        expires_at=datetime.utcnow() + timedelta(hours=48),
        collect_payer_data=False,
        payer_email=sub.customer_email,
        payer_name=sub.customer_name,
    )
    db.add(ps)

    sub_payment = SubscriptionPayment(
        subscription_id=sub.id,
        payment_session_id=session_id,
        period_start=sub.current_period_start,
        period_end=sub.current_period_end,
        amount=first_amount,
        fiat_currency=fiat_currency,
        status=PaymentStatus.CREATED,
    )
    db.add(sub_payment)
    db.commit()

    return {
        "message": "Payment session created",
        "checkout_url": f"{base_url}/checkout/{session_id}",
    }


@router.post("/subscribe/manage/{subscription_id}/pause")
async def manage_subscription_pause(
    request: Request,
    subscription_id: str,
    db: Session = Depends(get_db),
):
    body = await request.json()
    email = (body.get("email") or "").strip().lower()
    sub = db.query(Subscription).filter(Subscription.id == subscription_id).first()
    if not sub or sub.customer_email.lower() != email:
        raise HTTPException(status_code=404, detail="Subscription not found")

    current = _status_value(sub.status)
    if current not in [SubscriptionStatus.ACTIVE.value, SubscriptionStatus.TRIALING.value]:
        raise HTTPException(status_code=400, detail="Only active/trialing subscriptions can be paused")

    sub.status = SubscriptionStatus.PAUSED.value
    sub.updated_at = datetime.utcnow()
    db.commit()
    return {"message": "Subscription paused"}


@router.post("/subscribe/manage/{subscription_id}/resume")
async def manage_subscription_resume(
    request: Request,
    subscription_id: str,
    db: Session = Depends(get_db),
):
    body = await request.json()
    email = (body.get("email") or "").strip().lower()
    sub = db.query(Subscription).filter(Subscription.id == subscription_id).first()
    if not sub or sub.customer_email.lower() != email:
        raise HTTPException(status_code=404, detail="Subscription not found")

    if _status_value(sub.status) != SubscriptionStatus.PAUSED.value:
        raise HTTPException(status_code=400, detail="Only paused subscriptions can be resumed")

    sub.status = SubscriptionStatus.ACTIVE.value
    sub.updated_at = datetime.utcnow()
    db.commit()
    return {"message": "Subscription resumed"}


@router.post("/subscribe/manage/{subscription_id}/cancel")
async def manage_subscription_cancel(
    request: Request,
    subscription_id: str,
    db: Session = Depends(get_db),
):
    body = await request.json()
    email = (body.get("email") or "").strip().lower()
    sub = db.query(Subscription).filter(Subscription.id == subscription_id).first()
    if not sub or sub.customer_email.lower() != email:
        raise HTTPException(status_code=404, detail="Subscription not found")

    if _status_value(sub.status) == SubscriptionStatus.CANCELLED.value:
        raise HTTPException(status_code=400, detail="Subscription already cancelled")

    sub.status = SubscriptionStatus.CANCELLED.value
    sub.cancelled_at = datetime.utcnow()
    sub.cancel_at = datetime.utcnow()
    sub.updated_at = datetime.utcnow()
    db.commit()
    return {"message": "Subscription cancelled"}


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
