"""
Activity Log API Routes
View team member activity logs for audit trail
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional
import logging

from app.core.database import get_db
from app.core.team_middleware import get_current_team_member
from app.core.permissions import get_effective_permissions, has_permission
from app.core.activity_logger import get_activity_logs
from app.models.models import MerchantUser
from app.schemas.schemas import ActivityLogResponse, ActivityLogList

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/team", tags=["Activity Logs"])
router_v1 = APIRouter(prefix="/api/v1/team", tags=["Activity Logs API v1"])


@router.get("/activity-logs", response_model=ActivityLogList)
@router_v1.get("/activity-logs", response_model=ActivityLogList)
async def list_activity_logs(
    team_member_id: Optional[str] = Query(None, description="Filter by team member ID"),
    action: Optional[str] = Query(None, description="Filter by action code (e.g., 'team.login')"),
    resource_type: Optional[str] = Query(None, description="Filter by resource type (e.g., 'payment')"),
    start_date: Optional[datetime] = Query(None, description="Filter from date"),
    end_date: Optional[datetime] = Query(None, description="Filter to date"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    current_team_member: MerchantUser = Depends(get_current_team_member),
    db: Session = Depends(get_db),
):
    """
    Query activity logs with filtering and pagination.
    
    Requires team.view_logs permission.
    Logs are scoped to the current merchant.
    """
    # Check permission
    permissions = await get_effective_permissions(str(current_team_member.id), db)
    if not has_permission(permissions, "team.view_logs"):
        raise HTTPException(
            status_code=403,
            detail="Permission denied: team.view_logs required"
        )
    
    # Build filters
    filters = {
        "team_member_id": team_member_id,
        "action": action,
        "resource_type": resource_type,
        "start_date": start_date,
        "end_date": end_date,
        "page": page,
        "page_size": page_size,
    }
    
    # Get logs
    logs, total = await get_activity_logs(
        merchant_id=str(current_team_member.merchant_id),
        filters=filters,
        db=db,
    )
    
    # Build response
    log_responses = []
    for log in logs:
        # Get team member info if available
        member_email = None
        member_name = None
        if log.team_member:
            member_email = log.team_member.email
            member_name = log.team_member.name
        
        log_responses.append(
            ActivityLogResponse(
                id=str(log.id),
                team_member_id=str(log.team_member_id) if log.team_member_id else None,
                team_member_email=member_email,
                team_member_name=member_name,
                action=log.action,
                resource_type=log.resource_type,
                resource_id=log.resource_id,
                details=log.details,
                ip_address=log.ip_address,
                user_agent=log.user_agent,
                created_at=log.created_at,
            )
        )
    
    return ActivityLogList(
        items=log_responses,
        total=total,
        page=page,
        page_size=page_size,
    )
