"""
CSRF Protection Middleware
Protects against Cross-Site Request Forgery attacks
"""
import secrets
import hmac
import hashlib
import logging
from typing import Optional
from fastapi import Request, HTTPException, status
from fastapi.responses import Response
from app.core.config import settings

logger = logging.getLogger(__name__)


class CSRFProtection:
    """
    CSRF protection using double-submit cookie pattern.
    
    How it works:
    1. Server generates CSRF token and sets it in cookie
    2. Client includes token in request header (X-CSRF-Token)
    3. Server validates that cookie token matches header token
    """
    
    COOKIE_NAME = "csrf_token"
    HEADER_NAME = "X-CSRF-Token"
    COOKIE_MAX_AGE = 3600  # 1 hour
    
    # Methods that require CSRF protection
    PROTECTED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
    
    # Paths excluded from CSRF protection
    EXCLUDED_PATHS = {
        "/health",
        "/metrics",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/auth/login",  # Login uses rate limiting instead
        "/auth/register",
        "/auth/google",
        "/checkout/",  # Public checkout pages
    }
    
    @staticmethod
    def generate_token() -> str:
        """Generate a cryptographically secure CSRF token"""
        return secrets.token_urlsafe(32)
    
    @staticmethod
    def create_signed_token(token: str) -> str:
        """
        Create HMAC-signed token to prevent tampering.
        Format: <token>.<signature>
        """
        signature = hmac.new(
            settings.JWT_SECRET.encode(),
            token.encode(),
            hashlib.sha256
        ).hexdigest()[:16]  # First 16 chars of signature
        return f"{token}.{signature}"
    
    @staticmethod
    def verify_signed_token(signed_token: str) -> Optional[str]:
        """
        Verify HMAC signature and extract token.
        Returns token if valid, None if invalid.
        """
        try:
            parts = signed_token.split(".")
            if len(parts) != 2:
                return None
            
            token, signature = parts
            expected_signature = hmac.new(
                settings.JWT_SECRET.encode(),
                token.encode(),
                hashlib.sha256
            ).hexdigest()[:16]
            
            # Constant-time comparison
            if not hmac.compare_digest(signature, expected_signature):
                return None
            
            return token
        except Exception as e:
            logger.error(f"CSRF token verification failed: {e}")
            return None
    
    @staticmethod
    def is_path_excluded(path: str) -> bool:
        """Check if path is excluded from CSRF protection"""
        for excluded in CSRFProtection.EXCLUDED_PATHS:
            if path.startswith(excluded):
                return True
        return False
    
    @staticmethod
    async def validate_csrf(request: Request) -> bool:
        """
        Validate CSRF token from request.
        
        Args:
            request: FastAPI Request object
        
        Returns:
            True if valid, raises HTTPException if invalid
        """
        # Skip if method doesn't require protection
        if request.method not in CSRFProtection.PROTECTED_METHODS:
            return True
        
        # Skip if path is excluded
        if CSRFProtection.is_path_excluded(request.url.path):
            return True
        
        # Get token from cookie
        cookie_token = request.cookies.get(CSRFProtection.COOKIE_NAME)
        if not cookie_token:
            logger.warning(f"CSRF validation failed: No cookie token for {request.url.path}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF token missing in cookie"
            )
        
        # Get token from header
        header_token = request.headers.get(CSRFProtection.HEADER_NAME)
        if not header_token:
            logger.warning(f"CSRF validation failed: No header token for {request.url.path}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF token missing in header"
            )
        
        # Verify cookie token signature
        verified_cookie_token = CSRFProtection.verify_signed_token(cookie_token)
        if not verified_cookie_token:
            logger.warning(f"CSRF validation failed: Invalid cookie token signature")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid CSRF token signature"
            )
        
        # Compare tokens (constant-time)
        if not hmac.compare_digest(verified_cookie_token, header_token):
            logger.warning(f"CSRF validation failed: Token mismatch")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF token mismatch"
            )
        
        return True
    
    @staticmethod
    def set_csrf_cookie(response: Response) -> Response:
        """
        Set CSRF token cookie in response.
        
        Args:
            response: FastAPI Response object
        
        Returns:
            Response with CSRF cookie set
        """
        token = CSRFProtection.generate_token()
        signed_token = CSRFProtection.create_signed_token(token)
        
        response.set_cookie(
            key=CSRFProtection.COOKIE_NAME,
            value=signed_token,
            max_age=CSRFProtection.COOKIE_MAX_AGE,
            httponly=True,  # Prevent JavaScript access
            secure=settings.ENVIRONMENT == "production",  # HTTPS only in production
            samesite="strict"  # Strict same-site policy
        )
        
        # Also set token in response header for client to read
        response.headers[CSRFProtection.HEADER_NAME] = token
        
        return response


class CSRFMiddleware:
    """
    CSRF protection middleware for FastAPI.
    Automatically validates CSRF tokens on protected requests.
    """
    
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        # Create request object
        from fastapi import Request
        request = Request(scope, receive)
        
        # Validate CSRF for protected methods
        if request.method in CSRFProtection.PROTECTED_METHODS:
            if not CSRFProtection.is_path_excluded(request.url.path):
                try:
                    await CSRFProtection.validate_csrf(request)
                except HTTPException as e:
                    # Send 403 response
                    response_body = f'{{"detail":"{e.detail}"}}'.encode()
                    await send({
                        "type": "http.response.start",
                        "status": e.status_code,
                        "headers": [[b"content-type", b"application/json"]]
                    })
                    await send({
                        "type": "http.response.body",
                        "body": response_body
                    })
                    return
        
        # Continue with request
        await self.app(scope, receive, send)


# Dependency for manual CSRF validation
async def require_csrf(request: Request) -> bool:
    """
    FastAPI dependency to require CSRF validation.
    
    Usage:
        @router.post("/sensitive-operation")
        async def operation(csrf_valid: bool = Depends(require_csrf)):
            ...
    """
    return await CSRFProtection.validate_csrf(request)
