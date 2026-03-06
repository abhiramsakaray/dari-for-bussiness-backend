"""
Idempotency Middleware
Prevents duplicate API operations using idempotency keys
"""
from fastapi import Request, Response, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import hashlib
import json
from typing import Optional, Callable

from app.core.database import get_db
from app.models.models import IdempotencyKey


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """
    Middleware to handle idempotency keys for POST/PUT/PATCH requests.
    
    Usage:
        Include header: Idempotency-Key: <unique-key>
        
    Behavior:
        1. If key not seen before: Process request, store response
        2. If key seen and processing: Return 409 Conflict
        3. If key seen and completed: Return stored response
    """
    
    IDEMPOTENT_METHODS = ["POST", "PUT", "PATCH"]
    IDEMPOTENCY_HEADER = "Idempotency-Key"
    KEY_EXPIRY_HOURS = 24
    
    # Endpoints that support idempotency
    IDEMPOTENT_ENDPOINTS = [
        "/api/v1/payments",
        "/api/v1/payment-links",
        "/api/v1/invoices",
        "/api/v1/subscriptions",
        "/api/v1/refunds",
    ]
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Only process idempotent methods
        if request.method not in self.IDEMPOTENT_METHODS:
            return await call_next(request)
        
        # Check if endpoint supports idempotency
        if not self._endpoint_supports_idempotency(request.url.path):
            return await call_next(request)
        
        # Get idempotency key from header
        idempotency_key = request.headers.get(self.IDEMPOTENCY_HEADER)
        if not idempotency_key:
            # No key provided, process normally
            return await call_next(request)
        
        # Get merchant ID from auth (if available)
        merchant_id = getattr(request.state, 'merchant_id', None)
        if not merchant_id:
            # Try to extract from API key header
            # This is a simplified check - actual auth happens in route
            return await call_next(request)
        
        # Check database for existing key
        db: Session = next(get_db())
        try:
            existing = db.query(IdempotencyKey).filter(
                IdempotencyKey.key == idempotency_key,
                IdempotencyKey.merchant_id == merchant_id
            ).first()
            
            if existing:
                return await self._handle_existing_key(existing, request, db)
            
            # Create new idempotency record
            return await self._process_with_idempotency(
                idempotency_key, merchant_id, request, call_next, db
            )
        finally:
            db.close()
    
    def _endpoint_supports_idempotency(self, path: str) -> bool:
        """Check if the endpoint supports idempotency"""
        for endpoint in self.IDEMPOTENT_ENDPOINTS:
            if path.startswith(endpoint):
                return True
        return False
    
    async def _handle_existing_key(
        self, 
        existing: IdempotencyKey, 
        request: Request,
        db: Session
    ) -> Response:
        """Handle an existing idempotency key"""
        # Check if expired
        if existing.expires_at < datetime.utcnow():
            # Key expired, delete and process as new
            db.delete(existing)
            db.commit()
            return None  # Signal to process as new
        
        # Check if still processing
        if existing.is_processing and not existing.completed:
            raise HTTPException(
                status_code=409,
                detail="A request with this idempotency key is still being processed"
            )
        
        # Return cached response
        if existing.completed and existing.response_body:
            return Response(
                content=json.dumps(existing.response_body),
                status_code=existing.response_code or 200,
                media_type="application/json",
                headers={"Idempotency-Key-Status": "cached"}
            )
        
        # Something went wrong, process as new
        db.delete(existing)
        db.commit()
        return None
    
    async def _process_with_idempotency(
        self,
        key: str,
        merchant_id: str,
        request: Request,
        call_next: Callable,
        db: Session
    ) -> Response:
        """Process request with idempotency tracking"""
        # Create hash of request body for validation
        body = await request.body()
        request_hash = hashlib.sha256(body).hexdigest() if body else None
        
        # Create idempotency record
        idempotency_record = IdempotencyKey(
            key=key,
            merchant_id=merchant_id,
            endpoint=request.url.path,
            request_hash=request_hash,
            is_processing=True,
            completed=False,
            expires_at=datetime.utcnow() + timedelta(hours=self.KEY_EXPIRY_HOURS)
        )
        
        db.add(idempotency_record)
        db.commit()
        
        try:
            # Process the actual request
            response = await call_next(request)
            
            # Read response body
            response_body = b""
            async for chunk in response.body_iterator:
                response_body += chunk
            
            # Store response
            try:
                response_json = json.loads(response_body.decode())
            except (json.JSONDecodeError, UnicodeDecodeError):
                response_json = {"raw": response_body.decode(errors='ignore')}
            
            idempotency_record.response_code = response.status_code
            idempotency_record.response_body = response_json
            idempotency_record.is_processing = False
            idempotency_record.completed = True
            db.commit()
            
            # Return new response with body
            return Response(
                content=response_body,
                status_code=response.status_code,
                media_type=response.media_type,
                headers=dict(response.headers)
            )
            
        except Exception as e:
            # Mark as failed
            idempotency_record.is_processing = False
            idempotency_record.completed = False
            db.commit()
            raise


def get_idempotency_info(
    idempotency_key: str,
    merchant_id: str,
    db: Session
) -> Optional[dict]:
    """
    Get information about an idempotency key.
    
    Used by API endpoints to check key status.
    """
    record = db.query(IdempotencyKey).filter(
        IdempotencyKey.key == idempotency_key,
        IdempotencyKey.merchant_id == merchant_id
    ).first()
    
    if not record:
        return None
    
    return {
        "key": record.key,
        "endpoint": record.endpoint,
        "status": "processing" if record.is_processing else ("completed" if record.completed else "failed"),
        "created_at": record.created_at.isoformat(),
        "expires_at": record.expires_at.isoformat()
    }


async def check_idempotency_key(
    idempotency_key: Optional[str],
    merchant_id: str,
    endpoint: str,
    request_body: dict,
    db: Session
) -> Optional[dict]:
    """
    Check idempotency key before processing a request.
    
    This is an alternative to middleware for more control.
    
    Returns:
        - None if no cached response (proceed with processing)
        - Dict with cached response if key was already processed
        
    Raises:
        - HTTPException 409 if key is currently being processed
    """
    if not idempotency_key:
        return None
    
    existing = db.query(IdempotencyKey).filter(
        IdempotencyKey.key == idempotency_key,
        IdempotencyKey.merchant_id == merchant_id
    ).first()
    
    if not existing:
        # Create new record
        request_hash = hashlib.sha256(
            json.dumps(request_body, sort_keys=True).encode()
        ).hexdigest()
        
        record = IdempotencyKey(
            key=idempotency_key,
            merchant_id=merchant_id,
            endpoint=endpoint,
            request_hash=request_hash,
            is_processing=True,
            completed=False,
            expires_at=datetime.utcnow() + timedelta(hours=24)
        )
        db.add(record)
        db.commit()
        return None
    
    # Check if expired
    if existing.expires_at < datetime.utcnow():
        db.delete(existing)
        db.commit()
        return None
    
    # Check if processing
    if existing.is_processing and not existing.completed:
        raise HTTPException(
            status_code=409,
            detail="A request with this idempotency key is currently being processed"
        )
    
    # Return cached response
    if existing.completed and existing.response_body:
        return existing.response_body
    
    return None


async def save_idempotency_response(
    idempotency_key: str,
    merchant_id: str,
    response_code: int,
    response_body: dict,
    db: Session
):
    """
    Save the response for an idempotency key after processing.
    """
    record = db.query(IdempotencyKey).filter(
        IdempotencyKey.key == idempotency_key,
        IdempotencyKey.merchant_id == merchant_id
    ).first()
    
    if record:
        record.response_code = response_code
        record.response_body = response_body
        record.is_processing = False
        record.completed = True
        db.commit()
