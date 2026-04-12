"""
Team RBAC Integration Tests
End-to-end tests for authentication, permission enforcement, and activity logging
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
import os
import uuid
from datetime import datetime

os.environ.setdefault("STELLAR_NETWORK", "testnet")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("API_KEY_SECRET", "test_secret_for_hmac_testing_only")
os.environ.setdefault("JWT_SECRET", "test_jwt_secret")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.database import Base, get_db
from app.core.team_auth import hash_password
from app.core.permissions import PERMISSIONS, ROLE_PERMISSIONS
from app.models.models import (
    Merchant, MerchantUser, MerchantRole,
    Permission, RolePermission, TeamMemberSession, ActivityLog,
)

pytestmark = pytest.mark.asyncio

# Test database setup
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


def seed_permissions_and_roles(db_session):
    """Seed all permissions and role mappings into DB."""
    perm_objects = {}
    for code, desc in PERMISSIONS.items():
        category = code.split('.')[0]
        p = Permission(
            id=uuid.uuid4(), code=code, name=desc,
            description=desc, category=category,
        )
        db_session.add(p)
        perm_objects[code] = p
    db_session.flush()

    for perm_code in ROLE_PERMISSIONS.get('viewer', []):
        if perm_code in perm_objects:
            rp = RolePermission(role='viewer', permission_id=perm_objects[perm_code].id)
            db_session.add(rp)

    for perm_code in ROLE_PERMISSIONS.get('admin', []):
        if perm_code.endswith('.*'):
            prefix = perm_code.replace('.*', '')
            for code, p in perm_objects.items():
                if code.startswith(prefix + '.'):
                    rp = RolePermission(role='admin', permission_id=p.id)
                    db_session.add(rp)
        elif perm_code in perm_objects:
            rp = RolePermission(role='admin', permission_id=perm_objects[perm_code].id)
            db_session.add(rp)
    db_session.flush()
    return perm_objects


@pytest.fixture
def seeded_data(db_session):
    """Create merchant with owner and viewer, seed permissions."""
    seed_permissions_and_roles(db_session)

    merchant = Merchant(
        id=uuid.uuid4(), name="RBAC Test Co.",
        email="rbac@test.com", password_hash="fakehash",
        business_name="RBAC Test Co.",
    )
    db_session.add(merchant)
    db_session.flush()

    owner = MerchantUser(
        id=uuid.uuid4(), merchant_id=merchant.id,
        email="owner@rbac.com", name="Owner",
        password_hash=hash_password("OwnerPass1!"),
        role=MerchantRole.OWNER, is_active=True,
    )
    db_session.add(owner)

    viewer = MerchantUser(
        id=uuid.uuid4(), merchant_id=merchant.id,
        email="viewer@rbac.com", name="Viewer",
        password_hash=hash_password("ViewerPass1!"),
        role=MerchantRole.VIEWER, is_active=True,
    )
    db_session.add(viewer)
    db_session.commit()
    return {"merchant": merchant, "owner": owner, "viewer": viewer}


async def login_member(client, email, password):
    """Helper to login and return access token."""
    res = await client.post("/auth/team/login", json={
        "email": email, "password": password,
    })
    assert res.status_code == 200, f"Login failed: {res.json()}"
    return res.json()["access_token"]


# ============= E2E: Login → Protected Endpoint → Logout =============

class TestEndToEndAuth:

    async def test_full_auth_flow(self, client, db_session, seeded_data):
        token = await login_member(client, "owner@rbac.com", "OwnerPass1!")
        res = await client.get(
            "/team/permissions",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        res = await client.post(
            "/auth/team/logout",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200

    async def test_unauthenticated_access_denied(self, client, db_session, seeded_data):
        res = await client.get("/team/permissions")
        assert res.status_code in [401, 403]

    async def test_invalid_token_denied(self, client, db_session, seeded_data):
        res = await client.get(
            "/team/permissions",
            headers={"Authorization": "Bearer invalid-token"},
        )
        assert res.status_code == 401


# ============= Permission Enforcement =============

class TestPermissionEnforcement:

    async def test_owner_can_create_member(self, client, db_session, seeded_data):
        token = await login_member(client, "owner@rbac.com", "OwnerPass1!")
        res = await client.post(
            "/team/members",
            json={
                "email": "newmember@rbac.com",
                "name": "New Member",
                "role": "developer",
                "auto_generate_password": True,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["email"] == "newmember@rbac.com"
        assert data["temporary_password"] is not None

    async def test_viewer_cannot_create_member(self, client, db_session, seeded_data):
        token = await login_member(client, "viewer@rbac.com", "ViewerPass1!")
        res = await client.post(
            "/team/members",
            json={
                "email": "unauthorized@rbac.com",
                "name": "Unauthorized",
                "role": "viewer",
                "password": "SecurePass1!",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 403

    async def test_owner_can_view_member_permissions(self, client, db_session, seeded_data):
        viewer = seeded_data["viewer"]
        token = await login_member(client, "owner@rbac.com", "OwnerPass1!")
        res = await client.get(
            f"/team/members/{viewer.id}/permissions",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["role"] == "viewer"
        assert "payments.view" in data["effective_permissions"]

    async def test_viewer_can_view_own_permissions(self, client, db_session, seeded_data):
        viewer = seeded_data["viewer"]
        token = await login_member(client, "viewer@rbac.com", "ViewerPass1!")
        res = await client.get(
            f"/team/members/{viewer.id}/permissions",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200

    async def test_owner_can_grant_permission(self, client, db_session, seeded_data):
        viewer = seeded_data["viewer"]
        token = await login_member(client, "owner@rbac.com", "OwnerPass1!")
        res = await client.post(
            f"/team/members/{viewer.id}/permissions",
            json={"grant": ["payments.create"], "revoke": []},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert "payments.create" in data["results"]["granted"]
        assert "payments.create" in data["effective_permissions"]


# ============= Activity Logging =============

class TestActivityLogging:

    async def test_login_creates_activity_log(self, client, db_session, seeded_data):
        await login_member(client, "owner@rbac.com", "OwnerPass1!")
        logs = db_session.query(ActivityLog).filter(
            ActivityLog.action == "team.login"
        ).all()
        assert len(logs) >= 1
        assert logs[0].team_member_id == seeded_data["owner"].id

    async def test_permission_change_logged(self, client, db_session, seeded_data):
        viewer = seeded_data["viewer"]
        token = await login_member(client, "owner@rbac.com", "OwnerPass1!")
        await client.post(
            f"/team/members/{viewer.id}/permissions",
            json={"grant": ["invoices.create"], "revoke": []},
            headers={"Authorization": f"Bearer {token}"},
        )
        logs = db_session.query(ActivityLog).filter(
            ActivityLog.action == "team.permission_granted"
        ).all()
        assert len(logs) >= 1


# ============= Session Management =============

class TestSessionManagement:

    async def test_login_creates_session(self, client, db_session, seeded_data):
        owner = seeded_data["owner"]
        await login_member(client, "owner@rbac.com", "OwnerPass1!")
        sessions = db_session.query(TeamMemberSession).filter(
            TeamMemberSession.team_member_id == owner.id,
            TeamMemberSession.revoked_at.is_(None),
        ).all()
        assert len(sessions) >= 1

    async def test_view_sessions(self, client, db_session, seeded_data):
        owner = seeded_data["owner"]
        token = await login_member(client, "owner@rbac.com", "OwnerPass1!")
        res = await client.get(
            f"/team/members/{owner.id}/sessions",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        sessions = res.json()
        assert isinstance(sessions, list)
        assert len(sessions) >= 1

    async def test_revoke_sessions(self, client, db_session, seeded_data):
        viewer = seeded_data["viewer"]
        await login_member(client, "viewer@rbac.com", "ViewerPass1!")
        owner_token = await login_member(client, "owner@rbac.com", "OwnerPass1!")
        res = await client.post(
            f"/team/members/{viewer.id}/revoke-sessions",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert res.status_code == 200
        assert res.json()["sessions_revoked"] >= 1


# ============= Password Management =============

class TestPasswordManagement:

    async def test_admin_reset_member_password(self, client, db_session, seeded_data):
        viewer = seeded_data["viewer"]
        token = await login_member(client, "owner@rbac.com", "OwnerPass1!")
        res = await client.post(
            f"/team/members/{viewer.id}/reset-password",
            json={"auto_generate_password": True},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["sessions_revoked"] is True
        assert "temporary_password" in data
