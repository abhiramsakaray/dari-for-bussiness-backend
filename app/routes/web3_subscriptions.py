"""
Web3 Subscriptions API Routes

REST API endpoints for the hybrid Web3 recurring payment system.

Endpoints:
  - Merchant: manage subscriptions, view payments, analytics
  - User: authorize mandates, cancel subscriptions
  - Admin: relayer status, scheduler health
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
import logging

from app.models.models import MerchantWallet

from app.core.database import get_db
from app.core import require_merchant
from app.schemas.web3_schemas import (
    CreateWeb3SubscriptionRequest,
    CancelWeb3SubscriptionRequest,
    UserCancelRequest,
    MandateSigningRequest,
    MandateSigningResponse,
    Web3SubscriptionResponse,
    Web3SubscriptionListResponse,
    Web3PaymentResponse,
    Web3PaymentListResponse,
    Web3AnalyticsResponse,
    RelayerStatusResponse,
    SchedulerStatusResponse,
    HealthCheckResponse,
)
from app.services.web3_subscription_service import Web3SubscriptionService
from app.services.mandate_service import MandateService
from app.services.gasless_relayer import relayer
from app.services.subscription_scheduler import scheduler

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/web3-subscriptions", tags=["Web3 Subscriptions"])


# ============= HELPERS =============

def _sub_to_response(sub) -> dict:
    """Convert a Web3Subscription model to response dict"""
    return {
        "id": str(sub.id),
        "onchain_subscription_id": sub.onchain_subscription_id,
        "chain": sub.chain,
        "contract_address": sub.contract_address,
        "subscriber_address": sub.subscriber_address,
        "merchant_address": sub.merchant_address,
        "token_symbol": sub.token_symbol,
        "amount": str(sub.amount),
        "interval_seconds": sub.interval_seconds,
        "next_payment_at": sub.next_payment_at,
        "status": sub.status.value if hasattr(sub.status, 'value') else sub.status,
        "failed_payment_count": sub.failed_payment_count,
        "total_payments": sub.total_payments,
        "total_amount_collected": str(sub.total_amount_collected),
        "customer_email": sub.customer_email,
        "customer_name": sub.customer_name,
        "created_tx_hash": sub.created_tx_hash,
        "cancelled_tx_hash": sub.cancelled_tx_hash,
        "created_at": sub.created_at,
        "cancelled_at": sub.cancelled_at,
    }


def _payment_to_response(p) -> dict:
    """Convert a Web3SubscriptionPayment model to response dict"""
    return {
        "id": str(p.id),
        "subscription_id": str(p.subscription_id),
        "amount": str(p.amount),
        "token_symbol": p.token_symbol,
        "chain": p.chain,
        "payment_number": p.payment_number,
        "period_start": p.period_start,
        "period_end": p.period_end,
        "tx_hash": p.tx_hash,
        "block_number": p.block_number,
        "status": p.status.value if hasattr(p.status, 'value') else p.status,
        "created_at": p.created_at,
        "confirmed_at": p.confirmed_at,
    }


# ============= MANDATE ENDPOINTS =============

@router.post("/mandate/signing-data", response_model=MandateSigningResponse)
async def get_mandate_signing_data(
    request: MandateSigningRequest,
    db: Session = Depends(get_db),
):
    """
    Generate EIP-712 typed data for a subscription mandate.
    
    The frontend should present this to the user's wallet for signing.
    Returns the complete EIP-712 structure for eth_signTypedData_v4.
    """
    # Resolve the merchant's actual wallet address for this chain.
    # CRITICAL: this MUST be the same address used during signature verification
    # in verify_and_create_mandate(), otherwise the recovered signer will never
    # match the expected subscriber.
    chain_str = request.chain.value
    merchant_wallet = (
        db.query(MerchantWallet)
        .filter(
            MerchantWallet.merchant_id == request.merchant_id,
            MerchantWallet.chain == chain_str,
            MerchantWallet.is_active == True,
        )
        .first()
    )
    if not merchant_wallet:
        raise HTTPException(
            status_code=400,
            detail=f"Merchant has no active wallet on {chain_str}. "
                   "Cannot generate signing data.",
        )

    mandate_service = MandateService(db)
    try:
        signing_data = mandate_service.get_signing_data(
            subscriber=request.subscriber,
            merchant=merchant_wallet.wallet_address,   # ← real address, not UUID
            token=request.token_address,
            amount=request.amount,
            interval=request.interval,
            max_payments=request.max_payments,
            chain=chain_str,
            chain_id=request.chain_id,
        )
        return signing_data
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============= SUBSCRIPTION CREATION =============

@router.post("/authorize", response_model=Web3SubscriptionResponse)
async def authorize_subscription(
    request: CreateWeb3SubscriptionRequest,
    db: Session = Depends(get_db),
):
    """
    Authorize and create a new Web3 subscription.

    Flow:
    1. User signs EIP-712 mandate in their wallet
    2. Frontend submits signature + details to this endpoint
    3. Backend verifies signature, creates on-chain subscription via relayer
    4. Returns subscription details

    The user must have already approved the subscription contract
    to spend their tokens (ERC20 approve).
    """
    service = Web3SubscriptionService(db)
    # Pass the exact amount_raw used during signing to avoid float rounding issues
    if request.amount_raw:
        service._amount_raw_override = request.amount_raw

    try:
        sub = await service.create_subscription(
            signature=request.signature,
            subscriber_address=request.subscriber_address,
            merchant_id=request.merchant_id or "",
            plan_id=request.plan_id,
            token_address=request.token_address,
            token_symbol=request.token_symbol.value,
            amount=request.amount or 0,
            interval=request.interval.value,
            chain=request.chain.value,
            chain_id=request.chain_id,
            max_payments=request.max_payments,
            customer_email=request.customer_email,
            customer_name=request.customer_name,
            nonce=request.nonce,
        )
        return _sub_to_response(sub)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Subscription creation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Subscription creation failed")


@router.post("/debug/verify-sig")
async def debug_verify_signature(
    payload: dict,
    db: Session = Depends(get_db),
):
    """
    Debug endpoint: attempt to recover the EIP-712 signer for a given signature.
    Returns the recovered address so you can compare with what the frontend expects.

    Required payload fields:
      signature, subscriber, merchant_address, token_address,
      amount_raw, interval_seconds, chain_id, chain (e.g. "polygon"),
      verifying_contract, nonce
    Optional:
      max_payments (default 0)
    """
    from app.services.mandate_service import MandateService, DARI_DOMAIN_BASE
    from web3 import Web3
    try:
        signature        = payload["signature"]
        subscriber       = payload["subscriber"]
        merchant_address = payload["merchant_address"]
        token_address    = payload["token_address"]
        amount_raw       = int(payload["amount_raw"])
        interval_seconds = int(payload["interval_seconds"])
        max_payments     = int(payload.get("max_payments", 0))
        nonce            = int(payload["nonce"])
        chain_id         = int(payload["chain_id"])
        verifying_contract = payload["verifying_contract"]

        domain_data = {
            **DARI_DOMAIN_BASE,
            "chainId": chain_id,
            "verifyingContract": Web3.to_checksum_address(verifying_contract),
        }
        # chainId is NOT a struct field — it belongs to the domain only
        message_data = {
            "subscriber":  Web3.to_checksum_address(subscriber),
            "merchant":    Web3.to_checksum_address(merchant_address),
            "token":       Web3.to_checksum_address(token_address),
            "amount":      amount_raw,
            "interval":    interval_seconds,
            "maxPayments": max_payments,
            "nonce":       nonce,
        }

        svc = MandateService(db)
        recovered = svc._recover_signer(signature, domain_data, message_data)
        return {
            "recovered": recovered,
            "subscriber": subscriber,
            "match": recovered.lower() == subscriber.lower(),
            "domain": domain_data,
            "message": message_data,
        }
    except Exception as e:
        return {"error": str(e)}


# ============= MERCHANT ENDPOINTS =============

@router.get("/", response_model=Web3SubscriptionListResponse)
async def list_subscriptions(
    status: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant),
):
    """List all Web3 subscriptions for the authenticated merchant"""
    service = Web3SubscriptionService(db)
    result = service.list_merchant_subscriptions(
        merchant_id=current_user["merchant_id"],
        status=status,
        page=page,
        page_size=page_size,
    )
    return {
        "subscriptions": [_sub_to_response(s) for s in result["subscriptions"]],
        "total": result["total"],
        "page": result["page"],
        "page_size": result["page_size"],
    }


@router.get("/analytics", response_model=Web3AnalyticsResponse)
async def get_analytics(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant),
):
    """Get Web3 subscription analytics for the authenticated merchant"""
    service = Web3SubscriptionService(db)
    return service.get_merchant_analytics(current_user["merchant_id"])


@router.get("/{subscription_id}", response_model=Web3SubscriptionResponse)
async def get_subscription(
    subscription_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant),
):
    """Get a specific Web3 subscription"""
    service = Web3SubscriptionService(db)
    sub = service.get_subscription(subscription_id)
    if not sub or str(sub.merchant_id) != current_user["merchant_id"]:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return _sub_to_response(sub)


@router.post("/{subscription_id}/cancel")
async def cancel_subscription(
    subscription_id: str,
    request: CancelWeb3SubscriptionRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant),
):
    """Cancel a Web3 subscription (merchant-initiated)"""
    service = Web3SubscriptionService(db)
    try:
        sub = await service.cancel_subscription(
            subscription_id=subscription_id,
            cancelled_by="merchant",
            merchant_id=current_user["merchant_id"],
        )
        return {
            "message": "Subscription cancelled",
            "subscription": _sub_to_response(sub),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{subscription_id}/payments", response_model=Web3PaymentListResponse)
async def list_payments(
    subscription_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant),
):
    """List all payments for a Web3 subscription"""
    service = Web3SubscriptionService(db)
    
    # Verify ownership
    sub = service.get_subscription(subscription_id)
    if not sub or str(sub.merchant_id) != current_user["merchant_id"]:
        raise HTTPException(status_code=404, detail="Subscription not found")

    result = service.list_subscription_payments(subscription_id, page, page_size)
    return {
        "payments": [_payment_to_response(p) for p in result["payments"]],
        "total": result["total"],
        "page": result["page"],
        "page_size": result["page_size"],
    }


# ============= USER / PUBLIC ENDPOINTS =============

@router.post("/user/cancel")
async def user_cancel_subscription(
    request: UserCancelRequest,
    db: Session = Depends(get_db),
):
    """
    Cancel a subscription (user-initiated).
    
    The subscriber address must match the subscription's subscriber.
    """
    service = Web3SubscriptionService(db)
    try:
        sub = await service.cancel_subscription(
            subscription_id=request.subscription_id,
            cancelled_by="subscriber",
            subscriber_address=request.subscriber_address,
        )
        return {
            "message": "Subscription cancelled",
            "subscription_id": str(sub.id),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/user/{address}")
async def get_user_subscriptions(
    address: str,
    db: Session = Depends(get_db),
):
    """Get all subscriptions for a subscriber wallet address"""
    service = Web3SubscriptionService(db)
    subs = service.list_subscriber_subscriptions(address)
    return {
        "subscriber_address": address.lower(),
        "subscriptions": [_sub_to_response(s) for s in subs],
        "total": len(subs),
    }


# ============= ADMIN ENDPOINTS =============

@router.get("/admin/relayer-status", response_model=RelayerStatusResponse)
async def get_relayer_status(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant),
):
    """Get relayer wallet balances and health status"""
    return {
        "balances": relayer.get_all_balances(),
        "address": relayer.address,
    }


@router.get("/admin/scheduler-status", response_model=SchedulerStatusResponse)
async def get_scheduler_status(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant),
):
    """Get scheduler status and metrics"""
    return scheduler.get_status()


@router.get("/admin/health/{subscription_id}", response_model=HealthCheckResponse)
async def check_subscription_health(
    subscription_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant),
):
    """
    Check subscription health (DB vs on-chain state).
    
    Useful for debugging state drift or verifying consistency.
    """
    service = Web3SubscriptionService(db)
    result = service.check_subscription_health(subscription_id)
    if "error" in result and result["error"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result
