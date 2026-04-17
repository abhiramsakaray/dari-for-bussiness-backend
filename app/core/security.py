from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
import bcrypt
import uuid as uuid_module
from fastapi import HTTPException, status, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import settings

security = HTTPBearer()


def hash_password(password: str) -> str:
    """Hash a password using bcrypt. Truncates to 72 bytes for compatibility."""
    # Bcrypt has a 72-byte limit
    password_bytes = password.encode('utf-8')[:72]
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash using bcrypt."""
    try:
        password_bytes = plain_password.encode('utf-8')[:72]
        hashed_bytes = hashed_password.encode('utf-8')
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    except Exception:
        return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> dict:
    """Decode and verify a JWT token."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """Get current authenticated user from JWT token."""
    token = credentials.credentials
    payload = decode_access_token(token)
    
    user_id = payload.get("sub")
    role = payload.get("role")
    
    if user_id is None or role is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )
    
    # Validate that the sub claim is a valid UUID (prevents injection)
    try:
        uuid_module.UUID(user_id, version=4)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: malformed user identifier",
        )
    
    # Validate role is an expected value
    if role not in ("merchant", "admin", "team_member"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: unknown role",
        )
    
    return {"id": user_id, "role": role}


def require_role(required_role: str):
    """Dependency to require a specific role."""
    def role_checker(current_user: dict = Depends(get_current_user)):
        if current_user["role"] != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access forbidden: {required_role} role required",
            )
        return current_user
    return role_checker


# Role-specific dependencies
require_merchant = require_role("merchant")
require_admin = require_role("admin")


def require_merchant_or_admin(current_user: dict = Depends(get_current_user)):
    """Dependency that accepts both merchant and admin roles."""
    if current_user["role"] not in ["merchant", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access forbidden: merchant or admin role required. Got role: {current_user.get('role')}",
        )
    return current_user


def require_replay_protection(request: Request):
    """Dependency to enforce Replay Protection headers on sensitive routes."""
    nonce = request.headers.get("X-Request-Nonce")
    timestamp = request.headers.get("X-Request-Timestamp")
    if not nonce or not timestamp:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Replay protection headers required: X-Request-Nonce and X-Request-Timestamp",
        )
    return True
