"""
Team Management API Routes
Multi-user access for merchant accounts
"""
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import and_
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Optional

from app.core.database import get_db
from app.core.security import hash_password, verify_password
from app.core import require_merchant
from app.models.models import Merchant, MerchantUser, MerchantRole as DBMerchantRole
from app.schemas.schemas import (
    TeamMemberInvite, TeamMemberUpdate, TeamMemberResponse, TeamList, MerchantRole
)

router = APIRouter(prefix="/team", tags=["Team"])


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
async def list_team_members(
    db: Session = Depends(get_db)
):
    """List all team members for the merchant."""
    # TEMP: Show all data (no auth)
    query = db.query(MerchantUser)
    
    members = query.order_by(MerchantUser.created_at).all()
    
    return TeamList(
        members=[build_member_response(m) for m in members],
        total=len(members)
    )


@router.get("/{member_id}", response_model=TeamMemberResponse)
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


@router.post("/{member_id}/resend-invite")
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
