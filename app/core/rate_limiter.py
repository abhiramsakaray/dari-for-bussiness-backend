"""
Rate Limiting Middleware
Prevents brute-force attacks and API abuse
"""
import time
import logging
from typing import Dict, Tuple
from fastapi import Request, HTTPException, status
from collections import defaultdict
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class InMemoryRateLimiter:
    """
    Simple in-memory rate limiter for development/testing.
    For production, use Redis-backed rate limiting.
    """
    
    def __init__(self):
        # Store: {key: [(timestamp, count), ...]}
        self._store: Dict[str, list] = defaultdict(list)
        self._cleanup_interval = 60  # Cleanup old entries every 60 seconds
        self._last_cleanup = time.time()
    
    def _cleanup(self):
        """Remove expired entries to prevent memory leak"""
        now = time.time()
        if now - self._last_cleanup < self._cleanup_interval:
            return
        
        cutoff = now - 3600  # Keep last hour of data
        for key in list(self._store.keys()):
            self._store[key] = [
                (ts, count) for ts, count in self._store[key]
                if ts > cutoff
            ]
            if not self._store[key]:
                del self._store[key]
        
        self._last_cleanup = now
    
    def check_rate_limit(
        self,
        key: str,
        max_requests: int,
        window_seconds: int
    ) -> Tuple[bool, int, int]:
        """
        Check if request is within rate limit.
        
        Returns:
            (allowed, remaining, reset_time)
        """
        self._cleanup()
        
        now = time.time()
        window_start = now - window_seconds
        
        # Get requests in current window
        requests = self._store[key]
        requests_in_window = [
            (ts, count) for ts, count in requests
            if ts > window_start
        ]
        
        # Count total requests
        total_requests = sum(count for _, count in requests_in_window)
        
        if total_requests >= max_requests:
            # Rate limit exceeded
            oldest_request = min(ts for ts, _ in requests_in_window) if requests_in_window else now
            reset_time = int(oldest_request + window_seconds)
            return False, 0, reset_time
        
        # Allow request
        requests_in_window.append((now, 1))
        self._store[key] = requests_in_window
        
        remaining = max_requests - total_requests - 1
        reset_time = int(now + window_seconds)
        
        return True, remaining, reset_time


# Global rate limiter instance
_rate_limiter = InMemoryRateLimiter()


def get_client_ip(request: Request) -> str:
    """Extract client IP from request, handling proxies"""
    # Check X-Forwarded-For header (set by proxies/load balancers)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # Take first IP (client IP)
        return forwarded.split(",")[0].strip()
    
    # Check X-Real-IP header
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    
    # Fall back to direct connection IP
    if request.client:
        return request.client.host
    
    return "unknown"


def rate_limit(
    max_requests: int = 60,
    window_seconds: int = 60,
    key_prefix: str = "global"
):
    """
    Rate limiting decorator for FastAPI routes.
    
    Args:
        max_requests: Maximum requests allowed in window
        window_seconds: Time window in seconds
        key_prefix: Prefix for rate limit key (e.g., "auth", "api")
    
    Example:
        @router.post("/login")
        @rate_limit(max_requests=5, window_seconds=60, key_prefix="auth")
        async def login(...):
            ...
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Extract request from kwargs
            request = kwargs.get("request")
            if not request:
                # Try to find request in args
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break
            
            if not request:
                logger.warning("Rate limiter: No request object found")
                return await func(*args, **kwargs)
            
            # Build rate limit key
            client_ip = get_client_ip(request)
            rate_key = f"{key_prefix}:{client_ip}"
            
            # Check rate limit
            allowed, remaining, reset_time = _rate_limiter.check_rate_limit(
                rate_key, max_requests, window_seconds
            )
            
            if not allowed:
                logger.warning(
                    f"Rate limit exceeded for {client_ip} on {key_prefix}: "
                    f"{max_requests} requests per {window_seconds}s"
                )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded. Try again in {reset_time - int(time.time())} seconds.",
                    headers={
                        "X-RateLimit-Limit": str(max_requests),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(reset_time),
                        "Retry-After": str(reset_time - int(time.time()))
                    }
                )
            
            # Add rate limit headers to response
            response = await func(*args, **kwargs)
            
            # If response is a Response object, add headers
            if hasattr(response, "headers"):
                response.headers["X-RateLimit-Limit"] = str(max_requests)
                response.headers["X-RateLimit-Remaining"] = str(remaining)
                response.headers["X-RateLimit-Reset"] = str(reset_time)
            
            return response
        
        return wrapper
    return decorator


class RateLimitMiddleware:
    """
    Global rate limiting middleware.
    Applies to all requests unless excluded.
    """
    
    def __init__(
        self,
        app,
        max_requests: int = 100,
        window_seconds: int = 60,
        exclude_paths: list = None
    ):
        self.app = app
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.exclude_paths = exclude_paths or ["/health", "/metrics", "/docs", "/redoc", "/openapi.json"]
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        # Check if path is excluded
        path = scope["path"]
        if any(path.startswith(excluded) for excluded in self.exclude_paths):
            await self.app(scope, receive, send)
            return
        
        # Extract client IP
        headers = dict(scope.get("headers", []))
        forwarded = headers.get(b"x-forwarded-for", b"").decode()
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()
        else:
            client_ip = scope.get("client", ["unknown"])[0]
        
        # Check rate limit
        rate_key = f"global:{client_ip}"
        allowed, remaining, reset_time = _rate_limiter.check_rate_limit(
            rate_key, self.max_requests, self.window_seconds
        )
        
        if not allowed:
            logger.warning(
                f"Global rate limit exceeded for {client_ip}: "
                f"{self.max_requests} requests per {self.window_seconds}s"
            )
            
            # Send 429 response
            response_body = b'{"detail":"Rate limit exceeded. Please try again later."}'
            await send({
                "type": "http.response.start",
                "status": 429,
                "headers": [
                    [b"content-type", b"application/json"],
                    [b"x-ratelimit-limit", str(self.max_requests).encode()],
                    [b"x-ratelimit-remaining", b"0"],
                    [b"x-ratelimit-reset", str(reset_time).encode()],
                    [b"retry-after", str(reset_time - int(time.time())).encode()],
                ]
            })
            await send({
                "type": "http.response.body",
                "body": response_body
            })
            return
        
        # Continue with request
        await self.app(scope, receive, send)
