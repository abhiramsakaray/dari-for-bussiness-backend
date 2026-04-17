"""
PCI-DSS Compliance Enforcement
Runtime validation of network segmentation and data handling
"""
import logging
from typing import Optional
from fastapi import Request, HTTPException
from app.core.config import settings

logger = logging.getLogger(__name__)


class PCIDSSEnvironment:
    """
    PCI-DSS environment classification and enforcement.
    
    Ensures proper network segmentation between CDE and non-CDE.
    """
    
    # CDE endpoints (handle cardholder data)
    CDE_ENDPOINTS = {
        "/api/payments",
        "/api/sessions",
        "/checkout",
        "/api/refunds",
        "/webhooks",
    }
    
    # Non-CDE endpoints
    NON_CDE_ENDPOINTS = {
        "/api/merchant",
        "/api/analytics",
        "/api/team",
        "/api/admin",
        "/health",
        "/metrics",
    }
    
    @staticmethod
    def is_cde_endpoint(path: str) -> bool:
        """Check if endpoint is in CDE"""
        for cde_path in PCIDSSEnvironment.CDE_ENDPOINTS:
            if path.startswith(cde_path):
                return True
        return False
    
    @staticmethod
    def validate_environment_access(request: Request):
        """
        Validate that request is accessing appropriate environment.
        
        PCI-DSS Requirement 1.2.1 - Network segmentation
        """
        path = request.url.path
        is_cde = PCIDSSEnvironment.is_cde_endpoint(path)
        
        # Check environment tag
        environment_tag = getattr(settings, 'ENVIRONMENT_TAG', 'non-cde')
        
        if is_cde and environment_tag != 'cde':
            logger.error(
                f"PCI-DSS violation: CDE endpoint {path} accessed from "
                f"non-CDE environment ({environment_tag})"
            )
            raise HTTPException(
                status_code=403,
                detail="Access denied: CDE endpoint requires CDE environment"
            )
        
        # Log CDE access
        if is_cde:
            logger.info(
                f"CDE access: {path} from {request.client.host if request.client else 'unknown'}"
            )
    
    @staticmethod
    def get_database_url(is_cde: bool = False) -> str:
        """
        Get appropriate database URL based on environment.
        
        CDE operations use separate database connection.
        """
        if is_cde and hasattr(settings, 'CDE_DATABASE_URL'):
            return settings.CDE_DATABASE_URL
        return settings.DATABASE_URL
    
    @staticmethod
    def mask_card_data(data: str) -> str:
        """
        Mask sensitive card data for logging.
        
        PCI-DSS Requirement 3.3 - Mask PAN when displayed
        """
        if not data or len(data) < 13:
            return data
        
        # Mask all but last 4 digits
        return f"{'*' * (len(data) - 4)}{data[-4:]}"


class PCIDSSMiddleware:
    """
    Middleware to enforce PCI-DSS network segmentation.
    """
    
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        # Validate environment access
        from fastapi import Request
        request = Request(scope, receive)
        
        try:
            PCIDSSEnvironment.validate_environment_access(request)
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
        
        await self.app(scope, receive, send)


def require_cde_environment():
    """
    Dependency to require CDE environment for sensitive operations.
    
    Usage:
        @router.post("/process-payment")
        async def process_payment(
            _: None = Depends(require_cde_environment)
        ):
            ...
    """
    environment_tag = getattr(settings, 'ENVIRONMENT_TAG', 'non-cde')
    if environment_tag != 'cde':
        raise HTTPException(
            status_code=403,
            detail="This operation requires CDE environment"
        )
