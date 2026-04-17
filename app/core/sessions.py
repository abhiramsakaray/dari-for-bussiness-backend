"""
Session Management Service
Handles team member session tracking and validation
"""
from datetime import datetime, timedelta
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_
from fastapi import Request
import uuid

from app.models.models import TeamMemberSession
from app.core.team_auth import hash_token


SESSION_EXPIRY_HOURS = 24  # Sessions expire after 24 hours


async def create_session(
    team_member_id: str,
    token: str,
    request: Request,
    db: Session,
    regenerate_on_auth: bool = True
) -> str:
    """
    Create a new session for team member.
    
    Session Fixation Protection:
    - Invalidates any existing sessions for this team member
    - Generates new session ID after authentication
    - Prevents session hijacking attacks
    
    Args:
        team_member_id: Team member UUID
        token: JWT access token
        request: FastAPI request object
        db: Database session
        regenerate_on_auth: If True, invalidates old sessions (default: True)
        
    Returns:
        Session ID
    """
    # Session fixation protection: Invalidate old sessions on new login
    if regenerate_on_auth:
        old_sessions = db.query(TeamMemberSession).filter(
            and_(
                TeamMemberSession.team_member_id == uuid.UUID(team_member_id),
                TeamMemberSession.revoked_at.is_(None)
            )
        ).all()
        
        for old_session in old_sessions:
            old_session.revoked_at = datetime.utcnow()
            old_session.revocation_reason = "Session regenerated on authentication"
        
        if old_sessions:
            db.commit()
    
    # Hash token for storage
    token_hash_value = hash_token(token)
    
    # Extract request metadata
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    
    # Create NEW session with NEW ID
    session = TeamMemberSession(
        team_member_id=uuid.UUID(team_member_id),
        token_hash=token_hash_value,
        ip_address=ip_address,
        user_agent=user_agent,
        expires_at=datetime.utcnow() + timedelta(hours=SESSION_EXPIRY_HOURS),
        last_activity=datetime.utcnow()
    )
    
    db.add(session)
    db.commit()
    db.refresh(session)
    
    return str(session.id)


async def validate_session(token: str, db: Session) -> Optional[TeamMemberSession]:
    """
    Validate session token and return session if valid
    
    Args:
        token: JWT access token
        db: Database session
        
    Returns:
        TeamMemberSession if valid, None otherwise
    """
    token_hash_value = hash_token(token)
    
    session = db.query(TeamMemberSession).filter(
        and_(
            TeamMemberSession.token_hash == token_hash_value,
            TeamMemberSession.revoked_at.is_(None),
            TeamMemberSession.expires_at > datetime.utcnow()
        )
    ).first()
    
    return session


async def update_session_activity(session_id: str, db: Session):
    """
    Update last activity timestamp for session
    
    Args:
        session_id: Session UUID
        db: Database session
    """
    session = db.query(TeamMemberSession).filter(
        TeamMemberSession.id == uuid.UUID(session_id)
    ).first()
    
    if session:
        session.last_activity = datetime.utcnow()
        db.commit()


async def revoke_session(session_id: str, db: Session):
    """
    Revoke a specific session
    
    Args:
        session_id: Session UUID
        db: Database session
    """
    session = db.query(TeamMemberSession).filter(
        TeamMemberSession.id == uuid.UUID(session_id)
    ).first()
    
    if session:
        session.revoked_at = datetime.utcnow()
        db.commit()


async def revoke_all_sessions(team_member_id: str, db: Session) -> int:
    """
    Revoke all active sessions for a team member
    
    Args:
        team_member_id: Team member UUID
        db: Database session
        
    Returns:
        Number of sessions revoked
    """
    sessions = db.query(TeamMemberSession).filter(
        and_(
            TeamMemberSession.team_member_id == uuid.UUID(team_member_id),
            TeamMemberSession.revoked_at.is_(None)
        )
    ).all()
    
    count = 0
    for session in sessions:
        session.revoked_at = datetime.utcnow()
        count += 1
    
    db.commit()
    return count


async def get_active_sessions(team_member_id: str, db: Session) -> List[TeamMemberSession]:
    """
    Get all active sessions for a team member
    
    Args:
        team_member_id: Team member UUID
        db: Database session
        
    Returns:
        List of active TeamMemberSession objects
    """
    sessions = db.query(TeamMemberSession).filter(
        and_(
            TeamMemberSession.team_member_id == uuid.UUID(team_member_id),
            TeamMemberSession.revoked_at.is_(None),
            TeamMemberSession.expires_at > datetime.utcnow()
        )
    ).order_by(TeamMemberSession.created_at.desc()).all()
    
    return sessions


async def cleanup_expired_sessions(db: Session) -> int:
    """
    Clean up expired sessions (background task)
    
    Args:
        db: Database session
        
    Returns:
        Number of sessions cleaned up
    """
    # Delete sessions that expired more than 7 days ago
    cutoff = datetime.utcnow() - timedelta(days=7)
    
    result = db.query(TeamMemberSession).filter(
        TeamMemberSession.expires_at < cutoff
    ).delete()
    
    db.commit()
    return result
