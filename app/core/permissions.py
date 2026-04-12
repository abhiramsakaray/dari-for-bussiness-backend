"""
Permission Service
Handles permission resolution and enforcement for team members
"""
from typing import List, Dict
from sqlalchemy.orm import Session
from sqlalchemy import and_
import uuid

from app.models.models import (
    MerchantUser, Permission, RolePermission, TeamMemberPermission, MerchantRole
)

# Permission definitions (matches database seed)
PERMISSIONS = {
    # Payments
    'payments.view': 'View payment transactions',
    'payments.create': 'Create payment sessions',
    'payments.refund': 'Process refunds',
    'payments.export': 'Export payment data',
    
    # Invoices
    'invoices.view': 'View invoices',
    'invoices.create': 'Create invoices',
    'invoices.update': 'Update invoices',
    'invoices.delete': 'Delete invoices',
    'invoices.send': 'Send invoices to customers',
    
    # Payment Links
    'payment_links.view': 'View payment links',
    'payment_links.create': 'Create payment links',
    'payment_links.update': 'Update payment links',
    'payment_links.delete': 'Delete payment links',
    
    # Subscriptions
    'subscriptions.view': 'View subscriptions',
    'subscriptions.create': 'Create subscription plans',
    'subscriptions.update': 'Update subscriptions',
    'subscriptions.cancel': 'Cancel subscriptions',
    
    # Withdrawals
    'withdrawals.view': 'View withdrawals',
    'withdrawals.create': 'Create withdrawal requests',
    'withdrawals.approve': 'Approve withdrawals',
    
    # Coupons
    'coupons.view': 'View coupons',
    'coupons.create': 'Create coupons',
    'coupons.update': 'Update coupons',
    'coupons.delete': 'Delete coupons',
    
    # Team Management
    'team.view': 'View team members',
    'team.create': 'Add team members',
    'team.update': 'Update team members',
    'team.delete': 'Remove team members',
    'team.view_logs': 'View activity logs',
    
    # API & Integrations
    'api_keys.view': 'View API keys',
    'api_keys.manage': 'Create/delete API keys',
    'webhooks.view': 'View webhooks',
    'webhooks.manage': 'Manage webhooks',
    
    # Analytics
    'analytics.view': 'View analytics dashboard',
    'analytics.export': 'Export analytics data',
    
    # Settings
    'settings.view': 'View settings',
    'settings.update': 'Update settings',
    'settings.billing': 'Manage billing and plans',
    
    # Wallets
    'wallets.view': 'View wallet addresses',
    'wallets.manage': 'Add/remove wallets',
}

# Role permission mappings (matches database seed)
ROLE_PERMISSIONS = {
    'owner': ['*'],  # All permissions
    
    'admin': [
        'payments.*',
        'invoices.*',
        'payment_links.*',
        'subscriptions.*',
        'withdrawals.view',
        'withdrawals.create',
        'coupons.*',
        'team.*',
        'api_keys.view',
        'webhooks.view',
        'analytics.*',
        'settings.view',
        'settings.update',
        'wallets.view',
    ],
    
    'developer': [
        'payments.view',
        'invoices.view',
        'payment_links.view',
        'subscriptions.view',
        'api_keys.*',
        'webhooks.*',
        'analytics.view',
        'settings.view',
    ],
    
    'finance': [
        'payments.*',
        'invoices.*',
        'payment_links.view',
        'subscriptions.view',
        'withdrawals.*',
        'coupons.view',
        'analytics.*',
        'settings.view',
    ],
    
    'viewer': [
        'payments.view',
        'invoices.view',
        'payment_links.view',
        'subscriptions.view',
        'withdrawals.view',
        'coupons.view',
        'analytics.view',
        'settings.view',
    ],
}


async def get_role_permissions(role: str, db: Session) -> List[str]:
    """
    Get permissions for a specific role from database
    
    Args:
        role: Role name (owner, admin, developer, finance, viewer)
        db: Database session
        
    Returns:
        List of permission codes
    """
    # Owner has all permissions
    if role == MerchantRole.OWNER.value or role == "owner":
        return ["*"]
    
    # Query role permissions from database
    role_perms = db.query(Permission.code).join(
        RolePermission, RolePermission.permission_id == Permission.id
    ).filter(
        RolePermission.role == role
    ).all()
    
    return [perm[0] for perm in role_perms]


async def get_custom_permissions(team_member_id: str, db: Session) -> Dict[str, List[str]]:
    """
    Get custom permission grants and revokes for a team member
    
    Args:
        team_member_id: Team member UUID
        db: Database session
        
    Returns:
        Dict with 'granted' and 'revoked' lists of permission codes
    """
    custom_perms = db.query(
        Permission.code, TeamMemberPermission.granted
    ).join(
        TeamMemberPermission, TeamMemberPermission.permission_id == Permission.id
    ).filter(
        TeamMemberPermission.team_member_id == uuid.UUID(team_member_id)
    ).all()
    
    granted = [code for code, is_granted in custom_perms if is_granted]
    revoked = [code for code, is_granted in custom_perms if not is_granted]
    
    return {
        "granted": granted,
        "revoked": revoked
    }


async def get_effective_permissions(team_member_id: str, db: Session) -> List[str]:
    """
    Calculate effective permissions for a team member
    
    Formula: (role_permissions ∪ custom_granted) - custom_revoked
    
    Args:
        team_member_id: Team member UUID
        db: Database session
        
    Returns:
        List of effective permission codes
    """
    # Get team member
    team_member = db.query(MerchantUser).filter(
        MerchantUser.id == uuid.UUID(team_member_id)
    ).first()
    
    if not team_member:
        return []
    
    # Get role permissions
    role_perms = await get_role_permissions(team_member.role.value, db)
    
    # Owner has all permissions
    if "*" in role_perms:
        return ["*"]
    
    # Get custom permissions
    custom = await get_custom_permissions(team_member_id, db)
    
    # Calculate effective permissions
    effective = (set(role_perms) | set(custom["granted"])) - set(custom["revoked"])
    
    return list(effective)


def has_permission(permissions: List[str], required: str) -> bool:
    """
    Check if user has a specific permission (supports wildcards)
    
    Wildcard rules:
    - "*" grants all permissions
    - "category.*" grants all permissions in that category
    
    Args:
        permissions: List of user's permissions
        required: Required permission code
        
    Returns:
        True if user has permission, False otherwise
    """
    # Check for super admin
    if "*" in permissions:
        return True
    
    # Check for exact match
    if required in permissions:
        return True
    
    # Check for category wildcard (e.g., "payments.*")
    category = required.split('.')[0]
    if f"{category}.*" in permissions:
        return True
    
    return False


async def grant_permission(
    team_member_id: str,
    permission_code: str,
    granted_by: str,
    db: Session
) -> bool:
    """
    Grant a custom permission to a team member
    
    Args:
        team_member_id: Team member UUID
        permission_code: Permission code to grant
        granted_by: UUID of team member granting permission
        db: Database session
        
    Returns:
        True if successful, False otherwise
    """
    # Get permission ID
    permission = db.query(Permission).filter(
        Permission.code == permission_code
    ).first()
    
    if not permission:
        return False
    
    # Check if custom permission already exists
    existing = db.query(TeamMemberPermission).filter(
        and_(
            TeamMemberPermission.team_member_id == uuid.UUID(team_member_id),
            TeamMemberPermission.permission_id == permission.id
        )
    ).first()
    
    if existing:
        # Update to granted
        existing.granted = True
        existing.created_by = uuid.UUID(granted_by) if granted_by else None
    else:
        # Create new grant
        custom_perm = TeamMemberPermission(
            team_member_id=uuid.UUID(team_member_id),
            permission_id=permission.id,
            granted=True,
            created_by=uuid.UUID(granted_by) if granted_by else None
        )
        db.add(custom_perm)
    
    db.commit()
    return True


async def revoke_permission(
    team_member_id: str,
    permission_code: str,
    revoked_by: str,
    db: Session
) -> bool:
    """
    Revoke a permission from a team member
    
    Args:
        team_member_id: Team member UUID
        permission_code: Permission code to revoke
        revoked_by: UUID of team member revoking permission
        db: Database session
        
    Returns:
        True if successful, False otherwise
    """
    # Get permission ID
    permission = db.query(Permission).filter(
        Permission.code == permission_code
    ).first()
    
    if not permission:
        return False
    
    # Check if custom permission already exists
    existing = db.query(TeamMemberPermission).filter(
        and_(
            TeamMemberPermission.team_member_id == uuid.UUID(team_member_id),
            TeamMemberPermission.permission_id == permission.id
        )
    ).first()
    
    if existing:
        # Update to revoked
        existing.granted = False
        existing.created_by = uuid.UUID(revoked_by) if revoked_by else None
    else:
        # Create new revocation
        custom_perm = TeamMemberPermission(
            team_member_id=uuid.UUID(team_member_id),
            permission_id=permission.id,
            granted=False,
            created_by=uuid.UUID(revoked_by) if revoked_by else None
        )
        db.add(custom_perm)
    
    db.commit()
    return True


async def get_all_permissions(db: Session) -> List[Dict]:
    """
    Get all available permissions
    
    Args:
        db: Database session
        
    Returns:
        List of permission dictionaries
    """
    permissions = db.query(Permission).order_by(Permission.category, Permission.code).all()
    
    return [
        {
            "code": perm.code,
            "name": perm.name,
            "description": perm.description,
            "category": perm.category
        }
        for perm in permissions
    ]
