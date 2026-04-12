"""
Team Member Authentication Service
Handles JWT tokens, password hashing, and account security
"""
import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict
import jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.models.models import MerchantUser
from app.core.config import settings

# Password hashing context with bcrypt (12 rounds minimum as per requirements)
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12  # Minimum 12 salt rounds for security
)

# JWT settings
SECRET_KEY = settings.JWT_SECRET
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60  # 1 hour
REFRESH_TOKEN_EXPIRE_DAYS = 7  # 7 days


def create_access_token(team_member_id: str, merchant_id: str, role: str) -> str:
    """
    Create JWT access token for team member
    
    Args:
        team_member_id: Team member UUID
        merchant_id: Merchant UUID
        role: Team member role
        
    Returns:
        JWT access token string
    """
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": team_member_id,
        "merchant_id": merchant_id,
        "role": role,
        "type": "access",
        "exp": expire,
        "iat": datetime.utcnow()
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(team_member_id: str) -> str:
    """
    Create JWT refresh token for team member
    
    Args:
        team_member_id: Team member UUID
        
    Returns:
        JWT refresh token string
    """
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": team_member_id,
        "type": "refresh",
        "exp": expire,
        "iat": datetime.utcnow()
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str, token_type: str = "access") -> Dict:
    """
    Verify and decode JWT token
    
    Args:
        token: JWT token string
        token_type: Expected token type ("access" or "refresh")
        
    Returns:
        Decoded token payload
        
    Raises:
        jwt.ExpiredSignatureError: Token has expired
        jwt.InvalidTokenError: Token is invalid
        ValueError: Token type mismatch
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        
        # Verify token type
        if payload.get("type") != token_type:
            raise ValueError(f"Invalid token type. Expected {token_type}, got {payload.get('type')}")
        
        return payload
    except jwt.ExpiredSignatureError:
        raise jwt.ExpiredSignatureError("Token has expired")
    except jwt.InvalidTokenError as e:
        raise jwt.InvalidTokenError(f"Invalid token: {str(e)}")


def hash_password(password: str) -> str:
    """
    Hash password using bcrypt
    
    Args:
        password: Plain text password
        
    Returns:
        Hashed password string
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify password against hash
    
    Args:
        plain_password: Plain text password
        hashed_password: Hashed password from database
        
    Returns:
        True if password matches, False otherwise
    """
    return pwd_context.verify(plain_password, hashed_password)


def generate_password_reset_token() -> str:
    """
    Generate secure password reset token
    
    Returns:
        Random URL-safe token string
    """
    return secrets.token_urlsafe(32)


def generate_secure_password(length: int = 16) -> str:
    """
    Generate a secure random password
    
    Args:
        length: Password length (default 16)
        
    Returns:
        Random password string
    """
    import string
    import random
    
    # Ensure password has all required character types
    chars = string.ascii_letters + string.digits + "!@#$%^&*"
    password = ''.join(random.choice(chars) for _ in range(length))
    
    # Ensure it meets complexity requirements
    has_upper = any(c.isupper() for c in password)
    has_lower = any(c.islower() for c in password)
    has_digit = any(c.isdigit() for c in password)
    has_special = any(c in "!@#$%^&*" for c in password)
    
    if not (has_upper and has_lower and has_digit and has_special):
        # Regenerate if doesn't meet requirements
        return generate_secure_password(length)
    
    return password


def validate_password_strength(password: str) -> tuple[bool, Optional[str]]:
    """
    Validate password meets strength requirements
    
    Requirements:
    - Minimum 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character
    
    Args:
        password: Password to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    
    if not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter"
    
    if not any(c.islower() for c in password):
        return False, "Password must contain at least one lowercase letter"
    
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one digit"
    
    if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password):
        return False, "Password must contain at least one special character"
    
    return True, None


def check_account_lockout(team_member: MerchantUser) -> tuple[bool, Optional[datetime]]:
    """
    Check if account is locked due to failed login attempts
    
    Args:
        team_member: MerchantUser instance
        
    Returns:
        Tuple of (is_locked, locked_until)
    """
    if not team_member.locked_until:
        return False, None
    
    if team_member.locked_until > datetime.utcnow():
        return True, team_member.locked_until
    
    # Lock period has expired
    return False, None


def increment_failed_attempts(team_member: MerchantUser, db: Session):
    """
    Increment failed login attempts and lock account if threshold reached
    
    Lockout policy:
    - 5 attempts: Lock for 15 minutes
    - 10 attempts: Lock for 1 hour
    - 20 attempts: Lock until admin unlocks
    
    Args:
        team_member: MerchantUser instance
        db: Database session
    """
    team_member.failed_login_attempts += 1
    
    if team_member.failed_login_attempts >= 20:
        # Permanent lock until admin unlocks
        team_member.locked_until = datetime.utcnow() + timedelta(days=365)
    elif team_member.failed_login_attempts >= 10:
        # Lock for 1 hour
        team_member.locked_until = datetime.utcnow() + timedelta(hours=1)
    elif team_member.failed_login_attempts >= 5:
        # Lock for 15 minutes
        team_member.locked_until = datetime.utcnow() + timedelta(minutes=15)
    
    db.commit()


def reset_failed_attempts(team_member: MerchantUser, db: Session):
    """
    Reset failed login attempts counter on successful login
    
    Args:
        team_member: MerchantUser instance
        db: Database session
    """
    team_member.failed_login_attempts = 0
    team_member.locked_until = None
    team_member.last_login = datetime.utcnow()
    db.commit()


def hash_token(token: str) -> str:
    """
    Hash token using SHA256 for storage
    
    Args:
        token: JWT token string
        
    Returns:
        SHA256 hash of token
    """
    return hashlib.sha256(token.encode()).hexdigest()
