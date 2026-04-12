"""
Team Authentication API Routes
Handles team member login, logout, token refresh, and password management
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import and_
from datetime import datetime, timedelta
import uuid

from app.core.database import get_db
from app.core.team_auth import (
    create_access_token,
    create_refresh_token,
    verify_token,
    verify_password,
    hash_password,
    validate_password_strength,
    check_account_lockout,
    increment_failed_attempts,
    reset_failed_attempts,
    generate_password_reset_token,
)
from app.core.sessions import create_session, revoke_session, validate_session, revoke_all_sessions
from app.core.activity_logger import log_login, log_logout, log_failed_login, log_password_reset
from app.core.team_middleware import get_current_team_member
from app.models.models import MerchantUser, MerchantRole
from app.schemas.schemas import (
    TeamLoginRequest,
    TeamLoginResponse,
    RefreshTokenRequest,
    RefreshTokenResponse,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    ChangePasswordRequest,
)

import jwt as pyjwt
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/team", tags=["Team Authentication"])
router_v1 = APIRouter(prefix="/api/v1/auth/team", tags=["Team Authentication API v1"])  # For /api/v1 prefixed calls


@router.post("/login", response_model=TeamLoginResponse)
@router_v1.post("/login", response_model=TeamLoginResponse)
async def team_login(
    login_data: TeamLoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Authenticate a team member with email and password.
    
    Returns access token (1 hour) and refresh token (7 days).
    Tracks sessions and logs activity.
    """
    # Find team member by email (case-insensitive)
    team_member = db.query(MerchantUser).filter(
        MerchantUser.email == login_data.email.lower()
    ).first()
    
    if not team_member:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )
    
    # Check if account is active
    if not team_member.is_active:
        raise HTTPException(
            status_code=401,
            detail="Account is inactive. Contact your administrator."
        )
    
    # Check account lockout
    is_locked, locked_until = check_account_lockout(team_member)
    if is_locked:
        raise HTTPException(
            status_code=423,
            detail={
                "message": "Account is temporarily locked due to too many failed login attempts",
                "locked_until": locked_until.isoformat() if locked_until else None
            }
        )
    
    # Check if password is set (invite not yet accepted)
    if not team_member.password_hash:
        raise HTTPException(
            status_code=401,
            detail="Account setup incomplete. Please accept your invitation first."
        )
    
    # Verify password
    if not verify_password(login_data.password, team_member.password_hash):
        # Increment failed attempts
        increment_failed_attempts(team_member, db)
        
        # Log failed login
        await log_failed_login(
            login_data.email,
            str(team_member.merchant_id),
            request,
            db
        )
        
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )
    
    # Successful login — reset failed attempts
    reset_failed_attempts(team_member, db)
    
    # Create tokens
    access_token = create_access_token(
        team_member_id=str(team_member.id),
        merchant_id=str(team_member.merchant_id),
        role=team_member.role.value,
    )
    refresh_token = create_refresh_token(
        team_member_id=str(team_member.id)
    )
    
    # Create session
    session_id = await create_session(
        team_member_id=str(team_member.id),
        token=access_token,
        request=request,
        db=db,
    )
    
    # Log login
    await log_login(team_member, request, db)
    
    logger.info(f"Team member logged in: {team_member.email} (session={session_id})")
    
    return TeamLoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=3600,
        team_member={
            "id": str(team_member.id),
            "email": team_member.email,
            "name": team_member.name,
            "role": team_member.role.value,
            "merchant_id": str(team_member.merchant_id),
        },
    )


@router.post("/logout")
@router_v1.post("/logout")
async def team_logout(
    request: Request,
    current_team_member: MerchantUser = Depends(get_current_team_member),
    db: Session = Depends(get_db),
):
    """
    Logout the current team member. Revokes the current session.
    """
    # Extract token from header to find session
    authorization = request.headers.get("authorization", "")
    if authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        session = await validate_session(token, db)
        if session:
            await revoke_session(str(session.id), db)
    
    # Log logout
    await log_logout(current_team_member, request, db)
    
    return {"message": "Logged out successfully"}


@router.post("/refresh", response_model=RefreshTokenResponse)
@router_v1.post("/refresh", response_model=RefreshTokenResponse)
async def refresh_access_token(
    refresh_data: RefreshTokenRequest,
    db: Session = Depends(get_db),
):
    """
    Exchange a refresh token for a new access token.
    """
    try:
        payload = verify_token(refresh_data.refresh_token, "refresh")
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail="Refresh token has expired. Please log in again."
        )
    except (pyjwt.InvalidTokenError, ValueError) as e:
        raise HTTPException(
            status_code=401,
            detail=f"Invalid refresh token: {str(e)}"
        )
    
    # Get team member
    team_member_id = payload.get("sub")
    team_member = db.query(MerchantUser).filter(
        MerchantUser.id == team_member_id
    ).first()
    
    if not team_member:
        raise HTTPException(status_code=401, detail="Team member not found")
    
    if not team_member.is_active:
        raise HTTPException(status_code=401, detail="Account is inactive")
    
    # Create new access token
    new_access_token = create_access_token(
        team_member_id=str(team_member.id),
        merchant_id=str(team_member.merchant_id),
        role=team_member.role.value,
    )
    
    return RefreshTokenResponse(
        access_token=new_access_token,
        token_type="bearer",
        expires_in=3600,
    )


@router.post("/forgot-password")
@router_v1.post("/forgot-password")
async def forgot_password(
    forgot_data: ForgotPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Initiate password reset. Generates a reset token.
    
    In production, this sends a reset email.
    For security, always returns success regardless of whether email exists.
    """
    # Find team member
    team_member = db.query(MerchantUser).filter(
        MerchantUser.email == forgot_data.email.lower()
    ).first()
    
    if team_member and team_member.is_active:
        # Generate reset token
        reset_token = generate_password_reset_token()
        team_member.password_reset_token = reset_token
        team_member.password_reset_expires_at = datetime.utcnow() + timedelta(hours=1)
        db.commit()
        
        # TODO: Send password reset email with token
        logger.info(f"Password reset token generated for: {team_member.email}")
    
    # Always return success for security (don't reveal whether email exists)
    return {
        "message": "If an account with that email exists, a password reset link has been sent."
    }


@router.post("/reset-password")
@router_v1.post("/reset-password")
async def reset_password(
    reset_data: ResetPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Reset password using a valid reset token.
    """
    # Find team member by reset token
    team_member = db.query(MerchantUser).filter(
        MerchantUser.password_reset_token == reset_data.token
    ).first()
    
    if not team_member:
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired reset token"
        )
    
    # Check token expiry
    if team_member.password_reset_expires_at and \
       team_member.password_reset_expires_at < datetime.utcnow():
        # Clear expired token
        team_member.password_reset_token = None
        team_member.password_reset_expires_at = None
        db.commit()
        raise HTTPException(
            status_code=400,
            detail="Reset token has expired. Please request a new one."
        )
    
    # Validate password strength
    is_valid, error_msg = validate_password_strength(reset_data.new_password)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)
    
    # Set new password
    team_member.password_hash = hash_password(reset_data.new_password)
    team_member.password_reset_token = None
    team_member.password_reset_expires_at = None
    team_member.failed_login_attempts = 0
    team_member.locked_until = None
    db.commit()
    
    # Revoke all existing sessions for security
    await revoke_all_sessions(str(team_member.id), db)
    
    # Log password reset
    await log_password_reset(
        team_member_id=str(team_member.id),
        merchant_id=str(team_member.merchant_id),
        reset_by=None,  # Self-service reset
        request=request,
        db=db,
    )
    
    return {"message": "Password has been reset successfully. Please log in with your new password."}


@router.post("/change-password")
@router_v1.post("/change-password")
async def change_password(
    change_data: ChangePasswordRequest,
    request: Request,
    current_team_member: MerchantUser = Depends(get_current_team_member),
    db: Session = Depends(get_db),
):
    """
    Change password for the currently authenticated team member.
    Requires current password verification.
    """
    # Verify current password
    if not verify_password(change_data.current_password, current_team_member.password_hash):
        raise HTTPException(
            status_code=400,
            detail="Current password is incorrect"
        )
    
    # Validate new password strength
    is_valid, error_msg = validate_password_strength(change_data.new_password)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)
    
    # Ensure new password is different
    if verify_password(change_data.new_password, current_team_member.password_hash):
        raise HTTPException(
            status_code=400,
            detail="New password must be different from the current password"
        )
    
    # Update password
    current_team_member.password_hash = hash_password(change_data.new_password)
    db.commit()
    
    # Log password change
    await log_password_reset(
        team_member_id=str(current_team_member.id),
        merchant_id=str(current_team_member.merchant_id),
        reset_by=str(current_team_member.id),  # Self-initiated
        request=request,
        db=db,
    )
    
    return {"message": "Password changed successfully"}
