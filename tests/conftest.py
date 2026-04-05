import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
import os
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import asyncio

# Need to set environment before importing app
os.environ["STELLAR_NETWORK"] = "testnet"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["API_KEY_SECRET"] = "test_secret_for_hmac_testing_only"
os.environ["JWT_SECRET"] = "test_jwt_secret"

from app.main import app
from app.core.database import Base, get_db
from app.core.security import create_access_token

# Use an in-memory SQLite for testing
engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="session")
def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

@pytest.fixture
def db_session(reset_db):
    """Returns a fresh database session."""
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()

@pytest.fixture
def override_get_db(db_session):
    """Override the get_db dependency to use the test database."""
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    yield
    app.dependency_overrides.clear()

@pytest_asyncio.fixture
async def client(override_get_db):
    """Return an async httpx client tied to the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

@pytest.fixture
def merchant_token():
    """Generates a mock JWT token for a merchant."""
    return create_access_token({"sub": "d50a7c93-519e-4e4b-9721-e00f9f302b11", "role": "merchant"})

@pytest.fixture
def auth_headers(merchant_token):
    """Returns headers with merchant Bearer token."""
    return {"Authorization": f"Bearer {merchant_token}"}
