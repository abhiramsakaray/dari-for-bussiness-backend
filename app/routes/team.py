"""
Team Management API Routes
Multi-user access for merchant accounts with RBAC support
"""
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, Request
from sqlalchemy.orm import Session
from sqlalchemy import and_
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Optional
import logging

from app.core.database import get_db
from app.core.security import hash_password, verify_password
from app.core import require_merchant
from app.core.team_middleware import get_current_team_member
from app.core.permissions import get_effective_permissions, has_permission
from app.core.sessions import revoke_all_sessions, get_active_sessions
from app.core.activity_logger import log_activity, log_password_reset, log_session_revoked
from app.core.team_auth import (
    hash_password as team_hash_password,
    validate_password_strength,
    generate_secure_password,
)
from app.models.models import Merchant, MerchantUser, MerchantRole as DBMerchantRole
from app.schemas.schemas import (
    TeamMemberInvite, TeamMemberUpdate, TeamMemberResponse, TeamList, MerchantRole,
    CreateTeamMemberRequest, CreateTeamMemberResponse, ResetMemberPasswordRequest,
    TeamMemberSessionResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/team", tags=["Team"])
router_v1 = APIRouter(prefix="/api/v1/team", tags=["Team API v1"])  # For /api/v1 prefixed calls


def generate_invite_token() -> str:
    """Generate a secure invite token"""
    return secrets.token_urlsafe(32)


# Role permissions mapping
ROLE_PERMISSIONS = {
    DBMerchantRole.OWNER: [
        "all:read", "all:write", "team:manage", "settings:manage", "billing:manage"
    ],
    DBMerchantRole.ADMIN: [
        "all:read", "all:write", "team:manage", "settings:read"
    ],
    DBMerchantRole.DEVELOPER: [
        "payments:read", "payments:write", "webhooks:manage", "api_keys:manage",
        "analytics:read"
    ],
    DBMerchantRole.FINANCE: [
        "payments:read", "invoices:read", "invoices:write", "analytics:read",
        "refunds:read", "refunds:write", "subscriptions:read"
    ],
    DBMerchantRole.VIEWER: [
        "payments:read", "invoices:read", "analytics:read"
    ]
}


def check_team_permission(user: MerchantUser, permission: str) -> bool:
    """Check if user has a specific permission"""
    role_perms = ROLE_PERMISSIONS.get(user.role, [])
    
    # Check for wildcard
    if "all:read" in role_perms and permission.endswith(":read"):
        return True
    if "all:write" in role_perms and permission.endswith(":write"):
        return True
    
    return permission in role_perms


@router.post("/invite", response_model=TeamMemberResponse)
@router_v1.post("/invite", response_model=TeamMemberResponse)
async def invite_team_member(
    invite_data: TeamMemberInvite,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant)
):
    """
    Invite a new team member.
    
    Sends an invitation email with a link to set up their account.
    Roles:
    - owner: Full access to everything
    - admin: Full access except billing
    - developer: API, webhooks, payments
    - finance: Invoices, refunds, analytics
    - viewer: Read-only access
    """
    # Check for existing member
    existing = db.query(MerchantUser).filter(
        and_(
            MerchantUser.merchant_id == uuid.UUID(current_user["id"]),
            MerchantUser.email == invite_data.email.lower()
        )
    ).first()
    
    if existing:
        if existing.is_active:
            raise HTTPException(
                status_code=400,
                detail="User is already a team member"
            )
        else:
            # Reactivate and resend invite
            existing.is_active = True
            existing.role = DBMerchantRole(invite_data.role.value)
            existing.invite_token = generate_invite_token()
            existing.invite_expires = datetime.utcnow() + timedelta(days=7)
            db.commit()
            db.refresh(existing)
            
            # TODO: Send invite email
            return build_member_response(existing)
    
    # Cannot invite owner role
    if invite_data.role == MerchantRole.OWNER:
        raise HTTPException(
            status_code=400,
            detail="Cannot invite users with owner role"
        )
    
    # Create invite
    invite_token = generate_invite_token()
    
    member = MerchantUser(
        merchant_id=uuid.UUID(current_user["id"]),
        email=invite_data.email.lower(),
        name=invite_data.name,
        role=DBMerchantRole(invite_data.role.value),
        invite_token=invite_token,
        invite_expires=datetime.utcnow() + timedelta(days=7)
    )
    
    db.add(member)
    db.commit()
    db.refresh(member)
    
    # TODO: Send invite email
    # background_tasks.add_task(send_team_invite_email, member, invite_token)
    
    return build_member_response(member)


@router.get("", response_model=TeamList)
@router_v1.get("", response_model=TeamList)
async def list_team_members(
    db: Session = Depends(get_db)
):
    """List all active team members for the merchant."""
    # Only show active members (exclude soft-deleted ones)
    query = db.query(MerchantUser).filter(MerchantUser.is_active == True)
    
    members = query.order_by(MerchantUser.created_at).all()
    
    return TeamList(
        members=[build_member_response(m) for m in members],
        total=len(members)
    )


@router.get("/{member_id}", response_model=TeamMemberResponse)
@router_v1.get("/{member_id}", response_model=TeamMemberResponse)
async def get_team_member(
    member_id: str,
    db: Session = Depends(get_db)
):
    """Get a specific team member."""
    # TEMP: Show all data (no auth)
    member = db.query(MerchantUser).filter(MerchantUser.id == member_id).first()
    
    if not member:
        raise HTTPException(status_code=404, detail="Team member not found")
    
    return build_member_response(member)


@router.patch("/{member_id}", response_model=TeamMemberResponse)
@router_v1.patch("/{member_id}", response_model=TeamMemberResponse)
async def update_team_member(
    member_id: str,
    update_data: TeamMemberUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant)
):
    """
    Update a team member's role or status.
    
    Cannot change owner role.
    """
    member = db.query(MerchantUser).filter(
        and_(
            MerchantUser.id == member_id,
            MerchantUser.merchant_id == uuid.UUID(current_user["id"])
        )
    ).first()
    
    if not member:
        raise HTTPException(status_code=404, detail="Team member not found")
    
    # Cannot modify owner
    if member.role == DBMerchantRole.OWNER:
        raise HTTPException(
            status_code=400,
            detail="Cannot modify the account owner"
        )
    
    # Cannot change to owner
    if update_data.role == MerchantRole.OWNER:
        raise HTTPException(
            status_code=400,
            detail="Cannot change role to owner"
        )
    
    if update_data.role is not None:
        member.role = DBMerchantRole(update_data.role.value)
    
    if update_data.is_active is not None:
        member.is_active = update_data.is_active
    
    member.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(member)
    
    return build_member_response(member)


@router.delete("/{member_id}")
@router_v1.delete("/{member_id}")
async def remove_team_member(
    member_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant)
):
    """
    Remove a team member.
    
    Cannot remove the account owner.
    """
    member = db.query(MerchantUser).filter(
        and_(
            MerchantUser.id == member_id,
            MerchantUser.merchant_id == uuid.UUID(current_user["id"])
        )
    ).first()
    
    if not member:
        raise HTTPException(status_code=404, detail="Team member not found")
    
    if member.role == DBMerchantRole.OWNER:
        raise HTTPException(
            status_code=400,
            detail="Cannot remove the account owner"
        )
    
    # Soft delete - deactivate instead of delete
    member.is_active = False
    member.updated_at = datetime.utcnow()
    db.commit()
    
    return {"message": "Team member removed", "id": member_id}


# ========================
# RBAC-ENHANCED ENDPOINTS
# ========================

@router.post("/members", response_model=CreateTeamMemberResponse)
@router_v1.post("/members", response_model=CreateTeamMemberResponse)
async def create_team_member(
    member_data: CreateTeamMemberRequest,
    current_user: dict = Depends(require_merchant),
    db: Session = Depends(get_db),
):
    """
    Create a team member with password (RBAC-protected).
    
    Requires team.create permission or merchant owner access.
    Can auto-generate a secure password or accept a custom one.
    """
    # Get or create owner team member for the merchant
    merchant_id = current_user["id"]
    owner_member = db.query(MerchantUser).filter(
        and_(
            MerchantUser.merchant_id == merchant_id,
            MerchantUser.role == DBMerchantRole.OWNER
        )
    ).first()
    
    # If no owner exists, merchant has full access (backward compatibility)
    if owner_member:
        # Check permission for existing team structure
        permissions = await get_effective_permissions(str(owner_member.id), db)
        if not has_permission(permissions, "team.create"):
            raise HTTPException(status_code=403, detail="Permission denied: team.create required")
        current_team_member = owner_member
    else:
        # Merchant owner has implicit permission
        current_team_member = None
    
    # Check for existing member
    existing = db.query(MerchantUser).filter(
        and_(
            MerchantUser.merchant_id == merchant_id,
            MerchantUser.email == member_data.email.lower()
        )
    ).first()
    
    if existing and existing.is_active:
        raise HTTPException(status_code=400, detail="User is already a team member")
    
    # Cannot create owner role
    if member_data.role == MerchantRole.OWNER:
        raise HTTPException(status_code=400, detail="Cannot create users with owner role")
    
    # Handle password
    temporary_password = None
    password_hash = None
    
    if member_data.auto_generate_password:
        temporary_password = generate_secure_password()
        password_hash = team_hash_password(temporary_password)
    elif member_data.password:
        is_valid, error_msg = validate_password_strength(member_data.password)
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)
        password_hash = team_hash_password(member_data.password)
    else:
        # No password provided - will create invitation flow
        raise HTTPException(
            status_code=400,
            detail="Must provide either 'password' or set 'auto_generate_password=true'. Use POST /team/invite for invitation flow."
        )
    
    if existing and not existing.is_active:
        # Reactivate deactivated member
        existing.is_active = True
        existing.role = DBMerchantRole(member_data.role.value)
        existing.name = member_data.name
        if password_hash:
            existing.password_hash = password_hash
        existing.created_by = current_team_member.id if current_team_member else None
        existing.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        
        # Return appropriate message
        if password_hash:
            message = "Account reactivated successfully! User can login immediately."
        else:
            message = "Account reactivated. Invitation sent to set password."
        
        return CreateTeamMemberResponse(
            id=str(existing.id),
            email=existing.email,
            name=existing.name,
            role=existing.role.value,
            temporary_password=temporary_password,
            message=message,
        )
    
    # Create new member
    # Only generate invite token if NO password was provided
    invite_token = None if password_hash else generate_invite_token()
    
    member = MerchantUser(
        merchant_id=merchant_id,
        email=member_data.email.lower(),
        name=member_data.name,
        role=DBMerchantRole(member_data.role.value),
        password_hash=password_hash,
        invite_token=invite_token,
        invite_expires=datetime.utcnow() + timedelta(days=7) if invite_token else None,
        created_by=current_team_member.id if current_team_member else None,
    )
    
    db.add(member)
    db.commit()
    db.refresh(member)
    
    # Log activity
    creator_email = current_team_member.email if current_team_member else current_user.get("email", "merchant_owner")
    await log_activity(
        merchant_id=str(merchant_id),
        team_member_id=str(current_team_member.id) if current_team_member else None,
        action="team.member_created",
        resource_type="team_member",
        resource_id=str(member.id),
        details={
            "email": member.email,
            "role": member.role.value,
            "created_by": creator_email,
            "has_password": password_hash is not None,
        },
        db=db,
    )
    
    logger.info(f"Team member created: {member.email} by {creator_email} (password_set={password_hash is not None})")
    
    # Return appropriate message based on whether password was set
    if password_hash:
        message = "Account created successfully! User can login immediately."
    else:
        message = "Invitation sent. User must accept invitation to set password."
    
    return CreateTeamMemberResponse(
        id=str(member.id),
        email=member.email,
        name=member.name,
        role=member.role.value,
        invite_token=invite_token,
        temporary_password=temporary_password,
        message=message,
    )


@router.post("/members/{member_id}/reset-password")
@router_v1.post("/members/{member_id}/reset-password")
async def reset_member_password(
    member_id: str,
    reset_data: ResetMemberPasswordRequest,
    request: Request,
    current_team_member: MerchantUser = Depends(get_current_team_member),
    db: Session = Depends(get_db),
):
    """
    Admin reset a team member's password.
    
    Requires team.update permission.
    Cannot reset owner's password unless you are the owner.
    """
    # Check permission
    permissions = await get_effective_permissions(str(current_team_member.id), db)
    if not has_permission(permissions, "team.update"):
        raise HTTPException(status_code=403, detail="Permission denied: team.update required")
    
    # Find target member
    target_member = db.query(MerchantUser).filter(
        and_(
            MerchantUser.id == member_id,
            MerchantUser.merchant_id == current_team_member.merchant_id,
        )
    ).first()
    
    if not target_member:
        raise HTTPException(status_code=404, detail="Team member not found")
    
    # Cannot reset owner's password unless you are the owner
    if target_member.role == DBMerchantRole.OWNER and \
       current_team_member.role != DBMerchantRole.OWNER:
        raise HTTPException(
            status_code=400,
            detail="Only the owner can reset the owner's password"
        )
    
    # Handle password
    temporary_password = None
    if reset_data.auto_generate_password:
        temporary_password = generate_secure_password()
        target_member.password_hash = team_hash_password(temporary_password)
    elif reset_data.new_password:
        is_valid, error_msg = validate_password_strength(reset_data.new_password)
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)
        target_member.password_hash = team_hash_password(reset_data.new_password)
    else:
        raise HTTPException(
            status_code=400,
            detail="Must provide new_password or set auto_generate_password=true"
        )
    
    # Reset security fields
    target_member.failed_login_attempts = 0
    target_member.locked_until = None
    db.commit()
    
    # Revoke all existing sessions
    await revoke_all_sessions(member_id, db)
    
    # Log the password reset
    await log_password_reset(
        team_member_id=member_id,
        merchant_id=str(current_team_member.merchant_id),
        reset_by=str(current_team_member.id),
        request=request,
        db=db,
    )
    
    result = {
        "message": "Password has been reset",
        "member_id": member_id,
        "sessions_revoked": True,
    }
    if temporary_password:
        result["temporary_password"] = temporary_password
    
    return result


@router.post("/members/{member_id}/revoke-sessions")
@router_v1.post("/members/{member_id}/revoke-sessions")
async def revoke_member_sessions(
    member_id: str,
    current_team_member: MerchantUser = Depends(get_current_team_member),
    db: Session = Depends(get_db),
):
    """
    Revoke all active sessions for a team member.
    
    Requires team.update permission (or revoking own sessions).
    """
    # Allow self-service or require team.update
    if str(current_team_member.id) != member_id:
        permissions = await get_effective_permissions(str(current_team_member.id), db)
        if not has_permission(permissions, "team.update"):
            raise HTTPException(status_code=403, detail="Permission denied: team.update required")
    
    # Verify target is in same merchant
    target_member = db.query(MerchantUser).filter(
        and_(
            MerchantUser.id == member_id,
            MerchantUser.merchant_id == current_team_member.merchant_id,
        )
    ).first()
    
    if not target_member:
        raise HTTPException(status_code=404, detail="Team member not found")
    
    count = await revoke_all_sessions(member_id, db)
    
    # Log session revocation
    await log_session_revoked(
        team_member_id=member_id,
        merchant_id=str(current_team_member.merchant_id),
        revoked_by=str(current_team_member.id),
        sessions_count=count,
        db=db,
    )
    
    return {
        "message": f"Revoked {count} session(s)",
        "sessions_revoked": count,
    }


@router.get("/members/{member_id}/sessions", response_model=list[TeamMemberSessionResponse])
@router_v1.get("/members/{member_id}/sessions", response_model=list[TeamMemberSessionResponse])
async def list_member_sessions(
    member_id: str,
    current_team_member: MerchantUser = Depends(get_current_team_member),
    db: Session = Depends(get_db),
):
    """
    Get all active sessions for a team member.
    
    Can view own sessions or requires team.view permission.
    """
    # Allow self-service or require team.view
    if str(current_team_member.id) != member_id:
        permissions = await get_effective_permissions(str(current_team_member.id), db)
        if not has_permission(permissions, "team.view"):
            raise HTTPException(status_code=403, detail="Permission denied: team.view required")
    
    # Verify target is in same merchant
    target_member = db.query(MerchantUser).filter(
        and_(
            MerchantUser.id == member_id,
            MerchantUser.merchant_id == current_team_member.merchant_id,
        )
    ).first()
    
    if not target_member:
        raise HTTPException(status_code=404, detail="Team member not found")
    
    sessions = await get_active_sessions(member_id, db)
    
    return [
        TeamMemberSessionResponse(
            id=str(s.id),
            ip_address=s.ip_address,
            user_agent=s.user_agent,
            last_activity=s.last_activity,
            expires_at=s.expires_at,
            is_current=False,  # We can't easily determine this from the session alone
            created_at=s.created_at,
        )
        for s in sessions
    ]


@router.post("/{member_id}/resend-invite")
@router_v1.post("/{member_id}/resend-invite")
async def resend_invite(
    member_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_merchant)
):
    """
    Resend invitation to a pending team member.
    """
    member = db.query(MerchantUser).filter(
        and_(
            MerchantUser.id == member_id,
            MerchantUser.merchant_id == uuid.UUID(current_user["id"])
        )
    ).first()
    
    if not member:
        raise HTTPException(status_code=404, detail="Team member not found")
    
    if member.password_hash:
        raise HTTPException(
            status_code=400,
            detail="User has already accepted the invitation"
        )
    
    # Generate new token
    member.invite_token = generate_invite_token()
    member.invite_expires = datetime.utcnow() + timedelta(days=7)
    db.commit()
    
    # TODO: Send invite email
    # background_tasks.add_task(send_team_invite_email, member)
    
    return {
        "message": "Invitation resent",
        "email": member.email
    }


@router.get("/roles/permissions")
@router_v1.get("/roles/permissions")
async def list_role_permissions():
    """
    List available roles and their permissions.
    """
    return {
        "roles": [
            {
                "role": role.value,
                "permissions": perms,
                "description": get_role_description(role)
            }
            for role, perms in ROLE_PERMISSIONS.items()
        ]
    }


# ========================
# PUBLIC ENDPOINTS (No auth)
# ========================

@router.post("/accept-invite")
@router_v1.post("/accept-invite")
async def accept_invite(
    token: str,
    password: str,
    name: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Accept a team invitation and set up account.
    
    This endpoint is public (no auth required).
    """
    member = db.query(MerchantUser).filter(
        MerchantUser.invite_token == token
    ).first()
    
    if not member:
        raise HTTPException(status_code=404, detail="Invalid invitation token")
    
    if member.invite_expires and member.invite_expires < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Invitation has expired")
    
    if member.password_hash:
        raise HTTPException(
            status_code=400,
            detail="Invitation has already been accepted"
        )
    
    # Set password and clear invite
    member.password_hash = hash_password(password)
    member.invite_token = None
    member.invite_expires = None
    if name:
        member.name = name
    member.updated_at = datetime.utcnow()
    
    db.commit()
    
    return {
        "message": "Account created successfully",
        "email": member.email
    }


# ========================
# HELPERS
# ========================

def build_member_response(member: MerchantUser) -> TeamMemberResponse:
    """Build TeamMemberResponse from model"""
    return TeamMemberResponse(
        id=str(member.id),
        email=member.email,
        name=member.name,
        role=member.role.value if hasattr(member.role, 'value') else member.role,
        is_active=member.is_active,
        invite_pending=member.password_hash is None,
        last_login=member.last_login,
        created_at=member.created_at
    )


def get_role_description(role: DBMerchantRole) -> str:
    """Get human-readable description for a role"""
    descriptions = {
        DBMerchantRole.OWNER: "Full access to all features including billing and account settings",
        DBMerchantRole.ADMIN: "Full access to all features except billing management",
        DBMerchantRole.DEVELOPER: "Access to API keys, webhooks, and payment integration",
        DBMerchantRole.FINANCE: "Access to invoices, refunds, analytics, and financial reports",
        DBMerchantRole.VIEWER: "Read-only access to payments and basic analytics"
    }
    return descriptions.get(role, "")
