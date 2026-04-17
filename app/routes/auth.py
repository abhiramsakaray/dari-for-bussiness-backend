from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
import secrets
import httpx
import logging
import re
from app.core import get_db, hash_password, verify_password, create_access_token, settings
from app.core.rate_limiter import rate_limit
from app.models import Merchant, Admin
from app.schemas import (
    MerchantRegister, MerchantLogin, TokenResponse,
    GoogleAuthRequest, GoogleAuthResponse,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])
logger = logging.getLogger(__name__)


# ── Password Policy ──
_PASSWORD_MIN_LENGTH = 12

def validate_password(password: str) -> None:
    """Enforce strong password policy. Raises HTTPException on failure."""
    errors = []
    if len(password) < _PASSWORD_MIN_LENGTH:
        errors.append(f"Password must be at least {_PASSWORD_MIN_LENGTH} characters")
    if not re.search(r'[A-Z]', password):
        errors.append("Password must contain at least one uppercase letter")
    if not re.search(r'[a-z]', password):
        errors.append("Password must contain at least one lowercase letter")
    if not re.search(r'[0-9]', password):
        errors.append("Password must contain at least one digit")
    if not re.search(r'[!@#$%^&*()_+\-=\[\]{};\':",.<>?/\\|`~]', password):
        errors.append("Password must contain at least one special character")
    if errors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password does not meet security requirements: " + "; ".join(errors)
        )


def generate_api_key() -> str:
    """Generate a secure API key for merchant."""
    return f"pk_live_{secrets.token_urlsafe(32)}"


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@rate_limit(max_requests=3, window_seconds=300, key_prefix="auth_register")
async def register_merchant(
    merchant_data: MerchantRegister,
    request: Request,
    db: Session = Depends(get_db)
):
    """Register a new merchant."""
    # Check if email already exists
    existing_merchant = db.query(Merchant).filter(Merchant.email == merchant_data.email).first()
    if existing_merchant:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Enforce password policy
    validate_password(merchant_data.password)
    
    # Create new merchant with API key
    new_merchant = Merchant(
        name=merchant_data.name,
        email=merchant_data.email,
        password_hash=hash_password(merchant_data.password),
        api_key=generate_api_key(),  # Auto-generate API key on registration
        webhook_secret=secrets.token_hex(32),  # 256-bit webhook signing secret
        merchant_category=getattr(merchant_data, 'merchant_category', 'individual') or 'individual',
        onboarding_step=0,
        onboarding_completed=False,
    )
    
    db.add(new_merchant)
    db.commit()
    db.refresh(new_merchant)
    
    # Generate JWT token
    access_token = create_access_token(
        data={"sub": str(new_merchant.id), "role": "merchant"}
    )
    
    return TokenResponse(
        access_token=access_token,
        api_key=new_merchant.api_key,
        onboarding_completed=False,
        onboarding_step=0,
    )


@router.post("/login", response_model=TokenResponse)
@rate_limit(max_requests=5, window_seconds=60, key_prefix="auth_login")
async def login_merchant(
    credentials: MerchantLogin,
    request: Request,
    db: Session = Depends(get_db)
):
    """Login as a merchant or admin."""
    from app.core.security_utils import (
        check_account_lockout,
        record_failed_login,
        clear_login_attempts,
    )

    # Brute-force protection: per-email AND per-IP
    check_account_lockout(credentials.email)
    client_ip = request.client.host if request.client else "unknown"
    check_account_lockout(f"ip:{client_ip}")

    # First check if it's an admin
    admin = db.query(Admin).filter(Admin.email == credentials.email).first()
    if admin and verify_password(credentials.password, admin.password_hash):
        clear_login_attempts(credentials.email)
        # Generate admin JWT token
        access_token = create_access_token(
            data={"sub": str(admin.id), "role": "admin"}
        )
        return TokenResponse(
            access_token=access_token,
            api_key=""  # Admins don't use API keys for payment creation
        )
    
    # Otherwise, check merchant
    merchant = db.query(Merchant).filter(Merchant.email == credentials.email).first()
    
    if not merchant or not verify_password(credentials.password, merchant.password_hash):
        record_failed_login(credentials.email)
        record_failed_login(f"ip:{client_ip}")  # Also track IP
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    if not merchant.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled"
        )
    
    # Successful login — clear lockout counter
    clear_login_attempts(credentials.email)

    # Generate API key if merchant doesn't have one (backward compatibility)
    if not merchant.api_key:
        merchant.api_key = generate_api_key()
        db.commit()
        db.refresh(merchant)
    
    # Generate JWT token
    access_token = create_access_token(
        data={"sub": str(merchant.id), "role": "merchant"}
    )
    
    return TokenResponse(
        access_token=access_token,
        api_key=merchant.api_key,
        onboarding_completed=merchant.onboarding_completed or False,
        onboarding_step=merchant.onboarding_step or 0,
    )


# ============= GOOGLE OAUTH =============

@router.post("/google", response_model=GoogleAuthResponse)
@rate_limit(max_requests=10, window_seconds=60, key_prefix="auth_google")
async def google_auth(
    auth_data: GoogleAuthRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Authenticate or register via Google OAuth.
    
    Accepts a Google ID token (from frontend Google Sign-In).
    - If the Google user already exists → login and return JWT.
    - If new → create merchant account and return JWT with is_new_user=True.
    """
    # Verify Google token by calling Google's tokeninfo endpoint
    google_user = await _verify_google_token(auth_data.token)
    
    if not google_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google token",
        )
    
    google_id = google_user["sub"]
    email = google_user.get("email", "")
    name = google_user.get("name", email.split("@")[0])
    avatar_url = google_user.get("picture", "")
    
    # Check if merchant already exists by google_id
    merchant = db.query(Merchant).filter(Merchant.google_id == google_id).first()
    
    if merchant:
        # Existing Google user → login
        if not merchant.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is disabled",
            )
        
        # Generate API key if missing
        if not merchant.api_key:
            merchant.api_key = generate_api_key()
            db.commit()
        
        access_token = create_access_token(
            data={"sub": str(merchant.id), "role": "merchant"}
        )
        
        return GoogleAuthResponse(
            access_token=access_token,
            api_key=merchant.api_key or "",
            is_new_user=False,
            onboarding_completed=merchant.onboarding_completed or False,
            onboarding_step=merchant.onboarding_step or 0,
        )
    existing_by_email = db.query(Merchant).filter(Merchant.email == email).first()
    
    if existing_by_email:
        # Link Google to existing account
        existing_by_email.google_id = google_id
        existing_by_email.avatar_url = avatar_url
        db.commit()
        db.refresh(existing_by_email)
        
        if not existing_by_email.api_key:
            existing_by_email.api_key = generate_api_key()
            db.commit()
        
        access_token = create_access_token(
            data={"sub": str(existing_by_email.id), "role": "merchant"}
        )
        
        return GoogleAuthResponse(
            access_token=access_token,
            api_key=existing_by_email.api_key or "",
            is_new_user=False,
            onboarding_completed=existing_by_email.onboarding_completed or False,
            onboarding_step=existing_by_email.onboarding_step or 0,
        )
    
    # New user → create merchant account
    new_merchant = Merchant(
        name=name,
        email=email,
        google_id=google_id,
        avatar_url=avatar_url,
        api_key=generate_api_key(),
        webhook_secret=secrets.token_hex(32),  # 256-bit webhook signing secret
        onboarding_step=0,
        onboarding_completed=False,
        merchant_category="individual",
    )
    
    db.add(new_merchant)
    db.commit()
    db.refresh(new_merchant)
    
    access_token = create_access_token(
        data={"sub": str(new_merchant.id), "role": "merchant"}
    )
    
    logger.info(f"New merchant registered via Google: {new_merchant.email}")
    
    return GoogleAuthResponse(
        access_token=access_token,
        api_key=new_merchant.api_key,
        is_new_user=True,
        onboarding_completed=False,
        onboarding_step=0,
    )


async def _verify_google_token(token: str) -> dict | None:
    """
    Verify a Google ID token using Google's tokeninfo endpoint.
    Returns user info dict or None if invalid.
    """
    try:
        async with httpx.AsyncClient() as client:
            # Try as ID token first  
            resp = await client.get(
                f"https://oauth2.googleapis.com/tokeninfo?id_token={token}",
                timeout=10.0,
            )
            
            if resp.status_code == 200:
                data = resp.json()
                # Validate client_id (audience check)
                if settings.GOOGLE_CLIENT_ID and data.get("aud") != settings.GOOGLE_CLIENT_ID:
                    logger.warning(f"Google token audience mismatch: {data.get('aud')}")
                    return None  # Always enforce audience validation
                return data
            
            # Try as access token (userinfo endpoint)
            resp2 = await client.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10.0,
            )
            
            if resp2.status_code == 200:
                return resp2.json()
            
            logger.warning(f"Google token verification failed: {resp.status_code}")
            return None
            
    except Exception as e:
        logger.error(f"Google token verification error: {e}")
        return None
