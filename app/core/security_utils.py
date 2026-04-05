"""
Endpoint Security Utilities for Dari for Business

Provides:
  - IDOR (Insecure Direct Object Reference) protection
  - Input sanitization / XSS prevention
  - SQL injection guard (for raw queries, if any)
  - Webhook signature timestamp validation
  - Strict UUID validation
  - IP-based account lockout
  - Content-type enforcement
  - Audit logging helpers
"""

import re
import uuid
import time
import hmac
import hashlib
import html
import logging
from typing import Optional
from collections import defaultdict
from functools import wraps

from fastapi import HTTPException, Request, status

logger = logging.getLogger(__name__)


# ── UUID Validation ──

def validate_uuid(value: str, field_name: str = "id") -> uuid.UUID:
    """
    Strictly validate that a string is a valid UUID v4.
    Prevents path traversal and injection via ID parameters.
    """
    try:
        parsed = uuid.UUID(value, version=4)
        if str(parsed) != value.lower().strip():
            # Catches cases where extra chars were accepted
            raise ValueError()
        return parsed
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {field_name} format"
        )


# ── IDOR Protection ──

def verify_resource_ownership(
    resource_merchant_id,
    current_user_id: str,
    resource_name: str = "resource",
):
    """
    Verify the current authenticated user owns the requested resource.
    Prevents IDOR attacks where one merchant accesses another's data.
    """
    resource_id_str = str(resource_merchant_id)
    if resource_id_str != current_user_id:
        logger.warning(
            f"IDOR attempt: user {current_user_id} tried to access "
            f"{resource_name} owned by {resource_id_str}"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{resource_name.capitalize()} not found"
        )


# ── Input Sanitization ──

# Dangerous patterns for SQL injection
_SQL_INJECTION_PATTERNS = re.compile(
    r"(--|;|'|\b(SELECT|INSERT|UPDATE|DELETE|DROP|ALTER|UNION|OR|AND)\b\s)",
    re.IGNORECASE,
)

# Dangerous patterns for command injection
_CMD_INJECTION_PATTERNS = re.compile(
    r"[`$|;&]|\b(cat|ls|rm|wget|curl|bash|sh|python|node|eval|exec)\b",
    re.IGNORECASE,
)


def sanitize_string(value: str, max_length: int = 500) -> str:
    """
    Sanitize a user-provided string:
    - Escape HTML entities (prevents XSS)
    - Strip null bytes
    - Enforce max length
    - Strip leading/trailing whitespace
    """
    if not value:
        return value
    # Remove null bytes
    value = value.replace("\x00", "")
    # Strip whitespace
    value = value.strip()
    # Enforce length
    value = value[:max_length]
    # Escape HTML
    value = html.escape(value, quote=True)
    return value


def check_sql_injection(value: str, field_name: str = "input") -> None:
    """
    Check if a string contains SQL injection patterns.
    Raises HTTP 400 if suspicious.
    """
    if _SQL_INJECTION_PATTERNS.search(value):
        logger.warning(f"Potential SQL injection in {field_name}: {value[:100]}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid characters in {field_name}"
        )


def check_command_injection(value: str, field_name: str = "input") -> None:
    """
    Check if a string contains command injection patterns.
    Raises HTTP 400 if suspicious.
    """
    if _CMD_INJECTION_PATTERNS.search(value):
        logger.warning(f"Potential command injection in {field_name}: {value[:100]}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid characters in {field_name}"
        )


def sanitize_email(email: str) -> str:
    """Validate and sanitize an email address."""
    email = email.strip().lower()
    if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid email format"
        )
    if len(email) > 254:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email address too long"
        )
    return email


def sanitize_wallet_address(address: str, chain: str = "evm") -> str:
    """Validate wallet address format based on chain."""
    address = address.strip()
    if chain in ("ethereum", "polygon", "base", "bsc", "arbitrum", "evm"):
        if not re.match(r"^0x[a-fA-F0-9]{40}$", address):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid EVM wallet address"
            )
    elif chain == "stellar":
        if not re.match(r"^G[A-Z2-7]{55}$", address):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Stellar address"
            )
    elif chain == "tron":
        if not re.match(r"^T[a-zA-Z0-9]{33}$", address):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Tron address"
            )
    elif chain == "solana":
        if not re.match(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$", address):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Solana address"
            )
    return address


def sanitize_tx_hash(tx_hash: str, chain: str = "evm") -> str:
    """Validate transaction hash format."""
    tx_hash = tx_hash.strip()
    if chain in ("ethereum", "polygon", "base", "bsc", "arbitrum", "evm"):
        if not re.match(r"^0x[a-fA-F0-9]{64}$", tx_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid transaction hash"
            )
    elif chain == "stellar":
        if not re.match(r"^[a-f0-9]{64}$", tx_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Stellar transaction hash"
            )
    return tx_hash


# ── Account Lockout (brute-force prevention) ──

_login_attempts: dict[str, list[float]] = defaultdict(list)
_LOCKOUT_WINDOW_SECONDS = 900  # 15 minutes
_MAX_LOGIN_ATTEMPTS = 5


def check_account_lockout(identifier: str) -> None:
    """
    Check if an account/IP is locked out due to too many failed login attempts.
    Identifier can be email or IP.
    """
    now = time.monotonic()
    window_start = now - _LOCKOUT_WINDOW_SECONDS
    _login_attempts[identifier] = [
        t for t in _login_attempts[identifier] if t > window_start
    ]
    if len(_login_attempts[identifier]) >= _MAX_LOGIN_ATTEMPTS:
        remaining = int(
            _LOCKOUT_WINDOW_SECONDS - (now - _login_attempts[identifier][0])
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Account locked. Try again in {remaining} seconds.",
        )


def record_failed_login(identifier: str) -> None:
    """Record a failed login attempt."""
    _login_attempts[identifier].append(time.monotonic())


def clear_login_attempts(identifier: str) -> None:
    """Clear login attempts after successful authentication."""
    _login_attempts.pop(identifier, None)


# ── Webhook Signature Verification (for receiving webhooks) ──

def verify_webhook_timestamp(
    signature_header: str,
    max_age_seconds: int = 300,
) -> tuple[str, str]:
    """
    Parse and validate webhook signature header format:
    t=<unix_timestamp>,v1=<hmac_hex>
    
    Returns (timestamp, signature) tuple.
    Raises HTTP 401 if invalid or expired.
    """
    if not signature_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing signature header"
        )

    parts = {}
    for part in signature_header.split(","):
        if "=" in part:
            key, _, val = part.partition("=")
            parts[key.strip()] = val.strip()

    ts = parts.get("t")
    sig = parts.get("v1")

    if not ts or not sig:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid signature format"
        )

    try:
        ts_int = int(ts)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid timestamp in signature"
        )

    age = abs(time.time() - ts_int)
    if age > max_age_seconds:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Signature expired (replay protection)"
        )

    return ts, sig


def verify_webhook_signature(
    body: bytes,
    timestamp: str,
    signature: str,
    secret: str,
) -> bool:
    """
    Verify HMAC-SHA256 webhook signature using constant-time comparison.
    """
    expected = hmac.new(
        secret.encode(),
        f"{timestamp}.{body.decode()}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


# ── Content-Type Enforcement ──

def enforce_json_content_type(request: Request) -> None:
    """
    Ensure POST/PUT/PATCH requests have application/json content type.
    Prevents CSRF attacks via form submissions.
    """
    if request.method in ("POST", "PUT", "PATCH"):
        content_type = request.headers.get("content-type", "")
        if "application/json" not in content_type and "multipart/form-data" not in content_type:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Content-Type must be application/json"
            )


# ── Audit Logging ──

def audit_log(
    action: str,
    user_id: str,
    resource_type: str,
    resource_id: str,
    details: Optional[str] = None,
    ip_address: Optional[str] = None,
):
    """
    Log a security-relevant action for audit trail.
    """
    logger.info(
        f"AUDIT | action={action} user={user_id} "
        f"resource={resource_type}:{resource_id} "
        f"ip={ip_address or 'unknown'} "
        f"details={details or ''}"
    )
