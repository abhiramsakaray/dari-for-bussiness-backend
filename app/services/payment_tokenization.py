"""
Payment Tokenization Service

Provides secure tokenization of sensitive payment data so that raw
amounts, wallet addresses, and payer details are never sent over the
wire in plain text after the initial checkout flow.

A *payment token* is a short-lived opaque reference that the frontend
uses to finalize a payment.  The backend resolves the token to the
real data server-side.

Storage backend:
  - Redis (preferred) — distributed, survives restarts
  - In-memory dict   — automatic fallback when Redis is unavailable
"""

import hashlib
import hmac
import json
import secrets
import time
import logging
from typing import Any, Optional
from datetime import datetime, timedelta

from app.core.config import settings

logger = logging.getLogger(__name__)

# Token TTL — matches the default payment session expiry
_TOKEN_TTL_SECONDS = settings.PAYMENT_EXPIRY_MINUTES * 60

# ── Redis client (lazy init) ──
_redis_client = None
_redis_available = False


def _get_redis():
    """Get or initialize Redis client. Returns None if unavailable."""
    global _redis_client, _redis_available
    if not settings.REDIS_ENABLED:
        return None
    if _redis_client is not None:
        return _redis_client if _redis_available else None
    try:
        import redis
        _redis_client = redis.Redis.from_url(
            settings.REDIS_URL,
            db=settings.REDIS_TOKEN_DB,
            decode_responses=True,
            socket_connect_timeout=3,
        )
        _redis_client.ping()
        _redis_available = True
        logger.info("Token vault connected to Redis")
        return _redis_client
    except Exception as e:
        logger.warning("Redis unavailable, using in-memory vault: %s", e)
        _redis_available = False
        return None


# ── In-memory fallback vault ──
_vault: dict[str, dict[str, Any]] = {}


def _prune():
    """Remove expired tokens from in-memory vault (lazy GC)."""
    now = time.monotonic()
    expired = [k for k, v in _vault.items() if now > v["_expires"]]
    for k in expired:
        del _vault[k]


def _redis_key(token_id: str) -> str:
    return f"ptok:{token_id}"


def create_payment_token(session_id: str, data: dict) -> str:
    """
    Tokenize payment session data.

    Stores in Redis if available, otherwise falls back to in-memory vault.

    Parameters
    ----------
    session_id : str
        The related payment session ID (e.g. ``pay_xxx``).
    data : dict
        Sensitive fields to store.

    Returns
    -------
    str
        An opaque token prefixed with ``ptok_``.
    """
    token_id = f"ptok_{secrets.token_urlsafe(32)}"

    r = _get_redis()
    if r is not None:
        try:
            payload = {**data, "session_id": session_id}
            r.setex(_redis_key(token_id), _TOKEN_TTL_SECONDS, json.dumps(payload, default=str))
            logger.debug("Created token %s in Redis for session %s", token_id, session_id)
            return token_id
        except Exception as e:
            logger.warning("Redis write failed, falling back to in-memory: %s", e)

    # In-memory fallback
    _prune()
    _vault[token_id] = {
        **data,
        "session_id": session_id,
        "_created": time.monotonic(),
        "_expires": time.monotonic() + _TOKEN_TTL_SECONDS,
    }
    logger.debug("Created token %s in-memory for session %s", token_id, session_id)
    return token_id


def build_session_token_payload(session) -> dict:
    """
    Build the standard tokenization payload from a PaymentSession ORM object.
    Includes dual currency and cross-border fields.
    """
    payload = {
        "session_id": session.id,
        "amount_fiat": str(session.amount_fiat),
        "fiat_currency": session.fiat_currency,
        "amount_token": session.amount_token or session.amount_usdc or "0",
        "token": session.token or "USDC",
        "chain": session.chain or "stellar",
        "merchant_id": str(session.merchant_id),
    }

    # Add dual currency data
    if session.payer_currency:
        payload["payer_currency"] = session.payer_currency
        payload["payer_currency_symbol"] = session.payer_currency_symbol or ""
        payload["payer_amount_local"] = str(session.payer_amount_local or 0)
        payload["payer_exchange_rate"] = str(session.payer_exchange_rate or 0)

    if session.merchant_currency:
        payload["merchant_currency"] = session.merchant_currency
        payload["merchant_currency_symbol"] = session.merchant_currency_symbol or ""
        payload["merchant_amount_local"] = str(session.merchant_amount_local or 0)
        payload["merchant_exchange_rate"] = str(session.merchant_exchange_rate or 0)

    # Cross-border flags
    payload["is_cross_border"] = session.is_cross_border or False
    if session.payer_country:
        payload["payer_country"] = session.payer_country

    return payload


def auto_tokenize_session(session) -> str:
    """
    Automatically tokenize a payment session at creation time.
    Returns the payment token string.
    """
    payload = build_session_token_payload(session)
    token_id = create_payment_token(session.id, payload)
    return token_id


def resolve_payment_token(token_id: str) -> Optional[dict]:
    """
    Resolve a payment token back to real data.

    Checks Redis first, then in-memory vault.
    Returns ``None`` if the token is invalid or expired.
    """
    r = _get_redis()
    if r is not None:
        try:
            raw = r.get(_redis_key(token_id))
            if raw is not None:
                return json.loads(raw)
        except Exception as e:
            logger.warning("Redis read failed: %s", e)

    # In-memory fallback
    _prune()
    entry = _vault.get(token_id)
    if entry is None:
        return None
    return {k: v for k, v in entry.items() if not k.startswith("_")}


def revoke_payment_token(token_id: str):
    """Manually revoke a token (e.g. after successful payment)."""
    r = _get_redis()
    if r is not None:
        try:
            r.delete(_redis_key(token_id))
        except Exception as e:
            logger.warning("Redis delete failed: %s", e)
    _vault.pop(token_id, None)


def sign_payload(payload: dict) -> str:
    """
    Produce an HMAC-SHA256 signature of a dict so the client can
    verify the checkout data hasn't been tampered with.
    """
    canonical = "&".join(f"{k}={payload[k]}" for k in sorted(payload))
    return hmac.new(
        settings.API_KEY_SECRET.encode(),
        canonical.encode(),
        hashlib.sha256,
    ).hexdigest()


def verify_signature(payload: dict, signature: str) -> bool:
    """Verify an HMAC-SHA256 signature."""
    expected = sign_payload(payload)
    return hmac.compare_digest(expected, signature)
