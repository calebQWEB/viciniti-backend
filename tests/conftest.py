import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.database import Base, get_db
from app.config import get_settings

settings = get_settings()

# Use a separate test database
TEST_DATABASE_URL = settings.DATABASE_URL.replace(
    "/viciniti", "/viciniti_test"
)

engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=engine
)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """Create all tables before tests, drop after."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture(autouse=True)
def clean_tables():
    """Clear all tables between tests so they don't interfere."""
    yield
    db = TestingSessionLocal()
    for table in reversed(Base.metadata.sorted_tables):
        db.execute(table.delete())
    db.commit()
    db.close()

@pytest.fixture
def client():
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

@pytest.fixture
def auth_headers(client):
    """Register and log in a test user, return auth headers."""
    client.post("/auth/register", json={
        "name": "Test User",
        "email": "test@viciniti.com",
        "password": "testpass123",
    })
    # Login expects JSON not form data
    response = client.post("/auth/login", json={
        "email": "test@viciniti.com",
        "password": "testpass123",
    })
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture
def second_auth_headers(client):
    """A second user for testing ownership restrictions."""
    client.post("/auth/register", json={
        "name": "Second User",
        "email": "second@viciniti.com",
        "password": "testpass123",
    })
    response = client.post("/auth/login", json={
        "email": "second@viciniti.com",
        "password": "testpass123",
    })
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}