"""
Example usage of team_middleware.py in API routes

This file demonstrates how to use the permission middleware
in FastAPI routes for the Team RBAC system.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.team_middleware import get_current_team_member, require_permissions
from app.models.models import MerchantUser

router = APIRouter(prefix="/api/v1", tags=["Example"])


# Example 1: Simple endpoint with single permission
@router.get("/payments")
@require_permissions("payments.view")
async def list_payments(
    current_team_member: MerchantUser = Depends(get_current_team_member),
    db: Session = Depends(get_db)
):
    """
    List payments - requires 'payments.view' permission
    """
    return {
        "message": "Listing payments",
        "team_member": current_team_member.email,
        "role": current_team_member.role.value
    }


# Example 2: Endpoint with multiple permissions (requires ALL)
@router.post("/payments/refund")
@require_permissions("payments.view", "payments.refund")
async def refund_payment(
    payment_id: str,
    current_team_member: MerchantUser = Depends(get_current_team_member),
    db: Session = Depends(get_db)
):
    """
    Refund a payment - requires both 'payments.view' AND 'payments.refund'
    """
    return {
        "message": f"Refunding payment {payment_id}",
        "refunded_by": current_team_member.email
    }


# Example 3: Team management endpoint
@router.post("/team/members")
@require_permissions("team.create")
async def create_team_member(
    email: str,
    role: str,
    current_team_member: MerchantUser = Depends(get_current_team_member),
    db: Session = Depends(get_db)
):
    """
    Create team member - requires 'team.create' permission
    """
    return {
        "message": f"Creating team member {email}",
        "created_by": current_team_member.email
    }


# Example 4: Endpoint without permission check (authenticated only)
@router.get("/profile")
async def get_profile(
    current_team_member: MerchantUser = Depends(get_current_team_member),
    db: Session = Depends(get_db)
):
    """
    Get current user profile - no specific permission required,
    just authentication via get_current_team_member
    """
    return {
        "id": str(current_team_member.id),
        "email": current_team_member.email,
        "name": current_team_member.name,
        "role": current_team_member.role.value,
        "merchant_id": str(current_team_member.merchant_id)
    }


# Example 5: Admin-only endpoint
@router.delete("/team/members/{member_id}")
@require_permissions("team.delete")
async def delete_team_member(
    member_id: str,
    current_team_member: MerchantUser = Depends(get_current_team_member),
    db: Session = Depends(get_db)
):
    """
    Delete team member - requires 'team.delete' permission
    (typically only OWNER and ADMIN roles have this)
    """
    return {
        "message": f"Deleting team member {member_id}",
        "deleted_by": current_team_member.email
    }


"""
PERMISSION BEHAVIOR:

1. Wildcard Permissions:
   - "*" grants ALL permissions (OWNER role has this)
   - "payments.*" grants all payment permissions (view, create, refund, export)
   - "team.*" grants all team permissions (view, create, update, delete, view_logs)

2. Permission Resolution:
   - Role permissions are loaded from role_permissions table
   - Custom granted permissions are added
   - Custom revoked permissions are removed
   - Formula: (role_permissions ∪ custom_granted) - custom_revoked

3. Error Responses:
   - 401 Unauthorized: Missing/invalid token, expired session, inactive account
   - 403 Forbidden: Valid authentication but insufficient permissions
   
4. Activity Logging:
   - All permission denials are logged to activity_logs table
   - Includes: team_member_id, action="permission_denied", endpoint, required permission

EXAMPLE PERMISSION MAPPINGS:

OWNER:
  - Has "*" (all permissions)
  
ADMIN:
  - payments.*, invoices.*, payment_links.*, subscriptions.*
  - withdrawals.view, withdrawals.create
  - coupons.*, team.*, analytics.*
  - settings.view, settings.update
  - api_keys.view, webhooks.view, wallets.view

DEVELOPER:
  - payments.view, invoices.view, payment_links.view, subscriptions.view
  - api_keys.*, webhooks.*, analytics.view, settings.view

FINANCE:
  - payments.*, invoices.*, withdrawals.*
  - payment_links.view, subscriptions.view
  - coupons.view, analytics.*, settings.view

VIEWER:
  - payments.view, invoices.view, payment_links.view
  - subscriptions.view, withdrawals.view, coupons.view
  - analytics.view, settings.view
"""

