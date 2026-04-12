"""
Team Member Permission Middleware
Provides authentication dependency and permission enforcement decorator
"""
from functools import wraps
from typing import List, Callable
from fastapi import Header, HTTPException, Depends, Request
from sqlalchemy.orm import Session
import jwt

from app.core.database import get_db
from app.core.team_auth import verify_token
from app.core.sessions import validate_session, update_session_activity
from app.core.permissions import get_effective_permissions, has_permission
from app.core.activity_logger import log_activity
from app.models.models import MerchantUser


async def get_current_team_member(
    authorization: str = Header(None),
    db: Session = Depends(get_db)
) -> MerchantUser:
    """
    Dependency to extract and validate JWT token, return authenticated team member
    
    Args:
        authorization: Authorization header (Bearer <token>)
        db: Database session
        
    Returns:
        Authenticated MerchantUser instance
        
    Raises:
        HTTPException: 401 if authentication fails
    """
    # Check for authorization header
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid authorization header"
        )
    
    # Extract token
    token = authorization.split(" ")[1]
    
    # Verify JWT token
    try:
        payload = verify_token(token, "access")
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail="Token has expired"
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=401,
            detail=f"Invalid token: {str(e)}"
        )
    except ValueError as e:
        raise HTTPException(
            status_code=401,
            detail=str(e)
        )
    
    # Get team member from database
    team_member = db.query(MerchantUser).filter(
        MerchantUser.id == payload["sub"]
    ).first()
    
    if not team_member:
        raise HTTPException(
            status_code=401,
            detail="Team member not found"
        )
    
    if not team_member.is_active:
        raise HTTPException(
            status_code=401,
            detail="Team member account is inactive"
        )
    
    # Validate session
    session = await validate_session(token, db)
    if not session:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired session"
        )
    
    # Update session activity
    await update_session_activity(str(session.id), db)
    
    return team_member


def require_permissions(*required_permissions: str):
    """
    Decorator to enforce permissions on API endpoints
    
    Usage:
        @router.post("/payments")
        @require_permissions("payments.create")
        async def create_payment(
            data: PaymentCreate,
            current_team_member: MerchantUser = Depends(get_current_team_member),
            db: Session = Depends(get_db)
        ):
            # Endpoint logic
            pass
    
    Args:
        *required_permissions: One or more permission codes required
        
    Returns:
        Decorator function
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(
            *args,
            current_team_member: MerchantUser = Depends(get_current_team_member),
            request: Request = None,
            db: Session = Depends(get_db),
            **kwargs
        ):
            # Get effective permissions for team member
            permissions = await get_effective_permissions(
                str(current_team_member.id), db
            )
            
            # Check each required permission
            for permission in required_permissions:
                if not has_permission(permissions, permission):
                    # Log permission denial
                    await log_activity(
                        merchant_id=str(current_team_member.merchant_id),
                        team_member_id=str(current_team_member.id),
                        action="permission_denied",
                        resource_type="endpoint",
                        details={
                            "required_permission": permission,
                            "endpoint": func.__name__,
                            "user_permissions": permissions
                        },
                        request=request,
                        db=db
                    )
                    
                    # Return 403 Forbidden
                    raise HTTPException(
                        status_code=403,
                        detail={
                            "message": f"Missing required permission: {permission}",
                            "error_code": "PERMISSION_DENIED",
                            "required_permission": permission,
                            "user_permissions": permissions
                        }
                    )
            
            # All permissions validated, execute endpoint
            return await func(
                *args,
                current_team_member=current_team_member,
                request=request,
                db=db,
                **kwargs
            )
        
        return wrapper
    return decorator
