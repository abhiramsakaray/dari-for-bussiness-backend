"""
Permission Management API Routes
View and manage team member permissions
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import and_
import uuid
import logging

from app.core.database import get_db
from app.core.team_middleware import get_current_team_member
from app.core.permissions import (
    get_all_permissions,
    get_role_permissions,
    get_effective_permissions,
    get_custom_permissions,
    grant_permission,
    revoke_permission,
    has_permission,
    ROLE_PERMISSIONS,
)
from app.core.activity_logger import log_permission_change
from app.models.models import MerchantUser, MerchantRole
from app.schemas.schemas import (
    PermissionResponse,
    RolePermissionsResponse,
    MemberPermissionsResponse,
    UpdatePermissionsRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/team", tags=["Permissions"])
router_v1 = APIRouter(prefix="/api/v1/team", tags=["Permissions API v1"])


@router.get("/permissions", response_model=list[PermissionResponse])
@router_v1.get("/permissions", response_model=list[PermissionResponse])
async def list_all_permissions(
    current_team_member: MerchantUser = Depends(get_current_team_member),
    db: Session = Depends(get_db),
):
    """
    List all available permissions in the system.
    Any authenticated team member can view available permissions.
    """
    permissions = await get_all_permissions(db)
    
    return [
        PermissionResponse(
            code=p["code"],
            name=p["name"],
            description=p.get("description"),
            category=p.get("category"),
        )
        for p in permissions
    ]


@router.get("/roles/{role}/permissions", response_model=RolePermissionsResponse)
@router_v1.get("/roles/{role}/permissions", response_model=RolePermissionsResponse)
async def get_role_permission_list(
    role: str,
    current_team_member: MerchantUser = Depends(get_current_team_member),
    db: Session = Depends(get_db),
):
    """
    Get all permissions assigned to a specific role.
    """
    # Validate role
    valid_roles = [r.value for r in MerchantRole]
    if role not in valid_roles:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role. Must be one of: {', '.join(valid_roles)}"
        )
    
    # Get role permissions from database
    role_perms = await get_role_permissions(role, db)
    
    # Build response with permission details
    all_perms = await get_all_permissions(db)
    perm_map = {p["code"]: p for p in all_perms}
    
    permission_responses = []
    for code in role_perms:
        if code == "*":
            # Owner has all permissions
            permission_responses = [
                PermissionResponse(
                    code=p["code"],
                    name=p["name"],
                    description=p.get("description"),
                    category=p.get("category"),
                )
                for p in all_perms
            ]
            break
        
        if code in perm_map:
            p = perm_map[code]
            permission_responses.append(
                PermissionResponse(
                    code=p["code"],
                    name=p["name"],
                    description=p.get("description"),
                    category=p.get("category"),
                )
            )
    
    return RolePermissionsResponse(
        role=role,
        permissions=permission_responses,
    )


@router.get("/members/{member_id}/permissions", response_model=MemberPermissionsResponse)
@router_v1.get("/members/{member_id}/permissions", response_model=MemberPermissionsResponse)
async def get_member_permissions(
    member_id: str,
    current_team_member: MerchantUser = Depends(get_current_team_member),
    db: Session = Depends(get_db),
):
    """
    Get a team member's effective permissions (role permissions + custom grants - custom revokes).
    Requires team.view permission or viewing your own permissions.
    """
    # Allow viewing own permissions or require team.view
    if str(current_team_member.id) != member_id:
        own_perms = await get_effective_permissions(str(current_team_member.id), db)
        if not has_permission(own_perms, "team.view"):
            raise HTTPException(
                status_code=403,
                detail="Permission denied: team.view required"
            )
    
    # Find the member
    target_member = db.query(MerchantUser).filter(
        and_(
            MerchantUser.id == member_id,
            MerchantUser.merchant_id == current_team_member.merchant_id,
        )
    ).first()
    
    if not target_member:
        raise HTTPException(status_code=404, detail="Team member not found")
    
    # Get role permissions
    role_perms = await get_role_permissions(target_member.role.value, db)
    
    # Get custom permissions
    custom = await get_custom_permissions(member_id, db)
    
    # Get effective permissions
    effective = await get_effective_permissions(member_id, db)
    
    return MemberPermissionsResponse(
        member_id=member_id,
        role=target_member.role.value,
        role_permissions=role_perms,
        custom_granted=custom["granted"],
        custom_revoked=custom["revoked"],
        effective_permissions=effective,
    )


@router.post("/members/{member_id}/permissions")
@router_v1.post("/members/{member_id}/permissions")
async def update_member_permissions(
    member_id: str,
    perm_data: UpdatePermissionsRequest,
    current_team_member: MerchantUser = Depends(get_current_team_member),
    db: Session = Depends(get_db),
):
    """
    Grant or revoke custom permissions for a team member.
    Requires team.update permission and the target member must be in the same merchant.
    Cannot modify owner permissions.
    """
    # Check current user has team.update permission
    own_perms = await get_effective_permissions(str(current_team_member.id), db)
    if not has_permission(own_perms, "team.update"):
        raise HTTPException(
            status_code=403,
            detail="Permission denied: team.update required"
        )
    
    # Find target member
    target_member = db.query(MerchantUser).filter(
        and_(
            MerchantUser.id == member_id,
            MerchantUser.merchant_id == current_team_member.merchant_id,
        )
    ).first()
    
    if not target_member:
        raise HTTPException(status_code=404, detail="Team member not found")
    
    # Cannot modify owner permissions
    if target_member.role == MerchantRole.OWNER:
        raise HTTPException(
            status_code=400,
            detail="Cannot modify permissions for the account owner"
        )
    
    results = {"granted": [], "revoked": [], "errors": []}
    
    # Process grants
    if perm_data.grant:
        for perm_code in perm_data.grant:
            success = await grant_permission(
                team_member_id=member_id,
                permission_code=perm_code,
                granted_by=str(current_team_member.id),
                db=db,
            )
            if success:
                results["granted"].append(perm_code)
                await log_permission_change(
                    team_member_id=member_id,
                    merchant_id=str(current_team_member.merchant_id),
                    action="team.permission_granted",
                    details={
                        "permission": perm_code,
                        "granted_by": str(current_team_member.id),
                        "granted_by_email": current_team_member.email,
                    },
                    db=db,
                )
            else:
                results["errors"].append(f"Permission not found: {perm_code}")
    
    # Process revokes
    if perm_data.revoke:
        for perm_code in perm_data.revoke:
            success = await revoke_permission(
                team_member_id=member_id,
                permission_code=perm_code,
                revoked_by=str(current_team_member.id),
                db=db,
            )
            if success:
                results["revoked"].append(perm_code)
                await log_permission_change(
                    team_member_id=member_id,
                    merchant_id=str(current_team_member.merchant_id),
                    action="team.permission_revoked",
                    details={
                        "permission": perm_code,
                        "revoked_by": str(current_team_member.id),
                        "revoked_by_email": current_team_member.email,
                    },
                    db=db,
                )
            else:
                results["errors"].append(f"Permission not found: {perm_code}")
    
    # Get updated effective permissions
    effective = await get_effective_permissions(member_id, db)
    
    return {
        "message": "Permissions updated",
        "results": results,
        "effective_permissions": effective,
    }
