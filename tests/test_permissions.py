"""
Tests for Permission Service
Tests permission resolution, wildcard matching, custom grants/revokes
"""
import pytest
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

from app.core.database import Base
from app.core.permissions import (
    has_permission,
    get_role_permissions,
    get_custom_permissions,
    get_effective_permissions,
    grant_permission,
    revoke_permission,
    get_all_permissions,
    PERMISSIONS,
    ROLE_PERMISSIONS,
)
from app.models.models import (
    Merchant, MerchantUser, MerchantRole,
    Permission, RolePermission, TeamMemberPermission,
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


def seed_permissions(db_session):
    """Helper to seed permissions and return objects."""
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

    # Seed role permissions for viewer
    for perm_code in ROLE_PERMISSIONS.get('viewer', []):
        if perm_code in perm_objects:
            rp = RolePermission(role='viewer', permission_id=perm_objects[perm_code].id)
            db_session.add(rp)

    # Seed role permissions for admin (expand wildcards)
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
def seeded_db(db_session):
    """Seed DB with permissions and a merchant + team members."""
    perm_objects = seed_permissions(db_session)

    # Create merchant
    merchant = Merchant(
        id=uuid.uuid4(), name="Perm Test Biz",
        email="permtest@test.com", password_hash="fakehash",
        business_name="Perm Test Biz",
    )
    db_session.add(merchant)
    db_session.flush()

    owner = MerchantUser(
        id=uuid.uuid4(), merchant_id=merchant.id,
        email="owner@perm.com", name="Owner",
        password_hash="hash", role=MerchantRole.OWNER, is_active=True,
    )
    db_session.add(owner)

    viewer = MerchantUser(
        id=uuid.uuid4(), merchant_id=merchant.id,
        email="viewer@perm.com", name="Viewer",
        password_hash="hash", role=MerchantRole.VIEWER, is_active=True,
    )
    db_session.add(viewer)

    admin_user = MerchantUser(
        id=uuid.uuid4(), merchant_id=merchant.id,
        email="admin@perm.com", name="Admin",
        password_hash="hash", role=MerchantRole.ADMIN, is_active=True,
    )
    db_session.add(admin_user)
    db_session.commit()

    return {
        "merchant": merchant, "owner": owner,
        "viewer": viewer, "admin": admin_user,
        "permissions": perm_objects,
    }


# ============= Unit Tests: has_permission =============

class TestHasPermission:

    def test_exact_match(self):
        assert has_permission(["payments.view", "invoices.view"], "payments.view") is True

    def test_no_match(self):
        assert has_permission(["payments.view"], "invoices.create") is False

    def test_wildcard_all(self):
        assert has_permission(["*"], "anything.here") is True

    def test_category_wildcard(self):
        assert has_permission(["payments.*"], "payments.view") is True
        assert has_permission(["payments.*"], "payments.create") is True
        assert has_permission(["payments.*"], "invoices.view") is False

    def test_empty_permissions(self):
        assert has_permission([], "payments.view") is False

    def test_multiple_wildcards(self):
        perms = ["payments.*", "invoices.*"]
        assert has_permission(perms, "payments.refund") is True
        assert has_permission(perms, "invoices.delete") is True
        assert has_permission(perms, "team.view") is False


# ============= Async Tests: Role Permissions =============

class TestRolePermissions:

    async def test_owner_has_wildcard(self, db_session, seeded_db):
        perms = await get_role_permissions("owner", db_session)
        assert "*" in perms

    async def test_viewer_has_read_perms(self, db_session, seeded_db):
        perms = await get_role_permissions("viewer", db_session)
        assert "payments.view" in perms
        assert "invoices.view" in perms
        assert "payments.create" not in perms

    async def test_admin_has_expanded_perms(self, db_session, seeded_db):
        perms = await get_role_permissions("admin", db_session)
        assert "payments.view" in perms
        assert "payments.create" in perms


# ============= Async Tests: Effective Permissions =============

class TestEffectivePermissions:

    async def test_owner_effective_wildcard(self, db_session, seeded_db):
        owner = seeded_db["owner"]
        effective = await get_effective_permissions(str(owner.id), db_session)
        assert "*" in effective

    async def test_viewer_effective_perms(self, db_session, seeded_db):
        viewer = seeded_db["viewer"]
        effective = await get_effective_permissions(str(viewer.id), db_session)
        assert "payments.view" in effective
        assert "payments.create" not in effective

    async def test_nonexistent_member(self, db_session, seeded_db):
        effective = await get_effective_permissions(str(uuid.uuid4()), db_session)
        assert effective == []


# ============= Async Tests: Custom Permissions =============

class TestCustomPermissions:

    async def test_grant_permission(self, db_session, seeded_db):
        viewer = seeded_db["viewer"]
        owner = seeded_db["owner"]
        result = await grant_permission(
            str(viewer.id), "payments.create", str(owner.id), db_session,
        )
        assert result is True
        custom = await get_custom_permissions(str(viewer.id), db_session)
        assert "payments.create" in custom["granted"]

    async def test_grant_nonexistent_permission(self, db_session, seeded_db):
        viewer = seeded_db["viewer"]
        result = await grant_permission(
            str(viewer.id), "nonexistent.perm", str(seeded_db["owner"].id), db_session,
        )
        assert result is False

    async def test_revoke_permission(self, db_session, seeded_db):
        viewer = seeded_db["viewer"]
        owner = seeded_db["owner"]
        result = await revoke_permission(
            str(viewer.id), "payments.view", str(owner.id), db_session,
        )
        assert result is True
        custom = await get_custom_permissions(str(viewer.id), db_session)
        assert "payments.view" in custom["revoked"]

    async def test_effective_with_custom_grant(self, db_session, seeded_db):
        viewer = seeded_db["viewer"]
        owner = seeded_db["owner"]
        await grant_permission(str(viewer.id), "payments.refund", str(owner.id), db_session)
        effective = await get_effective_permissions(str(viewer.id), db_session)
        assert "payments.refund" in effective

    async def test_effective_with_custom_revoke(self, db_session, seeded_db):
        viewer = seeded_db["viewer"]
        owner = seeded_db["owner"]
        await revoke_permission(str(viewer.id), "analytics.view", str(owner.id), db_session)
        effective = await get_effective_permissions(str(viewer.id), db_session)
        assert "analytics.view" not in effective


# ============= Async Tests: Get All Permissions =============

class TestGetAllPermissions:

    async def test_returns_all_seeded(self, db_session, seeded_db):
        all_perms = await get_all_permissions(db_session)
        assert len(all_perms) >= len(PERMISSIONS)
        codes = {p["code"] for p in all_perms}
        assert "payments.view" in codes
        assert "team.view_logs" in codes
