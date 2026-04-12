"""
Tests for Team Authentication Service
Tests login, token refresh, password reset, and account lockout flows
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
import os
import uuid
from datetime import datetime, timedelta

# Set environment before imports
os.environ.setdefault("STELLAR_NETWORK", "testnet")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("API_KEY_SECRET", "test_secret_for_hmac_testing_only")
os.environ.setdefault("JWT_SECRET", "test_jwt_secret")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.database import Base, get_db
from app.core.team_auth import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
    validate_password_strength,
    check_account_lockout,
    increment_failed_attempts,
    reset_failed_attempts,
    generate_password_reset_token,
    verify_token,
    generate_secure_password,
)
from app.models.models import Merchant, MerchantUser, MerchantRole

pytestmark = pytest.mark.asyncio

# Test database setup — each test gets a fresh DB
engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def fresh_db():
    """Recreate all tables before each test for total isolation."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def override_db(db_session):
    def _override():
        try:
            yield db_session
        finally:
            pass
    app.dependency_overrides[get_db] = _override
    yield
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(override_db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def merchant_and_team_member(db_session):
    """Create a merchant and team member (owner) for testing."""
    merchant = Merchant(
        id=uuid.uuid4(),
        name="Test Business",
        email="owner@test.com",
        password_hash="fakehash",
        business_name="Test Business",
    )
    db_session.add(merchant)
    db_session.flush()

    team_member = MerchantUser(
        id=uuid.uuid4(),
        merchant_id=merchant.id,
        email="owner@test.com",
        name="Test Owner",
        password_hash=hash_password("Password123!"),
        role=MerchantRole.OWNER,
        is_active=True,
    )
    db_session.add(team_member)
    db_session.commit()
    return merchant, team_member


# ============= Unit Tests: Password Hashing =============

class TestPasswordHashing:

    def test_hash_and_verify_password(self):
        password = "MySecure@Pass1"
        hashed = hash_password(password)
        assert hashed != password
        assert verify_password(password, hashed) is True

    def test_verify_wrong_password(self):
        hashed = hash_password("CorrectPass1!")
        assert verify_password("WrongPass1!", hashed) is False

    def test_hash_is_unique(self):
        p = "SamePassword1!"
        h1 = hash_password(p)
        h2 = hash_password(p)
        assert h1 != h2  # bcrypt salting makes each hash unique


# ============= Unit Tests: Password Validation =============

class TestPasswordStrength:

    def test_valid_password(self):
        is_valid, msg = validate_password_strength("MyStrong@1x")
        assert is_valid is True
        assert msg is None

    def test_too_short(self):
        is_valid, msg = validate_password_strength("Ab1!")
        assert is_valid is False
        assert "8 characters" in msg

    def test_no_uppercase(self):
        is_valid, msg = validate_password_strength("nouppercase1!")
        assert is_valid is False
        assert "uppercase" in msg

    def test_no_lowercase(self):
        is_valid, msg = validate_password_strength("NOLOWERCASE1!")
        assert is_valid is False
        assert "lowercase" in msg

    def test_no_digit(self):
        is_valid, msg = validate_password_strength("NoDigitHere!")
        assert is_valid is False
        assert "digit" in msg

    def test_no_special_char(self):
        is_valid, msg = validate_password_strength("NoSpecial1a")
        assert is_valid is False
        assert "special" in msg


# ============= Unit Tests: JWT Tokens =============

class TestJWTTokens:

    def test_create_and_verify_access_token(self):
        token = create_access_token("member-id-1", "merchant-id-1", "admin")
        payload = verify_token(token, "access")
        assert payload["sub"] == "member-id-1"
        assert payload["merchant_id"] == "merchant-id-1"
        assert payload["role"] == "admin"
        assert payload["type"] == "access"

    def test_create_and_verify_refresh_token(self):
        token = create_refresh_token("member-id-1")
        payload = verify_token(token, "refresh")
        assert payload["sub"] == "member-id-1"
        assert payload["type"] == "refresh"

    def test_wrong_token_type_raises(self):
        token = create_access_token("m1", "m2", "admin")
        with pytest.raises(ValueError, match="Invalid token type"):
            verify_token(token, "refresh")

    def test_expired_token_raises(self):
        import jwt as pyjwt
        from app.core.team_auth import SECRET_KEY, ALGORITHM
        expired_payload = {
            "sub": "member-id",
            "type": "access",
            "exp": datetime.utcnow() - timedelta(hours=1),
        }
        token = pyjwt.encode(expired_payload, SECRET_KEY, algorithm=ALGORITHM)
        with pytest.raises(pyjwt.ExpiredSignatureError):
            verify_token(token, "access")


# ============= Unit Tests: Account Lockout =============

class TestAccountLockout:

    def test_not_locked(self, db_session, merchant_and_team_member):
        _, member = merchant_and_team_member
        is_locked, until = check_account_lockout(member)
        assert is_locked is False
        assert until is None

    def test_locked_until_future(self, db_session, merchant_and_team_member):
        _, member = merchant_and_team_member
        member.locked_until = datetime.utcnow() + timedelta(minutes=15)
        db_session.commit()
        is_locked, until = check_account_lockout(member)
        assert is_locked is True
        assert until is not None

    def test_lock_expired(self, db_session, merchant_and_team_member):
        _, member = merchant_and_team_member
        member.locked_until = datetime.utcnow() - timedelta(minutes=1)
        db_session.commit()
        is_locked, until = check_account_lockout(member)
        assert is_locked is False

    def test_increment_failed_attempts(self, db_session, merchant_and_team_member):
        _, member = merchant_and_team_member
        member.failed_login_attempts = 0
        member.locked_until = None
        db_session.commit()
        increment_failed_attempts(member, db_session)
        assert member.failed_login_attempts == 1

    def test_lockout_at_5_attempts(self, db_session, merchant_and_team_member):
        _, member = merchant_and_team_member
        member.failed_login_attempts = 4
        member.locked_until = None
        db_session.commit()
        increment_failed_attempts(member, db_session)
        assert member.failed_login_attempts == 5
        assert member.locked_until is not None

    def test_reset_failed_attempts(self, db_session, merchant_and_team_member):
        _, member = merchant_and_team_member
        member.failed_login_attempts = 3
        member.locked_until = datetime.utcnow() + timedelta(hours=1)
        db_session.commit()
        reset_failed_attempts(member, db_session)
        assert member.failed_login_attempts == 0
        assert member.locked_until is None


# ============= Unit Tests: Password Generation =============

class TestPasswordGeneration:

    def test_generate_secure_password(self):
        pwd = generate_secure_password()
        assert len(pwd) >= 16
        is_valid, _ = validate_password_strength(pwd)
        assert is_valid is True

    def test_reset_token_generation(self):
        t1 = generate_password_reset_token()
        t2 = generate_password_reset_token()
        assert t1 != t2
        assert len(t1) > 20


# ============= Integration Tests: Login API =============

class TestTeamLoginAPI:

    async def test_login_success(self, client, db_session, merchant_and_team_member):
        _, member = merchant_and_team_member
        res = await client.post("/auth/team/login", json={
            "email": member.email,
            "password": "Password123!",
        })
        assert res.status_code == 200
        data = res.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert data["team_member"]["email"] == member.email

    async def test_login_wrong_password(self, client, db_session, merchant_and_team_member):
        _, member = merchant_and_team_member
        res = await client.post("/auth/team/login", json={
            "email": member.email,
            "password": "WrongPassword1!",
        })
        assert res.status_code == 401

    async def test_login_nonexistent_email(self, client, db_session):
        res = await client.post("/auth/team/login", json={
            "email": "nobody@example.com",
            "password": "Password123!",
        })
        assert res.status_code == 401

    async def test_login_inactive_account(self, client, db_session, merchant_and_team_member):
        merchant, _ = merchant_and_team_member
        inactive = MerchantUser(
            merchant_id=merchant.id,
            email="inactive@test.com",
            name="Inactive User",
            password_hash=hash_password("Password123!"),
            role=MerchantRole.VIEWER,
            is_active=False,
        )
        db_session.add(inactive)
        db_session.commit()

        res = await client.post("/auth/team/login", json={
            "email": "inactive@test.com",
            "password": "Password123!",
        })
        assert res.status_code == 401

    async def test_logout(self, client, db_session, merchant_and_team_member):
        _, member = merchant_and_team_member
        login_res = await client.post("/auth/team/login", json={
            "email": member.email,
            "password": "Password123!",
        })
        token = login_res.json()["access_token"]
        res = await client.post(
            "/auth/team/logout",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200


# ============= Integration Tests: Token Refresh API =============

class TestTokenRefreshAPI:

    async def test_refresh_success(self, client, db_session, merchant_and_team_member):
        _, member = merchant_and_team_member
        login_res = await client.post("/auth/team/login", json={
            "email": member.email,
            "password": "Password123!",
        })
        refresh_token = login_res.json()["refresh_token"]
        res = await client.post("/auth/team/refresh", json={
            "refresh_token": refresh_token,
        })
        assert res.status_code == 200
        assert "access_token" in res.json()

    async def test_refresh_invalid_token(self, client, db_session):
        res = await client.post("/auth/team/refresh", json={
            "refresh_token": "invalid-token-string",
        })
        assert res.status_code == 401


# ============= Integration Tests: Password Change API =============

class TestChangePasswordAPI:

    async def test_change_password_success(self, client, db_session, merchant_and_team_member):
        _, member = merchant_and_team_member
        login_res = await client.post("/auth/team/login", json={
            "email": member.email,
            "password": "Password123!",
        })
        token = login_res.json()["access_token"]
        res = await client.post(
            "/auth/team/change-password",
            json={
                "current_password": "Password123!",
                "new_password": "NewPassword456!",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200

    async def test_change_password_wrong_current(self, client, db_session, merchant_and_team_member):
        _, member = merchant_and_team_member
        login_res = await client.post("/auth/team/login", json={
            "email": member.email,
            "password": "Password123!",
        })
        token = login_res.json()["access_token"]
        res = await client.post(
            "/auth/team/change-password",
            json={
                "current_password": "WrongCurrent1!",
                "new_password": "NewPassword456!",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 400


# ============= Integration Tests: Forgot/Reset Password =============

class TestPasswordResetAPI:

    async def test_forgot_password_always_succeeds(self, client, db_session):
        res = await client.post("/auth/team/forgot-password", json={
            "email": "nonexistent@test.com",
        })
        assert res.status_code == 200

    async def test_reset_password_flow(self, client, db_session, merchant_and_team_member):
        _, member = merchant_and_team_member
        res = await client.post("/auth/team/forgot-password", json={
            "email": member.email,
        })
        assert res.status_code == 200
        db_session.refresh(member)
        reset_token = member.password_reset_token
        assert reset_token is not None
        res = await client.post("/auth/team/reset-password", json={
            "token": reset_token,
            "new_password": "NewReset1!abc",
        })
        assert res.status_code == 200

    async def test_reset_password_invalid_token(self, client, db_session):
        res = await client.post("/auth/team/reset-password", json={
            "token": "invalid-reset-token-xxx",
            "new_password": "NewPass1!abc",
        })
        assert res.status_code == 400

    async def test_reset_password_weak_password(self, client, db_session, merchant_and_team_member):
        _, member = merchant_and_team_member
        member.password_reset_token = "test-reset-token-weak"
        member.password_reset_expires_at = datetime.utcnow() + timedelta(hours=1)
        db_session.commit()
        res = await client.post("/auth/team/reset-password", json={
            "token": "test-reset-token-weak",
            "new_password": "weak",
        })
        assert res.status_code == 400
