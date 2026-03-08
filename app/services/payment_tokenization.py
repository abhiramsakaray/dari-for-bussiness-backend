"""
Payment Tokenization Service

Provides secure tokenization of sensitive payment data so that raw
amounts, wallet addresses, and payer details are never sent over the
wire in plain text after the initial checkout flow.

A *payment token* is a short-lived opaque reference that the frontend
uses to finalize a payment.  The backend resolves the token to the
real data server-side.

Tokens are stored in an in-memory TTL cache (not the database) because
they are ephemeral — they only live until the checkout completes or
expires.
"""

import hashlib
import hmac
import secrets
import time
import logging
from typing import Any, Optional
from datetime import datetime, timedelta

from app.core.config import settings

logger = logging.getLogger(__name__)

# Token TTL — matches the default payment session expiry
_TOKEN_TTL_SECONDS = settings.PAYMENT_EXPIRY_MINUTES * 60

# In-memory token vault (thread-safe enough for single-process uvicorn)
_vault: dict[str, dict[str, Any]] = {}


def _prune():
    """Remove expired tokens (lazy GC)."""
    now = time.monotonic()
    expired = [k for k, v in _vault.items() if now > v["_expires"]]
    for k in expired:
        del _vault[k]


def create_payment_token(session_id: str, data: dict) -> str:
    """
    Tokenize payment session data.

    Parameters
    ----------
    session_id : str
        The related payment session ID (e.g. ``pay_xxx``).
    data : dict
        Sensitive fields to store — e.g. ``amount_token``, ``chain``,
        ``wallet_address``, ``payer_email``, etc.

    Returns
    -------
    str
        An opaque token prefixed with ``ptok_``.
    """
    _prune()

    token_id = f"ptok_{secrets.token_urlsafe(32)}"
    _vault[token_id] = {
        **data,
        "session_id": session_id,
        "_created": time.monotonic(),
        "_expires": time.monotonic() + _TOKEN_TTL_SECONDS,
    }
    logger.debug("Created payment token %s for session %s", token_id, session_id)
    return token_id


def resolve_payment_token(token_id: str) -> Optional[dict]:
    """
    Resolve a payment token back to real data.

    Returns ``None`` if the token is invalid or expired.
    """
    _prune()
    entry = _vault.get(token_id)
    if entry is None:
        return None
    # Strip internal metadata
    return {k: v for k, v in entry.items() if not k.startswith("_")}


def revoke_payment_token(token_id: str):
    """Manually revoke a token (e.g. after successful payment)."""
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
