"""
Activity Logger Service
Logs team member actions for audit trail
"""
from datetime import datetime
from typing import Optional, Dict, List
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from fastapi import Request
import uuid

from app.models.models import ActivityLog, MerchantUser


async def log_activity(
    merchant_id: str,
    team_member_id: Optional[str],
    action: str,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    details: Optional[Dict] = None,
    request: Optional[Request] = None,
    db: Optional[Session] = None
):
    """
    Log a team member activity
    
    Args:
        merchant_id: Merchant UUID
        team_member_id: Team member UUID (None for unauthenticated actions)
        action: Action code (e.g., 'team.login', 'payment.create')
        resource_type: Type of resource affected (e.g., 'payment', 'invoice')
        resource_id: ID of resource affected
        details: Additional details as JSON
        request: FastAPI request object (for IP and user agent)
        db: Database session
    """
    if not db:
        return
    
    # Extract request metadata
    ip_address = None
    user_agent = None
    if request:
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")
    
    # Create activity log
    log = ActivityLog(
        merchant_id=uuid.UUID(merchant_id),
        team_member_id=uuid.UUID(team_member_id) if team_member_id else None,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        ip_address=ip_address,
        user_agent=user_agent
    )
    
    db.add(log)
    db.commit()


async def log_login(team_member: MerchantUser, request: Request, db: Session):
    """
    Log successful login
    
    Args:
        team_member: MerchantUser instance
        request: FastAPI request object
        db: Database session
    """
    await log_activity(
        merchant_id=str(team_member.merchant_id),
        team_member_id=str(team_member.id),
        action="team.login",
        details={
            "email": team_member.email,
            "role": team_member.role.value
        },
        request=request,
        db=db
    )


async def log_logout(team_member: MerchantUser, request: Request, db: Session):
    """
    Log logout
    
    Args:
        team_member: MerchantUser instance
        request: FastAPI request object
        db: Database session
    """
    await log_activity(
        merchant_id=str(team_member.merchant_id),
        team_member_id=str(team_member.id),
        action="team.logout",
        details={
            "email": team_member.email
        },
        request=request,
        db=db
    )


async def log_failed_login(email: str, merchant_id: str, request: Request, db: Session):
    """
    Log failed login attempt
    
    Args:
        email: Email address attempted
        merchant_id: Merchant UUID
        request: FastAPI request object
        db: Database session
    """
    await log_activity(
        merchant_id=merchant_id,
        team_member_id=None,
        action="team.login_failed",
        details={
            "email": email,
            "reason": "Invalid credentials"
        },
        request=request,
        db=db
    )


async def log_permission_change(
    team_member_id: str,
    merchant_id: str,
    action: str,
    details: Dict,
    db: Session
):
    """
    Log permission change (grant/revoke)
    
    Args:
        team_member_id: Team member UUID whose permissions changed
        merchant_id: Merchant UUID
        action: Action code ('team.permission_granted' or 'team.permission_revoked')
        details: Details about the change
        db: Database session
    """
    await log_activity(
        merchant_id=merchant_id,
        team_member_id=team_member_id,
        action=action,
        resource_type="permission",
        details=details,
        db=db
    )


async def log_password_reset(
    team_member_id: str,
    merchant_id: str,
    reset_by: Optional[str],
    request: Optional[Request],
    db: Session
):
    """
    Log password reset
    
    Args:
        team_member_id: Team member UUID whose password was reset
        merchant_id: Merchant UUID
        reset_by: UUID of team member who initiated reset (None if self-service)
        request: FastAPI request object
        db: Database session
    """
    await log_activity(
        merchant_id=merchant_id,
        team_member_id=team_member_id,
        action="team.password_reset",
        details={
            "reset_by": reset_by,
            "self_service": reset_by is None
        },
        request=request,
        db=db
    )


async def log_session_revoked(
    team_member_id: str,
    merchant_id: str,
    revoked_by: str,
    sessions_count: int,
    db: Session
):
    """
    Log session revocation
    
    Args:
        team_member_id: Team member UUID whose sessions were revoked
        merchant_id: Merchant UUID
        revoked_by: UUID of team member who revoked sessions
        sessions_count: Number of sessions revoked
        db: Database session
    """
    await log_activity(
        merchant_id=merchant_id,
        team_member_id=team_member_id,
        action="team.session_revoked",
        details={
            "revoked_by": revoked_by,
            "sessions_count": sessions_count
        },
        db=db
    )


async def get_activity_logs(
    merchant_id: str,
    filters: Dict,
    db: Session
) -> tuple[List[ActivityLog], int]:
    """
    Get activity logs with filtering and pagination
    
    Args:
        merchant_id: Merchant UUID
        filters: Filter parameters (team_member_id, action, resource_type, start_date, end_date, page, page_size)
        db: Database session
        
    Returns:
        Tuple of (logs list, total count)
    """
    query = db.query(ActivityLog).filter(
        ActivityLog.merchant_id == uuid.UUID(merchant_id)
    )
    
    # Apply filters
    if filters.get("team_member_id"):
        query = query.filter(
            ActivityLog.team_member_id == uuid.UUID(filters["team_member_id"])
        )
    
    if filters.get("action"):
        query = query.filter(ActivityLog.action == filters["action"])
    
    if filters.get("resource_type"):
        query = query.filter(ActivityLog.resource_type == filters["resource_type"])
    
    if filters.get("start_date"):
        query = query.filter(ActivityLog.created_at >= filters["start_date"])
    
    if filters.get("end_date"):
        query = query.filter(ActivityLog.created_at <= filters["end_date"])
    
    # Get total count
    total = query.count()
    
    # Apply pagination
    page = filters.get("page", 1)
    page_size = filters.get("page_size", 50)
    offset = (page - 1) * page_size
    
    logs = query.order_by(
        ActivityLog.created_at.desc()
    ).offset(offset).limit(page_size).all()
    
    return logs, total
